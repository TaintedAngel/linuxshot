"""Clipboard integration for Wayland and X11."""

import subprocess

from .utils import DisplayServer, get_display_server, run_cmd


def copy_text(text: str) -> bool:
    """Copy text to the clipboard."""
    ds = get_display_server()
    try:
        if ds == DisplayServer.WAYLAND:
            proc = subprocess.Popen(
                ["wl-copy", "--", text],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.wait(timeout=5)
            return proc.returncode == 0
        else:
            proc = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.communicate(input=text.encode(), timeout=5)
            return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def copy_image(filepath: str) -> bool:
    """Copy an image file to the clipboard."""
    ds = get_display_server()
    try:
        if ds == DisplayServer.WAYLAND:
            # wl-copy can read from a file with --type
            with open(filepath, "rb") as f:
                proc = subprocess.Popen(
                    ["wl-copy", "--type", "image/png"],
                    stdin=f,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                proc.wait(timeout=10)
                return proc.returncode == 0
        else:
            with open(filepath, "rb") as f:
                proc = subprocess.Popen(
                    ["xclip", "-selection", "clipboard", "-t", "image/png"],
                    stdin=f,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                proc.wait(timeout=10)
                return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
