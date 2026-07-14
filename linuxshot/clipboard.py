"""Clipboard access through wl-copy (Wayland) or xclip (X11)."""

import subprocess

from .utils import DisplayServer, get_display_server


def copy_text(text: str) -> bool:
    if get_display_server() == DisplayServer.WAYLAND:
        cmd = ["wl-copy", "--", text]
        stdin = None
    else:
        cmd = ["xclip", "-selection", "clipboard"]
        stdin = text.encode()
    return _run(cmd, stdin)


def copy_image(filepath: str) -> bool:
    try:
        with open(filepath, "rb") as f:
            data = f.read()
    except OSError:
        return False

    if get_display_server() == DisplayServer.WAYLAND:
        cmd = ["wl-copy", "--type", "image/png"]
    else:
        cmd = ["xclip", "-selection", "clipboard", "-t", "image/png"]
    return _run(cmd, data, timeout=10)


def _run(cmd: list[str], stdin: bytes | None, timeout: int = 5) -> bool:
    try:
        result = subprocess.run(
            cmd,
            input=stdin,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
