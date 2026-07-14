"""Capture pipeline: screenshot -> clipboard -> upload -> notify -> history.

This mirrors ShareX's after-capture task chain, with each step gated by
config so users can turn any of it off.
"""

import os
import subprocess
import sys

from . import clipboard, notify
from .capture import Capture, CaptureError, CaptureMode, CaptureResult
from .config import Config
from .history import History
from .upload import UploadError, upload


class App:
    def __init__(self):
        self.config = Config.get()
        self.history = History()
        self.capture_engine = Capture()

    def run_capture(self, mode: CaptureMode) -> bool:
        """Run the full pipeline. Returns False if the capture failed or
        the user cancelled the selection.
        """
        try:
            result = self.capture_engine.capture(mode)
        except CaptureError as e:
            notify.notify_error(str(e))
            print(f"error: {e}", file=sys.stderr)
            return False
        if result is None:
            return False

        print(f"Screenshot saved: {result.filepath}")

        if self.config["copy_image_to_clipboard"]:
            if clipboard.copy_image(result.filepath):
                print("Image copied to clipboard.")
            else:
                print("warning: could not copy image to clipboard", file=sys.stderr)

        if self.config["show_notification"]:
            notify.notify_capture_success(result.filepath)

        upload_url = ""
        if self.config["auto_upload"]:
            upload_url = self._upload_capture(result)
            if upload_url and self.config["show_notification"]:
                notify.notify_upload_success(upload_url)

        if self.config["save_history"]:
            self.history.add(
                filepath=result.filepath,
                mode=mode.value,
                filesize=result.filesize,
                uploaded=bool(upload_url),
                upload_url=upload_url,
            )
        return True

    def upload_file(self, filepath: str) -> str | None:
        """Upload an existing file, returning its URL or None on failure."""
        if not os.path.exists(filepath):
            notify.notify_error(f"File not found: {filepath}")
            return None

        try:
            result = upload(filepath)
        except UploadError as e:
            notify.notify_error(str(e))
            print(f"upload error: {e}", file=sys.stderr)
            return None

        print(f"Uploaded: {result.url}")
        if self.config["copy_url_to_clipboard"]:
            if clipboard.copy_text(result.url):
                print("URL copied to clipboard.")
            else:
                print("warning: could not copy URL to clipboard", file=sys.stderr)

        self.history.update_upload(filepath, result.url)
        if self.config["show_notification"]:
            notify.notify_upload_success(result.url)
        return result.url

    def upload_last(self) -> str | None:
        entries = self.history.get_entries(limit=1)
        if not entries:
            print("No captures in history.", file=sys.stderr)
            return None
        return self.upload_file(entries[0].filepath)

    def open_screenshots_dir(self) -> None:
        path = self.config.get_screenshot_dir()
        try:
            subprocess.Popen(["xdg-open", path])
        except FileNotFoundError:
            print(f"Screenshots directory: {path}")

    def _upload_capture(self, result: CaptureResult) -> str:
        try:
            upload_result = upload(result.filepath)
        except UploadError as e:
            notify.notify_error(f"Upload failed: {e}")
            print(f"upload error: {e}", file=sys.stderr)
            return ""

        print(f"Uploaded: {upload_result.url}")
        if self.config["copy_url_to_clipboard"] and clipboard.copy_text(upload_result.url):
            print("URL copied to clipboard.")
        return upload_result.url
