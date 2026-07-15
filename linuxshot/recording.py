"""Screen recording.

Backends, by session type:

- KDE Wayland: Spectacle (>= 6.x has --record). It only emits webm and
  is stopped by invoking spectacle -R again, which *toggles* - so state
  tracking matters: a stray toggle while idle would start a recording.
  We only ever toggle while our tracked pid is alive.
- wlroots Wayland: wf-recorder, stopped with SIGINT.
- X11: ffmpeg x11grab, stopped with SIGINT.

The active recording is tracked in a state file under XDG_RUNTIME_DIR
so any linuxshot process (hotkey, tray, CLI) can stop what another one
started. If the requested output format differs from what the backend
produces natively, ffmpeg converts after the stop.
"""

import json
import os
import signal
import subprocess
import time
from datetime import datetime

from .config import Config
from .utils import (
    DisplayServer,
    get_data_dir,
    get_display_server,
    has_command,
    run_cmd,
)

MODES = ("region", "screen", "window")
STOP_WAIT_SECONDS = 15
GIF_MAX_WIDTH = 1280


class RecordingError(Exception):
    pass


def state_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isdir(runtime):
        return os.path.join(runtime, "linuxshot-recording.json")
    return os.path.join(get_data_dir(), "recording.json")


def current() -> dict | None:
    """The active recording's state, or None. Stale files (recorder
    died) are cleaned up on sight."""
    try:
        with open(state_path()) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not _pid_alive(state.get("pid", -1)):
        _clear_state()
        return None
    return state


def detect_backend() -> str:
    """'spectacle', 'wf-recorder', 'x11grab', or 'none'."""
    if get_display_server() == DisplayServer.WAYLAND:
        if has_command("spectacle") and _spectacle_supports_record():
            return "spectacle"
        if has_command("wf-recorder"):
            return "wf-recorder"
        return "none"
    if has_command("ffmpeg"):
        return "x11grab"
    return "none"


def start(mode: str = "screen") -> dict:
    if mode not in MODES:
        raise RecordingError(f"Unknown recording mode '{mode}'.")
    if current() is not None:
        raise RecordingError("A recording is already running.")

    backend = detect_backend()
    if backend == "none":
        raise RecordingError(
            "No screen recorder found for this session.\n"
            "KDE needs spectacle 6+, wlroots compositors need wf-recorder, "
            "X11 needs ffmpeg."
        )

    native_ext = "webm" if backend == "spectacle" else "mp4"
    config = Config.get()
    filename = datetime.now().strftime(f"{config['filename_pattern']}.{native_ext}")
    output = os.path.join(config.get_screenshot_dir(), filename)

    cmd = _start_command(backend, mode, output)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    # Give it a moment to fail fast (bad geometry, missing portal, ...)
    time.sleep(1.5)
    if process.poll() is not None:
        raise RecordingError(
            f"The recorder exited immediately (backend: {backend}). "
            "Was the selection cancelled?"
        )

    state = {
        "pid": process.pid,
        "backend": backend,
        "mode": mode,
        "output": output,
        "format": config["recording_format"] or native_ext,
        "started": time.time(),
    }
    with open(state_path(), "w") as f:
        json.dump(state, f)
    return state


def stop() -> str:
    """Stop the active recording, convert if needed, and return the
    final file path."""
    state = current()
    if state is None:
        raise RecordingError("No recording is running.")

    pid = state["pid"]
    if state["backend"] == "spectacle":
        # Toggling stops the running instance; only safe because we
        # just confirmed our pid is alive.
        run_cmd(["spectacle", "-b", "-n", "-R", state["mode"]])
    else:
        _signal_pid(pid, signal.SIGINT)

    deadline = time.time() + STOP_WAIT_SECONDS
    while _pid_alive(pid) and time.time() < deadline:
        time.sleep(0.3)
    if _pid_alive(pid):
        _signal_pid(pid, signal.SIGTERM)
        time.sleep(2)
    if _pid_alive(pid):
        _signal_pid(pid, signal.SIGKILL)
    _clear_state()

    output = state["output"]
    if not os.path.exists(output) or os.path.getsize(output) == 0:
        if os.path.exists(output):
            os.remove(output)
        raise RecordingError("The recording produced no usable file.")
    return _convert(output, state["format"])


def elapsed_seconds(state: dict) -> int:
    return int(time.time() - state.get("started", time.time()))


def _start_command(backend: str, mode: str, output: str) -> list[str]:
    if backend == "spectacle":
        return ["spectacle", "-b", "-n", "-R", mode, "-o", output]

    if backend == "wf-recorder":
        cmd = ["wf-recorder", "-f", output]
        if mode == "region":
            selection = run_cmd(["slurp"])
            geometry = selection.stdout.strip()
            if selection.returncode != 0 or not geometry:
                raise RecordingError("Region selection cancelled.")
            cmd += ["-g", geometry]
        return cmd

    # x11grab: ffmpeg needs explicit geometry
    if mode == "region" and has_command("slop"):
        selection = run_cmd(["slop", "-f", "%wx%h %x,%y"])
        if selection.returncode != 0 or not selection.stdout.strip():
            raise RecordingError("Region selection cancelled.")
        size, offset = selection.stdout.strip().split()
        x, y = offset.split(",")
    else:
        size = _x11_screen_size()
        x = y = "0"
    display = os.environ.get("DISPLAY", ":0")
    return [
        "ffmpeg", "-y", "-f", "x11grab", "-video_size", size,
        "-framerate", "30", "-i", f"{display}+{x},{y}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        output,
    ]


def _convert(path: str, fmt: str) -> str:
    """Transcode to the requested format; keeps the original if ffmpeg
    is unavailable or fails."""
    base, ext = os.path.splitext(path)
    if ext.lstrip(".") == fmt:
        return path
    if not has_command("ffmpeg"):
        return path

    target = f"{base}.{fmt}"
    if fmt == "gif":
        fps = int(Config.get()["gif_fps"])
        filters = (
            f"fps={fps},scale='min(iw,{GIF_MAX_WIDTH})':-2:flags=lanczos,"
            "split[a][b];[a]palettegen[p];[b][p]paletteuse"
        )
        cmd = ["ffmpeg", "-y", "-i", path, "-vf", filters, target]
    elif fmt == "mp4":
        cmd = ["ffmpeg", "-y", "-i", path, "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", "-an", target]
    elif fmt == "webm":
        cmd = ["ffmpeg", "-y", "-i", path, "-c:v", "libvpx-vp9",
               "-crf", "32", "-b:v", "0", "-an", target]
    else:
        return path

    result = run_cmd(cmd, timeout=600)
    if result.returncode != 0 or not os.path.exists(target):
        return path
    os.remove(path)
    return target


def _spectacle_supports_record() -> bool:
    result = run_cmd(["spectacle", "--help"])
    return "--record" in (result.stdout + result.stderr)


def _x11_screen_size() -> str:
    result = run_cmd(["xdpyinfo"])
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("dimensions:"):
            return line.split()[1]
    return "1920x1080"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _signal_pid(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass


def _clear_state() -> None:
    try:
        os.remove(state_path())
    except OSError:
        pass
