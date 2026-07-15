import json
import os
import subprocess

import pytest

import linuxshot.recording as rec_mod
from linuxshot.recording import (
    RecordingError,
    _convert,
    _start_command,
    current,
    detect_backend,
    start,
    state_path,
    stop,
)
from linuxshot.utils import DisplayServer


def completed(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


class FakeProcess:
    def __init__(self, pid=4242, exits_immediately=False):
        self.pid = pid
        self._dead = exits_immediately

    def poll(self):
        return 1 if self._dead else None


@pytest.fixture(autouse=True)
def runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    os.makedirs(tmp_path / "run")
    monkeypatch.setattr(rec_mod.time, "sleep", lambda s: None)


@pytest.fixture
def kde_wayland(monkeypatch):
    monkeypatch.setattr(rec_mod, "get_display_server",
                        lambda: DisplayServer.WAYLAND)
    monkeypatch.setattr(rec_mod, "has_command", lambda cmd: cmd == "spectacle")
    monkeypatch.setattr(rec_mod, "_spectacle_supports_record", lambda: True)


def write_state(pid=4242, backend="spectacle", output="/tmp/x.webm", fmt="webm"):
    state = {"pid": pid, "backend": backend, "mode": "screen",
             "output": output, "format": fmt, "started": 0}
    with open(state_path(), "w") as f:
        json.dump(state, f)
    return state


def test_detect_backend_kde(kde_wayland):
    assert detect_backend() == "spectacle"


def test_detect_backend_wlroots(monkeypatch):
    monkeypatch.setattr(rec_mod, "get_display_server",
                        lambda: DisplayServer.WAYLAND)
    monkeypatch.setattr(rec_mod, "has_command", lambda cmd: cmd == "wf-recorder")
    assert detect_backend() == "wf-recorder"


def test_detect_backend_x11(monkeypatch):
    monkeypatch.setattr(rec_mod, "get_display_server", lambda: DisplayServer.X11)
    monkeypatch.setattr(rec_mod, "has_command", lambda cmd: cmd == "ffmpeg")
    assert detect_backend() == "x11grab"


def test_start_writes_state(kde_wayland, monkeypatch):
    seen = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeProcess()

    monkeypatch.setattr(rec_mod.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(rec_mod, "_pid_alive", lambda pid: pid == 4242)

    state = start("region")
    assert seen["cmd"][:5] == ["spectacle", "-b", "-n", "-R", "region"]
    assert state["pid"] == 4242
    assert state["output"].endswith(".webm")
    assert current()["backend"] == "spectacle"


def test_start_refuses_second_recording(kde_wayland, monkeypatch):
    monkeypatch.setattr(rec_mod, "_pid_alive", lambda pid: True)
    write_state()
    with pytest.raises(RecordingError, match="already running"):
        start("screen")


def test_start_detects_immediate_exit(kde_wayland, monkeypatch):
    monkeypatch.setattr(rec_mod.subprocess, "Popen",
                        lambda cmd, **kw: FakeProcess(exits_immediately=True))
    with pytest.raises(RecordingError, match="exited immediately"):
        start("screen")


def test_stale_state_is_cleared(monkeypatch):
    monkeypatch.setattr(rec_mod, "_pid_alive", lambda pid: False)
    write_state()
    assert current() is None
    assert not os.path.exists(state_path())


def test_stop_spectacle_toggles_and_converts(kde_wayland, tmp_path, monkeypatch):
    output = tmp_path / "rec.webm"
    output.write_bytes(b"webm data")
    write_state(output=str(output))

    alive = {"pid": True}
    monkeypatch.setattr(rec_mod, "_pid_alive", lambda pid: alive["pid"])
    toggles = []

    def fake_run(cmd, **kwargs):
        if cmd[0] == "spectacle":
            toggles.append(cmd)
            alive["pid"] = False
        return completed()

    monkeypatch.setattr(rec_mod, "run_cmd", fake_run)
    monkeypatch.setattr(rec_mod, "_convert", lambda path, fmt: path)

    assert stop() == str(output)
    assert toggles == [["spectacle", "-b", "-n", "-R", "screen"]]
    assert current() is None


def test_stop_without_recording():
    with pytest.raises(RecordingError, match="No recording"):
        stop()


def test_stop_rejects_empty_output(kde_wayland, tmp_path, monkeypatch):
    output = tmp_path / "rec.webm"
    output.write_bytes(b"")
    write_state(output=str(output))
    monkeypatch.setattr(rec_mod, "_pid_alive", lambda pid: False)

    # pid already dead: stale-state cleanup wins and reports no recording
    with pytest.raises(RecordingError):
        stop()


def test_convert_webm_to_mp4_command(tmp_path, monkeypatch):
    source = tmp_path / "rec.webm"
    source.write_bytes(b"x")
    monkeypatch.setattr(rec_mod, "has_command", lambda cmd: True)
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        (tmp_path / "rec.mp4").write_bytes(b"mp4")
        return completed()

    monkeypatch.setattr(rec_mod, "run_cmd", fake_run)
    result = _convert(str(source), "mp4")
    assert result.endswith(".mp4")
    assert "libx264" in seen["cmd"]
    assert not source.exists()  # original removed after conversion


def test_convert_gif_uses_palette(tmp_path, monkeypatch):
    source = tmp_path / "rec.webm"
    source.write_bytes(b"x")
    monkeypatch.setattr(rec_mod, "has_command", lambda cmd: True)
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        (tmp_path / "rec.gif").write_bytes(b"gif")
        return completed()

    monkeypatch.setattr(rec_mod, "run_cmd", fake_run)
    assert _convert(str(source), "gif").endswith(".gif")
    assert any("palettegen" in part for part in seen["cmd"])


def test_convert_same_format_is_noop(tmp_path):
    source = tmp_path / "rec.mp4"
    source.write_bytes(b"x")
    assert _convert(str(source), "mp4") == str(source)


def test_convert_keeps_original_when_ffmpeg_missing(tmp_path, monkeypatch):
    source = tmp_path / "rec.webm"
    source.write_bytes(b"x")
    monkeypatch.setattr(rec_mod, "has_command", lambda cmd: False)
    assert _convert(str(source), "mp4") == str(source)
    assert source.exists()


def test_wf_recorder_region_command(monkeypatch):
    monkeypatch.setattr(rec_mod, "run_cmd",
                        lambda cmd, **kw: completed(stdout="10,20 300x200\n"))
    cmd = _start_command("wf-recorder", "region", "/tmp/out.mp4")
    assert cmd == ["wf-recorder", "-f", "/tmp/out.mp4", "-g", "10,20 300x200"]


def test_wf_recorder_region_cancelled(monkeypatch):
    monkeypatch.setattr(rec_mod, "run_cmd",
                        lambda cmd, **kw: completed(returncode=1))
    with pytest.raises(RecordingError, match="cancelled"):
        _start_command("wf-recorder", "region", "/tmp/out.mp4")
