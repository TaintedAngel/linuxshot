import json
import subprocess

import pytest

import linuxshot.capture as capture_mod
from linuxshot.capture import Capture, CaptureMode, detect_wayland_backend
from linuxshot.config import Config


def fake_run(stdout: str = "", returncode: int = 0):
    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")
    return runner


@pytest.fixture
def wayland_session(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")


def test_output_path_uses_pattern_and_format(wayland_session, monkeypatch):
    monkeypatch.setattr(capture_mod, "detect_wayland_backend", lambda: "grim")
    config = Config.get()
    config["image_format"] = "webp"
    config["filename_pattern"] = "shot_%Y"

    path = Capture()._output_path()
    assert path.endswith(".webp")
    assert "shot_" in path


def test_detect_backend_prefers_spectacle_on_kde(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setattr(capture_mod, "has_command", lambda cmd: cmd == "spectacle")
    assert detect_wayland_backend() == "spectacle"


def test_detect_backend_grim_only_when_screencopy_works(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
    monkeypatch.setattr(capture_mod, "has_command", lambda cmd: cmd == "grim")

    monkeypatch.setattr(capture_mod, "run_cmd", fake_run(returncode=0))
    assert detect_wayland_backend() == "grim"

    monkeypatch.setattr(capture_mod, "run_cmd", fake_run(returncode=1))
    assert detect_wayland_backend() == "none"


def test_detect_backend_none_without_tools(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "")
    monkeypatch.setattr(capture_mod, "has_command", lambda cmd: False)
    assert detect_wayland_backend() == "none"


def test_hyprland_geometry(monkeypatch):
    payload = json.dumps({"at": [10, 20], "size": [800, 600]})
    monkeypatch.setattr(capture_mod, "run_cmd", fake_run(stdout=payload))
    assert Capture._hyprland_active_window_geometry() == "10,20 800x600"


def test_hyprland_geometry_rejects_empty_window(monkeypatch):
    payload = json.dumps({"at": [0, 0], "size": [0, 0]})
    monkeypatch.setattr(capture_mod, "run_cmd", fake_run(stdout=payload))
    assert Capture._hyprland_active_window_geometry() is None


def test_sway_geometry_finds_focused_node(monkeypatch):
    tree = json.dumps({
        "focused": False,
        "nodes": [
            {"focused": False, "nodes": [], "floating_nodes": []},
            {
                "focused": True,
                "rect": {"x": 5, "y": 6, "width": 100, "height": 50},
                "nodes": [], "floating_nodes": [],
            },
        ],
        "floating_nodes": [],
    })
    monkeypatch.setattr(capture_mod, "run_cmd", fake_run(stdout=tree))
    assert Capture._sway_active_window_geometry() == "5,6 100x50"


def test_grim_region_cancelled_by_user(wayland_session, monkeypatch):
    monkeypatch.setattr(capture_mod, "detect_wayland_backend", lambda: "grim")
    engine = Capture()
    # slurp exits 1 when the user presses Escape
    monkeypatch.setattr(capture_mod, "run_cmd", fake_run(returncode=1))
    assert engine._grim_region("/tmp/out.png") is False


def test_capture_returns_none_on_cancel(wayland_session, monkeypatch, tmp_path):
    monkeypatch.setattr(capture_mod, "detect_wayland_backend", lambda: "grim")
    engine = Capture()
    monkeypatch.setattr(engine, "_wayland_capture", lambda mode, output: False)
    assert engine.capture(CaptureMode.REGION) is None
