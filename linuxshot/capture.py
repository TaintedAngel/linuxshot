"""Screen capture engine supporting Wayland (KDE, GNOME, wlroots) and X11."""

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
    """Raised when a capture operation fails."""
    pass


class CaptureResult:
    """Result of a capture operation."""

    def __init__(self, filepath: str, mode: CaptureMode):
        self.filepath = filepath
        self.mode = mode
        self.timestamp = datetime.now()
        self.filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0

    def __repr__(self) -> str:
        return f"CaptureResult({self.filepath!r}, mode={self.mode.value})"


def _detect_wayland_backend() -> str:
    """Detect which Wayland capture backend to use.

    Returns one of: 'spectacle', 'gnome-screenshot', 'grim', or 'none'.
    """
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    # KDE Plasma → Spectacle
    if "kde" in desktop or "plasma" in desktop:
        if has_command("spectacle"):
            return "spectacle"

    # GNOME → gnome-screenshot
    if "gnome" in desktop or "unity" in desktop or "cinnamon" in desktop:
        if has_command("gnome-screenshot"):
            return "gnome-screenshot"

    # wlroots compositors (Hyprland, Sway, etc.) → grim
    if has_command("grim"):
        # Test if grim actually works (compositor supports wlr-screencopy)
        test = run_cmd(["grim", "-", "-t", "ppm"])
        if test.returncode == 0:
            return "grim"

    # Fallback: try spectacle or gnome-screenshot even if DE wasn't detected
    if has_command("spectacle"):
        return "spectacle"
    if has_command("gnome-screenshot"):
        return "gnome-screenshot"

    return "none"


