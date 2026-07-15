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

    def run_capture(self, mode: CaptureMode, editor=None) -> bool:
        """Run the full pipeline. Returns False if the capture failed or
        the user cancelled the selection.

        *editor* is an optional callable (filepath -> outcome) that runs
        between capture and the after-capture steps; it may rewrite the
        file in place. Outcome "discard" aborts the pipeline and deletes
        the capture.
        """
        try:
            result = self.capture_engine.capture(mode)
        except CaptureError as e:
            notify.notify_error(str(e))
            print(f"error: {e}", file=sys.stderr)
            return False
        if result is None:
            return False

        if editor is not None:
            if editor(result.filepath) == "discard":
                try:
                    os.remove(result.filepath)
                except OSError:
                    pass
                print("Capture discarded.")
                return False
            if os.path.exists(result.filepath):
                result.filesize = os.path.getsize(result.filepath)

        print(f"Screenshot saved: {result.filepath}")

        if self.config["copy_image_to_clipboard"]:
            if clipboard.copy_image(result.filepath):
                print("Image copied to clipboard.")
            else:
                print("warning: could not copy image to clipboard", file=sys.stderr)

        if self.config["show_notification"]:
            notify.notify_capture_success(result.filepath)

        uploaded = None
        if self.config["auto_upload"]:
            uploaded = self._upload_capture(result)
            if uploaded and self.config["show_notification"]:
                notify.notify_upload_success(uploaded.url)

        if self.config["save_history"]:
            self.history.add(
                filepath=result.filepath,
                mode=mode.value,
                filesize=result.filesize,
                uploaded=uploaded is not None,
                upload_url=uploaded.url if uploaded else "",
                delete_url=uploaded.delete_url if uploaded else "",
            )
        return True

    def upload_file(self, filepath: str, service: str | None = None) -> str | None:
        """Upload an existing file, returning its URL or None on failure."""
        if not os.path.exists(filepath):
            notify.notify_error(f"File not found: {filepath}")
            return None

        try:
            result = upload(filepath, service)
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

        self.history.update_upload(filepath, result.url, result.delete_url)
        if self.config["show_notification"]:
            notify.notify_upload_success(result.url)
        return result.url

    def run_ocr(self) -> str | None:
        """Capture a region and put the recognized text on the clipboard.
        Returns the text, or None if cancelled / nothing found.
        """
        import tempfile

        from .ocr import OcrError, extract_text

        with tempfile.TemporaryDirectory(prefix="linuxshot-ocr-") as tmp:
            try:
                result = self.capture_engine.capture(
                    CaptureMode.REGION, output_path=os.path.join(tmp, "ocr.png"))
            except CaptureError as e:
                notify.notify_error(str(e))
                print(f"error: {e}", file=sys.stderr)
                return None
            if result is None:
                return None
            try:
                text = extract_text(result.filepath, self.config["ocr_language"])
            except OcrError as e:
                notify.notify_error(str(e))
                print(f"error: {e}", file=sys.stderr)
                return None

        if not text:
            notify.send("OCR", "No text found in the selection.")
            print("No text found.", file=sys.stderr)
            return None

        if clipboard.copy_text(text):
            lines = text.count("\n") + 1
            notify.send("OCR", f"Copied {len(text)} characters ({lines} lines).")
        print(text)
        return text

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

    def _upload_capture(self, result: CaptureResult):
        try:
            upload_result = upload(result.filepath)
        except UploadError as e:
            notify.notify_error(f"Upload failed: {e}")
            print(f"upload error: {e}", file=sys.stderr)
            return None

        print(f"Uploaded: {upload_result.url}")
        if self.config["copy_url_to_clipboard"] and clipboard.copy_text(upload_result.url):
            print("URL copied to clipboard.")
        return upload_result
