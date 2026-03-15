"""Utility functions for LinuxShot."""

import os
import shutil
import subprocess
from datetime import datetime
from enum import Enum


class DisplayServer(Enum):
    WAYLAND = "wayland"
    X11 = "x11"
    UNKNOWN = "unknown"


def get_display_server() -> DisplayServer:
    """Detect whether the session is running Wayland or X11."""
    xdg_session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if xdg_session == "wayland":
        return DisplayServer.WAYLAND
    if xdg_session == "x11":
        return DisplayServer.X11

    # Fallback: check WAYLAND_DISPLAY
    if os.environ.get("WAYLAND_DISPLAY"):
        return DisplayServer.WAYLAND

    # Fallback: check DISPLAY (X11)
    if os.environ.get("DISPLAY"):
        return DisplayServer.X11

    return DisplayServer.UNKNOWN


def get_timestamp_filename(ext: str = "png") -> str:
    """Generate a ShareX-style timestamped filename."""
    now = datetime.now()
    return now.strftime(f"LinuxShot_%Y-%m-%d_%H-%M-%S.{ext}")


def get_screenshots_dir() -> str:
    """Get the default screenshots directory, creating it if needed."""
    pictures = os.environ.get(
        "XDG_PICTURES_DIR",
        os.path.join(os.path.expanduser("~"), "Pictures"),
    )
    screenshots_dir = os.path.join(pictures, "LinuxShot")
    os.makedirs(screenshots_dir, exist_ok=True)
    return screenshots_dir


def get_config_dir() -> str:
    """Get the config directory, creating it if needed."""
    config_dir = os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config")),
        "linuxshot",
    )
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def get_data_dir() -> str:
    """Get the data directory, creating it if needed."""
    data_dir = os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share")),
        "linuxshot",
    )
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def has_command(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    return shutil.which(cmd) is not None


def check_dependencies() -> dict[str, bool]:
    """Check which capture/clipboard tools are available."""
    return {
        # Wayland
        "spectacle": has_command("spectacle"),
        "gnome-screenshot": has_command("gnome-screenshot"),
        "grim": has_command("grim"),
        "slurp": has_command("slurp"),
        "wl-copy": has_command("wl-copy"),
        "wl-paste": has_command("wl-paste"),
        # X11
        "maim": has_command("maim"),
        "xdotool": has_command("xdotool"),
        "xclip": has_command("xclip"),
        # Common
        "notify-send": has_command("notify-send"),
    }


def run_cmd(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess with common defaults."""
    return subprocess.run(args, capture_output=True, text=True, **kwargs)
