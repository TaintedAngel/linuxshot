"""Configuration storage.

Settings live in a single JSON file under the XDG config dir. Unknown keys
found on disk are preserved so downgrades don't lose data, but lookups fall
back to DEFAULTS for anything missing.
"""

import json
import os
import sys
from typing import Any

from .utils import get_config_dir, get_screenshots_dir

DEFAULTS: dict[str, Any] = {
    # General
    "screenshot_dir": "",  # empty means ~/Pictures/LinuxShot
    "filename_pattern": "LinuxShot_%Y-%m-%d_%H-%M-%S",
    "image_format": "png",  # png, jpg, webp
    "jpg_quality": 95,
    "open_after_capture": False,
    "open_editor_after_capture": True,
    "copy_image_to_clipboard": True,
    "play_sound": False,

    # After-capture actions
    "auto_upload": False,
    "copy_url_to_clipboard": True,
    "show_notification": True,
    "save_to_disk": True,

    # Upload
    "upload_service": "imgbb",  # imgbb, imgur, catbox, 0x0, custom
    "imgbb_api_key": "",
    "imgur_client_id": "",
    "catbox_userhash": "",  # optional; enables deletion on catbox
    "custom_uploader": {},  # see linuxshot.upload.CustomUploader

    # Tools
    "ocr_language": "",  # tesseract -l value; empty uses its default

    # Capture
    "capture_delay": 0,
    "include_cursor": False,
    "region_border_color": "#ff4444",
    "region_border_width": 2,

    # Shortcuts (KDE key strings)
    "shortcut_region": "Print",
    "shortcut_fullscreen": "Ctrl+Print",
    "shortcut_window": "Alt+Print",
    "override_spectacle": True,

    # Tray
    "start_in_tray": True,
    "minimize_to_tray": True,
    "show_tray_icon": True,

    # History
    "save_history": True,
    "max_history_entries": 1000,
}

CONFIG_FILE = "config.json"


class Config:
    _instance: "Config | None" = None

    def __init__(self):
        self._path = os.path.join(get_config_dir(), CONFIG_FILE)
        self._data: dict[str, Any] = {}
        self.load()

    @classmethod
    def get(cls) -> "Config":
        if cls._instance is None:
            cls._instance = Config()
        return cls._instance

    def load(self) -> None:
        self._data = DEFAULTS.copy()
        try:
            with open(self._path) as f:
                self._data.update(json.load(f))
        except FileNotFoundError:
            pass
        except (json.JSONDecodeError, OSError) as e:
            print(f"warning: could not read {self._path}: {e}", file=sys.stderr)

    def save(self) -> None:
        # Write-then-rename so a crash can't truncate the config, and keep it
        # private since it holds the upload API key.
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(self._data, f, indent=2)
                f.write("\n")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        except OSError as e:
            print(f"error: could not save {self._path}: {e}", file=sys.stderr)

    def reset(self) -> None:
        self._data = DEFAULTS.copy()
        self.save()

    def is_known_key(self, key: str) -> bool:
        return key in DEFAULTS

    def get_screenshot_dir(self) -> str:
        custom = self._data.get("screenshot_dir", "")
        if custom:
            custom = os.path.expanduser(custom)
            os.makedirs(custom, exist_ok=True)
            return custom
        return get_screenshots_dir()

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    @property
    def path(self) -> str:
        return self._path

    @property
    def data(self) -> dict[str, Any]:
        return self._data.copy()
