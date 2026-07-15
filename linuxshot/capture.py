"""Screen capture backends.

Wayland has no single screenshot API, so the right tool depends on the
compositor: Spectacle on KDE, gnome-screenshot on GNOME, grim+slurp on
wlroots compositors (Hyprland, Sway, ...). X11 always goes through maim.
"""

import json
import os
import subprocess
import time
from datetime import datetime
from enum import Enum

from .config import Config
from .utils import DisplayServer, get_display_server, has_command, run_cmd


class CaptureMode(Enum):
    REGION = "region"
    FULLSCREEN = "fullscreen"
    WINDOW = "window"


class CaptureError(Exception):
    pass


class CaptureResult:
    def __init__(self, filepath: str, mode: CaptureMode):
        self.filepath = filepath
        self.mode = mode
        self.timestamp = datetime.now()
        self.filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0

    def __repr__(self) -> str:
        return f"CaptureResult({self.filepath!r}, mode={self.mode.value})"


def detect_wayland_backend() -> str:
    """Pick the capture tool for this compositor.

    Returns 'spectacle', 'gnome-screenshot', 'grim', or 'none'.
    """
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    if ("kde" in desktop or "plasma" in desktop) and has_command("spectacle"):
        return "spectacle"

    if any(de in desktop for de in ("gnome", "unity", "cinnamon")):
        if has_command("gnome-screenshot"):
            return "gnome-screenshot"

    if has_command("grim"):
        # grim exists on non-wlroots systems too; only trust it if the
        # compositor actually supports wlr-screencopy.
        if run_cmd(["grim", "-", "-t", "ppm"]).returncode == 0:
            return "grim"

    if has_command("spectacle"):
        return "spectacle"
    if has_command("gnome-screenshot"):
        return "gnome-screenshot"
    return "none"


