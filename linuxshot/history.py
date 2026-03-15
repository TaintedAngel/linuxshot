"""Capture history management for LinuxShot."""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .config import Config
from .utils import get_data_dir


@dataclass
class HistoryEntry:
    """A single capture history entry."""
    filepath: str
    timestamp: str
    mode: str  # region, fullscreen, window
    filesize: int = 0
    uploaded: bool = False
    upload_url: str = ""
    delete_hash: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        return cls(
            filepath=data.get("filepath", ""),
            timestamp=data.get("timestamp", ""),
            mode=data.get("mode", ""),
            filesize=data.get("filesize", 0),
            uploaded=data.get("uploaded", False),
            upload_url=data.get("upload_url", ""),
            delete_hash=data.get("delete_hash", ""),
        )


class History:
    """Manages the capture history log."""

    HISTORY_FILE = "history.json"

    def __init__(self):
        self._data_dir = get_data_dir()
        self._history_path = os.path.join(self._data_dir, self.HISTORY_FILE)
        self._entries: list[HistoryEntry] = []
        self.load()

    def load(self) -> None:
        """Load history from disk."""
        if not os.path.exists(self._history_path):
            self._entries = []
            return
        try:
            with open(self._history_path, "r") as f:
                raw = json.load(f)
            self._entries = [HistoryEntry.from_dict(e) for e in raw]
        except (json.JSONDecodeError, OSError):
            self._entries = []

    def save(self) -> None:
        """Save history to disk."""
        config = Config.get()
        max_entries = config["max_history_entries"]
        # Trim to max entries
        if len(self._entries) > max_entries:
            self._entries = self._entries[-max_entries:]
        try:
            with open(self._history_path, "w") as f:
                json.dump([asdict(e) for e in self._entries], f, indent=2)
        except OSError as e:
            print(f"Warning: Failed to save history: {e}")

    def add(
        self,
        filepath: str,
        mode: str,
        filesize: int = 0,
        uploaded: bool = False,
        upload_url: str = "",
        delete_hash: str = "",
    ) -> HistoryEntry:
        """Add a new entry to history."""
        entry = HistoryEntry(
            filepath=filepath,
            timestamp=datetime.now().isoformat(),
            mode=mode,
            filesize=filesize,
            uploaded=uploaded,
            upload_url=upload_url,
            delete_hash=delete_hash,
        )
        self._entries.append(entry)
        self.save()
        return entry

    def update_upload(self, filepath: str, url: str, delete_hash: str = "") -> None:
        """Update an existing entry with upload info."""
        for entry in reversed(self._entries):
            if entry.filepath == filepath:
                entry.uploaded = True
                entry.upload_url = url
                entry.delete_hash = delete_hash
                self.save()
                return

    def get_entries(self, limit: int = 0) -> list[HistoryEntry]:
        """Get history entries, newest first."""
        entries = list(reversed(self._entries))
        if limit > 0:
            return entries[:limit]
        return entries

    def clear(self) -> None:
        """Clear all history."""
        self._entries = []
        self.save()

    @property
    def count(self) -> int:
        return len(self._entries)

    @property
    def path(self) -> str:
        return self._history_path
