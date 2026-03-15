"""Screen capture engine supporting Wayland and X11."""

import json
import os
import subprocess
import time
from datetime import datetime
from enum import Enum

from .config import Config
from .utils import DisplayServer, get_display_server, run_cmd


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


class Capture:
    """Handles screen capture on both Wayland and X11."""

    def __init__(self):
        self.display_server = get_display_server()
        self.config = Config.get()

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
            return None  # User cancelled (e.g. pressed Escape during region select)

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

    # ── Wayland capture (grim + slurp) ─────────────────────────────────

    def _wayland_capture(self, mode: CaptureMode, output: str) -> bool:
        match mode:
            case CaptureMode.REGION:
                return self._wayland_region(output)
            case CaptureMode.FULLSCREEN:
                return self._wayland_fullscreen(output)
            case CaptureMode.WINDOW:
                return self._wayland_window(output)

    def _wayland_region(self, output: str) -> bool:
        """Capture a user-selected region using slurp + grim."""
        try:
            # slurp lets the user select a region
            result = run_cmd(["slurp"])
            if result.returncode != 0:
                return False  # User cancelled
            region = result.stdout.strip()
            if not region:
                return False

            result = run_cmd(["grim", "-g", region, output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError("'grim' and 'slurp' are required for Wayland region capture.")

    def _wayland_fullscreen(self, output: str) -> bool:
        """Capture the full screen using grim."""
        try:
            result = run_cmd(["grim", output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError("'grim' is required for Wayland fullscreen capture.")

    def _wayland_window(self, output: str) -> bool:
        """Capture the active window on Wayland.

        Tries compositor-specific methods, then falls back to region select.
        """
        # Try Hyprland
        geometry = self._hyprland_active_window_geometry()
        if geometry:
            try:
                result = run_cmd(["grim", "-g", geometry, output])
                return result.returncode == 0
            except FileNotFoundError:
                raise CaptureError("'grim' is required for Wayland capture.")

        # Try Sway
        geometry = self._sway_active_window_geometry()
        if geometry:
            try:
                result = run_cmd(["grim", "-g", geometry, output])
                return result.returncode == 0
            except FileNotFoundError:
                raise CaptureError("'grim' is required for Wayland capture.")

        # Try KDE/GNOME via slurp with window hints
        try:
            # slurp can select visible windows when compositor supports it
            result = run_cmd(["slurp"])
            if result.returncode != 0:
                return False
            region = result.stdout.strip()
            if not region:
                return False
            result = run_cmd(["grim", "-g", region, output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError("'grim' and 'slurp' are required for Wayland capture.")

    def _hyprland_active_window_geometry(self) -> str | None:
        """Get active window geometry from Hyprland."""
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
        """Get active window geometry from Sway."""
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
        """Recursively find the focused node in a Sway tree."""
        if node.get("focused"):
            return node
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            result = Capture._find_sway_focused(child)
            if result:
                return result
        return None

    # ── X11 capture (maim + xdotool) ──────────────────────────────────

    def _x11_capture(self, mode: CaptureMode, output: str) -> bool:
        match mode:
            case CaptureMode.REGION:
                return self._x11_region(output)
            case CaptureMode.FULLSCREEN:
                return self._x11_fullscreen(output)
            case CaptureMode.WINDOW:
                return self._x11_window(output)

    def _x11_region(self, output: str) -> bool:
        """Capture a user-selected region using maim -s."""
        try:
            result = run_cmd(["maim", "-s", output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError("'maim' is required for X11 region capture.")

    def _x11_fullscreen(self, output: str) -> bool:
        """Capture the full screen using maim."""
        try:
            result = run_cmd(["maim", output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError("'maim' is required for X11 fullscreen capture.")

    def _x11_window(self, output: str) -> bool:
        """Capture the active window using maim + xdotool."""
        try:
            # Get active window ID
            result = run_cmd(["xdotool", "getactivewindow"])
            if result.returncode != 0:
                # Fallback to region select
                return self._x11_region(output)
            window_id = result.stdout.strip()

            result = run_cmd(["maim", "-i", window_id, output])
            return result.returncode == 0
        except FileNotFoundError:
            raise CaptureError(
                "'maim' and 'xdotool' are required for X11 window capture."
            )