class Capture:
    def __init__(self):
        self.display_server = get_display_server()
        self.config = Config.get()
        if self.display_server == DisplayServer.WAYLAND:
            self._wayland_backend = detect_wayland_backend()

    def capture(self, mode: CaptureMode,
                output_path: str | None = None) -> CaptureResult | None:
        """Take a screenshot. Returns None if the user cancelled,
        raises CaptureError if no backend could produce a file.

        *output_path* overrides the configured screenshots directory,
        for captures that shouldn't land there (OCR scratch files etc.).
        """
        delay = self.config["capture_delay"]
        if delay > 0:
            time.sleep(delay)

        output = output_path or self._output_path()

        if self.display_server == DisplayServer.WAYLAND:
            ok = self._wayland_capture(mode, output)
        elif self.display_server == DisplayServer.X11:
            ok = self._x11_capture(mode, output)
        else:
            raise CaptureError(
                "Could not detect display server. "
                "Set XDG_SESSION_TYPE to 'wayland' or 'x11'."
            )

        if not ok:
            return None
        if not os.path.exists(output):
            raise CaptureError(f"Screenshot file was not created: {output}")
        return CaptureResult(output, mode)

    def _output_path(self) -> str:
        pattern = self.config["filename_pattern"]
        ext = self.config["image_format"]
        filename = datetime.now().strftime(f"{pattern}.{ext}")
        return os.path.join(self.config.get_screenshot_dir(), filename)

    def _wayland_capture(self, mode: CaptureMode, output: str) -> bool:
        backend = self._wayland_backend
        if backend == "spectacle":
            return self._spectacle_capture(mode, output)
        if backend == "gnome-screenshot":
            return self._gnome_capture(mode, output)
        if backend == "grim":
            return self._grim_capture(mode, output)
        raise CaptureError(
            "No supported screenshot tool found.\n"
            "Install one of: spectacle (KDE), gnome-screenshot (GNOME), "
            "or grim+slurp (wlroots compositors like Hyprland/Sway)."
        )

    # -- Spectacle (KDE) -------------------------------------------------

    def _spectacle_capture(self, mode: CaptureMode, output: str) -> bool:
        if mode == CaptureMode.REGION:
            return self._spectacle_region(output)

        cmd = ["spectacle", "-b", "-n", "-o", output]
        cmd.append("-a" if mode == CaptureMode.WINDOW else "-f")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return False
        except FileNotFoundError:
            raise CaptureError("'spectacle' is required for KDE screenshot capture.") from None
        if result.returncode != 0 and not os.path.exists(output):
            return False
        return os.path.exists(output) and os.path.getsize(output) > 0

    def _spectacle_region(self, output: str) -> bool:
        # Region capture with -b/-o is unreliable on some Spectacle
        # releases, so fall back to clipboard mode and save the clipboard
        # contents if the direct path produced nothing.
        try:
            direct = subprocess.run(
                ["spectacle", "-r", "-b", "-n", "-o", output],
                capture_output=True, text=True, timeout=90,
            )
            if direct.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 0:
                return True
        except subprocess.TimeoutExpired:
            pass
        except FileNotFoundError:
            raise CaptureError("'spectacle' is required for KDE screenshot capture.") from None

        try:
            clip = subprocess.run(
                ["spectacle", "-r", "-c"],
                capture_output=True, text=True, timeout=120,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        if clip.returncode != 0:
            return False
        return self._save_clipboard_image(output)

    @staticmethod
    def _save_clipboard_image(output: str) -> bool:
        for cmd in (
            ["wl-paste", "--type", "image/png"],
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
        ):
            try:
                with open(output, "wb") as f:
                    result = subprocess.run(
                        cmd, stdout=f, stderr=subprocess.PIPE, timeout=10
                    )
                if result.returncode == 0 and os.path.getsize(output) > 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
        return False

    # -- gnome-screenshot ------------------------------------------------

    def _gnome_capture(self, mode: CaptureMode, output: str) -> bool:
        cmd = ["gnome-screenshot"]
        if mode == CaptureMode.REGION:
            cmd.append("-a")
        elif mode == CaptureMode.WINDOW:
            cmd.append("-w")
        cmd.extend(["-f", output])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return False
        except FileNotFoundError:
            raise CaptureError("'gnome-screenshot' is required for GNOME capture.") from None
        return result.returncode == 0 and os.path.exists(output)

    # -- grim + slurp (wlroots) --------------------------------------------

    def _grim_capture(self, mode: CaptureMode, output: str) -> bool:
        try:
            if mode == CaptureMode.REGION:
                return self._grim_region(output)
            if mode == CaptureMode.WINDOW:
                return self._grim_window(output)
            return run_cmd(["grim", output]).returncode == 0
        except FileNotFoundError:
            raise CaptureError("'grim' and 'slurp' are required for wlroots capture.") from None

    def _grim_region(self, output: str) -> bool:
        selection = run_cmd(["slurp"])
        region = selection.stdout.strip()
        if selection.returncode != 0 or not region:
            return False
        return run_cmd(["grim", "-g", region, output]).returncode == 0

    def _grim_window(self, output: str) -> bool:
        geometry = (
            self._hyprland_active_window_geometry()
            or self._sway_active_window_geometry()
        )
        if geometry:
            return run_cmd(["grim", "-g", geometry, output]).returncode == 0
        # No compositor IPC available; let the user pick the window as a region.
        return self._grim_region(output)

    @staticmethod
    def _hyprland_active_window_geometry() -> str | None:
        try:
            result = run_cmd(["hyprctl", "activewindow", "-j"])
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            x, y = data.get("at", [0, 0])
            w, h = data.get("size", [0, 0])
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            return None
        if w <= 0 or h <= 0:
            return None
        return f"{x},{y} {w}x{h}"

    @staticmethod
    def _sway_active_window_geometry() -> str | None:
        try:
            result = run_cmd(["swaymsg", "-t", "get_tree"])
            if result.returncode != 0:
                return None
            focused = _find_sway_focused(json.loads(result.stdout))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        if not focused:
            return None
        rect = focused.get("rect", {})
        w, h = rect.get("width", 0), rect.get("height", 0)
        if w <= 0 or h <= 0:
            return None
        return f"{rect.get('x', 0)},{rect.get('y', 0)} {w}x{h}"

    # -- X11 (maim + xdotool) ----------------------------------------------

    def _x11_capture(self, mode: CaptureMode, output: str) -> bool:
        try:
            if mode == CaptureMode.REGION:
                return run_cmd(["maim", "-s", output]).returncode == 0
            if mode == CaptureMode.WINDOW:
                return self._x11_window(output)
            return run_cmd(["maim", output]).returncode == 0
        except FileNotFoundError:
            raise CaptureError("'maim' and 'xdotool' are required for X11 capture.") from None

    def _x11_window(self, output: str) -> bool:
        active = run_cmd(["xdotool", "getactivewindow"])
        if active.returncode != 0:
            return run_cmd(["maim", "-s", output]).returncode == 0
        window_id = active.stdout.strip()
        return run_cmd(["maim", "-i", window_id, output]).returncode == 0


def _find_sway_focused(node: dict) -> dict | None:
    if node.get("focused"):
        return node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        found = _find_sway_focused(child)
        if found:
            return found
    return None
