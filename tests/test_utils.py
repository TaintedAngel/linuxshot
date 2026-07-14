import os

from linuxshot.utils import (
    DisplayServer,
    get_display_server,
    get_screenshots_dir,
    xdg_user_dir,
)


def clear_display_env(monkeypatch):
    for var in ("XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY"):
        monkeypatch.delenv(var, raising=False)


def test_display_server_from_session_type(monkeypatch):
    clear_display_env(monkeypatch)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert get_display_server() == DisplayServer.WAYLAND
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert get_display_server() == DisplayServer.X11


def test_display_server_fallbacks(monkeypatch):
    clear_display_env(monkeypatch)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert get_display_server() == DisplayServer.WAYLAND

    clear_display_env(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":0")
    assert get_display_server() == DisplayServer.X11

    clear_display_env(monkeypatch)
    assert get_display_server() == DisplayServer.UNKNOWN


def test_xdg_user_dir_parses_user_dirs_file(tmp_path, monkeypatch):
    config_home = os.environ["XDG_CONFIG_HOME"]
    os.makedirs(config_home, exist_ok=True)
    with open(os.path.join(config_home, "user-dirs.dirs"), "w") as f:
        f.write('# comment\nXDG_PICTURES_DIR="$HOME/Media/Pics"\n')

    home = os.path.expanduser("~")
    assert xdg_user_dir("PICTURES", "/fallback") == f"{home}/Media/Pics"


def test_xdg_user_dir_fallback_when_missing():
    assert xdg_user_dir("PICTURES", "/fallback") == "/fallback"


def test_screenshots_dir_created():
    path = get_screenshots_dir()
    assert path.endswith("LinuxShot")
    assert os.path.isdir(path)
