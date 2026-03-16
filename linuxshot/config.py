"""Configuration management for LinuxShot."""

import json
import os
from typing import Any

from .utils import get_config_dir, get_screenshots_dir

CONFIG_FILE = "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    # General
    "screenshot_dir": "",  # Empty = auto-detect ~/Pictures/LinuxShot
    "filename_pattern": "LinuxShot_%Y-%m-%d_%H-%M-%S",
    "image_format": "png",  # png, jpg, webp
    "jpg_quality": 95,
    "open_after_capture": False,
    "copy_image_to_clipboard": True,
    "play_sound": False,

    # After-capture actions
    "auto_upload": False,
    "copy_url_to_clipboard": True,
    "show_notification": True,
    "save_to_disk": True,

    # Upload
    "upload_service": "catbox",  # catbox, 0x0, imgur
    "imgur_client_id": "",  # Only needed for imgur: https://api.imgur.com/oauth2/addclient
    "imgur_client_secret": "",
    "imgur_anonymous": True,

    # Capture
    "capture_delay": 0,  # Seconds to wait before capturing
    "include_cursor": False,
    "region_border_color": "#ff4444",
    "region_border_width": 2,

    # Shortcuts (KDE key names - change via Settings or linuxshot config --set)
    "shortcut_region": "Print",               # ShareX-style PrtSc bindings
    "shortcut_fullscreen": "Ctrl+Print",
    "shortcut_window": "Alt+Print",
    "override_spectacle": True,  # Replaces Spectacle's PrtSc on KDE

    # Tray
    "start_in_tray": True,
    "minimize_to_tray": True,
    "show_tray_icon": True,

    # History
    "save_history": True,
    "max_history_entries": 1000,
}


class Config:
    """Manages LinuxShot configuration."""

    _instance: "Config | None" = None

    def __init__(self):
        self._config_dir = get_config_dir()
        self._config_path = os.path.join(self._config_dir, CONFIG_FILE)
        self._data: dict[str, Any] = {}
        self.load()

    @classmethod
    def get(cls) -> "Config":
        """Get the singleton config instance."""
        if cls._instance is None:
            cls._instance = Config()
        return cls._instance

    def load(self) -> None:
        """Load config from disk, merging with defaults."""
        self._data = DEFAULT_CONFIG.copy()
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r") as f:
                    user_config = json.load(f)
                self._data.update(user_config)
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: Failed to load config: {e}")

    def save(self) -> None:
        """Save current config to disk."""
        try:
            with open(self._config_path, "w") as f:
                json.dump(self._data, f, indent=4)
        except OSError as e:
            print(f"Error: Failed to save config: {e}")

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key, DEFAULT_CONFIG.get(key))

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get_screenshot_dir(self) -> str:
        """Get the configured screenshot directory."""
        custom = self._data.get("screenshot_dir", "")
        if custom:
            os.makedirs(custom, exist_ok=True)
            return custom
        return get_screenshots_dir()

    def reset(self) -> None:
        """Reset to default configuration."""
        self._data = DEFAULT_CONFIG.copy()
        self.save()

    @property
    def path(self) -> str:
        return self._config_path

    @property
    def data(self) -> dict[str, Any]:
        return self._data.copy()
