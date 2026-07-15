"""Capture history, persisted as JSON in the XDG data dir."""

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime

from .config import Config
from .utils import get_data_dir


@dataclass
class HistoryEntry:
    filepath: str
    timestamp: str
    mode: str  # region, fullscreen, window
    filesize: int = 0
    uploaded: bool = False
    upload_url: str = ""
    delete_url: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        return cls(
            filepath=data.get("filepath", ""),
            timestamp=data.get("timestamp", ""),
            mode=data.get("mode", ""),
            filesize=data.get("filesize", 0),
            uploaded=data.get("uploaded", False),
            upload_url=data.get("upload_url", ""),
            delete_url=data.get("delete_url", ""),
        )


class History:
    HISTORY_FILE = "history.json"

    def __init__(self):
        self._path = os.path.join(get_data_dir(), self.HISTORY_FILE)
        self._entries: list[HistoryEntry] = []
        self.load()

    def load(self) -> None:
        try:
            with open(self._path) as f:
                raw = json.load(f)
            self._entries = [HistoryEntry.from_dict(e) for e in raw]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._entries = []

    def save(self) -> None:
        max_entries = Config.get()["max_history_entries"]
        if len(self._entries) > max_entries:
            self._entries = self._entries[-max_entries:]
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump([asdict(e) for e in self._entries], f, indent=2)
                f.write("\n")
            os.replace(tmp, self._path)
        except OSError as e:
            print(f"warning: could not save history: {e}", file=sys.stderr)

    def add(self, filepath: str, mode: str, filesize: int = 0,
            uploaded: bool = False, upload_url: str = "",
            delete_url: str = "") -> HistoryEntry:
        entry = HistoryEntry(
            filepath=filepath,
            timestamp=datetime.now().isoformat(),
            mode=mode,
            filesize=filesize,
            uploaded=uploaded,
            upload_url=upload_url,
            delete_url=delete_url,
        )
        self._entries.append(entry)
        self.save()
        return entry

    def update_upload(self, filepath: str, url: str, delete_url: str = "") -> None:
        """Mark the most recent entry for *filepath* as uploaded."""
        for entry in reversed(self._entries):
            if entry.filepath == filepath:
                entry.uploaded = True
                entry.upload_url = url
                entry.delete_url = delete_url
                self.save()
                return

    def remove(self, filepath: str, timestamp: str = "") -> None:
        self._entries = [
            e for e in self._entries
            if not (e.filepath == filepath and (not timestamp or e.timestamp == timestamp))
        ]
        self.save()

    def get_entries(self, limit: int = 0) -> list[HistoryEntry]:
        """Entries newest-first, optionally limited."""
        entries = list(reversed(self._entries))
        return entries[:limit] if limit > 0 else entries

    def clear(self) -> None:
        """Empty the history, leaving a timestamped backup next to it so
        a stray click can't wipe months of upload links."""
        if self._entries and os.path.exists(self._path):
            backup = f"{self._path}.bak-{datetime.now():%Y%m%d-%H%M%S}"
            try:
                shutil.copy2(self._path, backup)
            except OSError:
                pass
        self._entries = []
        self.save()

    @property
    def count(self) -> int:
        return len(self._entries)

    @property
    def path(self) -> str:
        return self._path
