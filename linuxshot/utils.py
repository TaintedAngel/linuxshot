"""Shared helpers: display server detection, XDG paths, subprocess wrappers."""

import os
import shutil
import subprocess
from enum import Enum


class DisplayServer(Enum):
    WAYLAND = "wayland"
    X11 = "x11"
    UNKNOWN = "unknown"


def get_display_server() -> DisplayServer:
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session in ("wayland", "x11"):
        return DisplayServer(session)
    if os.environ.get("WAYLAND_DISPLAY"):
        return DisplayServer.WAYLAND
    if os.environ.get("DISPLAY"):
        return DisplayServer.X11
    return DisplayServer.UNKNOWN


def xdg_user_dir(name: str, fallback: str) -> str:
    """Look up an XDG user directory (PICTURES, DOWNLOAD, ...) from
    user-dirs.dirs. The values there are shell-quoted and may reference
    $HOME, so expand that ourselves rather than shelling out.
    """
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    prefix = f"XDG_{name}_DIR="
    try:
        with open(os.path.join(config_home, "user-dirs.dirs")) as f:
            for line in f:
                line = line.strip()
                if line.startswith(prefix):
                    value = line[len(prefix):].strip('"')
                    return value.replace("$HOME", os.path.expanduser("~"))
    except OSError:
        pass
    return fallback


def get_screenshots_dir() -> str:
    pictures = xdg_user_dir("PICTURES", os.path.expanduser("~/Pictures"))
    path = os.path.join(pictures, "LinuxShot")
    os.makedirs(path, exist_ok=True)
    return path


def get_config_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    path = os.path.join(base, "linuxshot")
    os.makedirs(path, exist_ok=True)
    return path


def get_data_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    path = os.path.join(base, "linuxshot")
    os.makedirs(path, exist_ok=True)
    return path


def has_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run_cmd(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kwargs)


def check_dependencies() -> dict[str, bool]:
    """Availability of the external tools we might shell out to."""
    tools = (
        "spectacle", "gnome-screenshot", "grim", "slurp", "wl-copy", "wl-paste",
        "maim", "xdotool", "xclip",
        "notify-send",
        "tesseract", "hyprpicker", "ffmpeg", "wf-recorder", "slop",
    )
    return {tool: has_command(tool) for tool in tools}
