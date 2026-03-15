"""Main application logic for LinuxShot.

Orchestrates the capture → upload → clipboard → notify pipeline,
just like ShareX's after-capture task system.
"""

import os
import sys

from . import clipboard, notify
from .capture import Capture, CaptureError, CaptureMode, CaptureResult
from .config import Config
from .history import History
from .upload import UploadError, upload


class App:
    """LinuxShot application coordinator."""

    def __init__(self):
        self.config = Config.get()
        self.history = History()
        self.capture_engine = Capture()

    def run_capture(self, mode: CaptureMode) -> bool:
        """Execute the full capture pipeline.

        1. Take screenshot
        2. Copy image to clipboard (if configured)
        3. Upload to Imgur (if configured)
        4. Copy URL to clipboard (if configured)
        5. Show notification
        6. Save to history

        Returns True if capture was successful, False if cancelled.
        """
        # ── Step 1: Capture ────────────────────────────────────────────
        try:
            result = self.capture_engine.capture(mode)
        except CaptureError as e:
            notify.notify_error(str(e))
            print(f"Error: {e}", file=sys.stderr)
            return False

        if result is None:
            # User cancelled (pressed Escape, etc.)
            return False

        print(f"Screenshot saved: {result.filepath}")

        # ── Step 2: Copy image to clipboard ────────────────────────────
        if self.config["copy_image_to_clipboard"]:
            if clipboard.copy_image(result.filepath):
                print("Image copied to clipboard.")
            else:
                print("Warning: Failed to copy image to clipboard.", file=sys.stderr)

        # ── Step 3: Upload (if auto-upload is enabled) ─────────────────
        upload_url = ""
        if self.config["auto_upload"]:
            upload_url = self._do_upload(result)

        # ── Step 4: Show notification ──────────────────────────────────
        if self.config["show_notification"]:
            if upload_url:
                notify.notify_upload_success(upload_url)
            else:
                notify.notify_capture_success(result.filepath)

        # ── Step 5: Save to history ────────────────────────────────────
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
        """Upload an existing file.

        Returns the URL on success, None on failure.
        """
        if not os.path.exists(filepath):
            notify.notify_error(f"File not found: {filepath}")
            return None

        try:
            result = upload(filepath)
        except UploadError as e:
            notify.notify_error(str(e))
            print(f"Upload error: {e}", file=sys.stderr)
            return None

        url = result.url
        print(f"Uploaded: {url}")

        # Copy URL to clipboard
        if self.config["copy_url_to_clipboard"]:
            if clipboard.copy_text(url):
                print("URL copied to clipboard.")
            else:
                print("Warning: Failed to copy URL to clipboard.", file=sys.stderr)

        # Update history entry
        self.history.update_upload(filepath, url, result.delete_hash)

        # Notify
        if self.config["show_notification"]:
            notify.notify_upload_success(url)

        return url

    def upload_last(self) -> str | None:
        """Upload the most recent capture."""
        entries = self.history.get_entries(limit=1)
        if not entries:
            print("No captures in history.", file=sys.stderr)
            return None
        return self.upload_file(entries[0].filepath)

    def open_screenshots_dir(self) -> None:
        """Open the screenshots directory in the file manager."""
        screenshot_dir = self.config.get_screenshot_dir()
        try:
            import subprocess
            subprocess.Popen(["xdg-open", screenshot_dir])
        except FileNotFoundError:
            print(f"Screenshots directory: {screenshot_dir}")

    def _do_upload(self, result: CaptureResult) -> str:
        """Handle upload and clipboard copy for a capture result."""
        try:
            upload_result = upload(result.filepath)
            url = upload_result.url
            print(f"Uploaded: {url}")

            if self.config["copy_url_to_clipboard"]:
                if clipboard.copy_text(url):
                    print("URL copied to clipboard.")

            return url
        except UploadError as e:
            notify.notify_error(f"Upload failed: {e}")
            print(f"Upload error: {e}", file=sys.stderr)
            return ""