class Capture:
    """Handles screen capture on Wayland (KDE, GNOME, wlroots) and X11."""

    def __init__(self):
        self.display_server = get_display_server()
        self.config = Config.get()
        if self.display_server == DisplayServer.WAYLAND:
            self._wayland_backend = _detect_wayland_backend()

    def capture(self, mode: CaptureMode) -> CaptureResult | None:
        """Capture a screenshot using the specified mode.

        Returns CaptureResult on success, None if cancelled by user.
        Raises CaptureError on failure.
        """
        # Handle capture delay
        delay = self.config["capture_delay"]
        if delay > 0:
            time.sleep(delay)

        output_path = self._get_output_path()

        if self.display_server == DisplayServer.WAYLAND:
            success = self._wayland_capture(mode, output_path)
        elif self.display_server == DisplayServer.X11:
            success = self._x11_capture(mode, output_path)
        else:
            raise CaptureError(
                "Could not detect display server. "
                "Set XDG_SESSION_TYPE to 'wayland' or 'x11'."
            )

        if not success:
            return None  # User cancelled

        if not os.path.exists(output_path):
            raise CaptureError(f"Screenshot file was not created: {output_path}")

        return CaptureResult(output_path, mode)

    def _get_output_path(self) -> str:
        """Generate the output file path."""
        screenshot_dir = self.config.get_screenshot_dir()
        pattern = self.config["filename_pattern"]
        ext = self.config["image_format"]
        filename = datetime.now().strftime(f"{pattern}.{ext}")
        return os.path.join(screenshot_dir, filename)

    # ── Wayland capture (auto-detect backend) ────────────────────

    def _wayland_capture(self, mode: CaptureMode, output: str) -> bool:
        backend = self._wayland_backend
        if backend == "spectacle":
            return self._spectacle_capture(mode, output)
        elif backend == "gnome-screenshot":
            return self._gnome_capture(mode, output)
        elif backend == "grim":
            return self._grim_capture(mode, output)
        else:
            raise CaptureError(
                "No supported screenshot tool found.\n"
                "Install one of: spectacle (KDE), gnome-screenshot (GNOME), "
                "or grim+slurp (wlroots compositors like Hyprland/Sway)."
            )

    # ── Spectacle (KDE Plasma) ─────────────────────────────

    def _spectacle_capture(self, mode: CaptureMode, output: str) -> bool:
        """Capture using KDE Spectacle CLI."""
        # Region mode on some Spectacle/KDE versions is unreliable with -b/-o.
        # So we use a two-step fallback:
        # 1) Try direct file output.
        # 2) If that fails, use clipboard mode and save clipboard image.
        if mode == CaptureMode.REGION:
            try:
                direct = subprocess.run(
                    ["spectacle", "-r", "-b", "-n", "-o", output],
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                if direct.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 0:
                    return True
            except subprocess.TimeoutExpired:
                pass
            except FileNotFoundError:
                raise CaptureError("'spectacle' is required for KDE screenshot capture.")

            # Fallback path: copy region to clipboard, then persist clipboard image
            try:
                clip = subprocess.run(
                    ["spectacle", "-r", "-c"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if clip.returncode != 0:
                    return False
                return self._save_wayland_clipboard_image(output)
            except subprocess.TimeoutExpired:
                return False
            except FileNotFoundError:
                raise CaptureError("'spectacle' is required for KDE screenshot capture.")

        cmd = ["spectacle", "-b", "-n", "-o", output]
        match mode:
            case CaptureMode.FULLSCREEN:
                cmd.append("-f")
            case CaptureMode.WINDOW:
                cmd.append("-a")
            case _:
                cmd.append("-f")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0 and not os.path.exists(output):
                return False
            return os.path.exists(output) and os.path.getsize(output) > 0
        except subprocess.TimeoutExpired:
            return False
        except FileNotFoundError:
            raise CaptureError("'spectacle' is required for KDE screenshot capture.")

    def _save_wayland_clipboard_image(self, output: str) -> bool:
        """Persist clipboard image data to a PNG file."""
        try:
            with open(output, "wb") as f:
                result = subprocess.run(
                    ["wl-paste", "--type", "image/png"],
                    stdout=f,
                    stderr=subprocess.PIPE,
                    timeout=10,
                )
            if result.returncode == 0 and os.path.getsize(output) > 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        # X11 fallback
        try:
            with open(output, "wb") as f:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                    stdout=f,
                    stderr=subprocess.PIPE,
                    timeout=10,
                )
            return result.returncode == 0 and os.path.getsize(output) > 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    # ── GNOME Screenshot ───────────────────────────────────

    def _gnome_capture(self, mode: CaptureMode, output: str) -> bool:
        """Capture using gnome-screenshot."""
        cmd = ["gnome-screenshot"]
        match mode:
            case CaptureMode.REGION:
                cmd.append("-a")
            case CaptureMode.FULLSCREEN:
                pass  # Default is fullscreen
            case CaptureMode.WINDOW:
                cmd.append("-w")
        cmd.extend(["-f", output])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0 and os.path.exists(output)
        except subprocess.TimeoutExpired:
            return False
        except FileNotFoundError:
            raise CaptureError("'gnome-screenshot' is required for GNOME screenshot capture.")

    # ── grim + slurp (wlroots: Hyprland, Sway, etc.) ────────────

    def _grim_capture(self, mode: CaptureMode, output: str) -> bool:
        match mode:
            case CaptureMode.REGION:
                return self._grim_region(output)
            case CaptureMode.FULLSCREEN:
                return self._grim_fullscreen(output)
            case CaptureMode.WINDOW:
                return self._grim_window(output)

    def _grim_region(self, output: str) -> bool:
        try:
            result = run_cmd(["slurp"])
            if result.returncode != 0:
                return False
            region = result.stdout.strip()
            if not region:
                return False
            result = run_cmd(["grim", "-g", region, output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError("'grim' and 'slurp' are required for wlroots region capture.")

    def _grim_fullscreen(self, output: str) -> bool:
        try:
            result = run_cmd(["grim", output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError("'grim' is required for wlroots fullscreen capture.")

    def _grim_window(self, output: str) -> bool:
        geometry = self._hyprland_active_window_geometry()
        if not geometry:
            geometry = self._sway_active_window_geometry()
        if geometry:
            try:
                result = run_cmd(["grim", "-g", geometry, output])
                return result.returncode == 0
            except FileNotFoundError:
                raise CaptureError("'grim' is required for wlroots capture.")
        return self._grim_region(output)

    def _hyprland_active_window_geometry(self) -> str | None:
        try:
            result = run_cmd(["hyprctl", "activewindow", "-j"])
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            at = data.get("at", [0, 0])
            size = data.get("size", [0, 0])
            if size[0] <= 0 or size[1] <= 0:
                return None
            return f"{at[0]},{at[1]} {size[0]}x{size[1]}"
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    def _sway_active_window_geometry(self) -> str | None:
        try:
            result = run_cmd(["swaymsg", "-t", "get_tree"])
            if result.returncode != 0:
                return None
            tree = json.loads(result.stdout)
            focused = self._find_sway_focused(tree)
            if not focused:
                return None
            rect = focused.get("rect", {})
            x, y = rect.get("x", 0), rect.get("y", 0)
            w, h = rect.get("width", 0), rect.get("height", 0)
            if w <= 0 or h <= 0:
                return None
            return f"{x},{y} {w}x{h}"
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    @staticmethod
    def _find_sway_focused(node: dict) -> dict | None:
        if node.get("focused"):
            return node
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            result = Capture._find_sway_focused(child)
            if result:
                return result
        return None

    # ── X11 capture (maim + xdotool) ──────────────────────────────

    def _x11_capture(self, mode: CaptureMode, output: str) -> bool:
        match mode:
            case CaptureMode.REGION:
                return self._x11_region(output)
            case CaptureMode.FULLSCREEN:
                return self._x11_fullscreen(output)
            case CaptureMode.WINDOW:
                return self._x11_window(output)

    def _x11_region(self, output: str) -> bool:
        try:
            result = run_cmd(["maim", "-s", output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError("'maim' is required for X11 region capture.")

    def _x11_fullscreen(self, output: str) -> bool:
        try:
            result = run_cmd(["maim", output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError("'maim' is required for X11 fullscreen capture.")

    def _x11_window(self, output: str) -> bool:
        try:
            result = run_cmd(["xdotool", "getactivewindow"])
            if result.returncode != 0:
                return self._x11_region(output)
            window_id = result.stdout.strip()
            result = run_cmd(["maim", "-i", window_id, output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError("'maim' and 'xdotool' are required for X11 window capture.")
