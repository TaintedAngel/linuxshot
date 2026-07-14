"""Desktop notifications via notify-send."""

import subprocess

from .utils import has_command


def send(title: str, body: str = "", icon: str = "image-x-generic",
         urgency: str = "normal", timeout_ms: int = 3000,
         image_path: str | None = None) -> bool:
    if not has_command("notify-send"):
        return False

    cmd = [
        "notify-send",
        "--app-name=LinuxShot",
        f"--urgency={urgency}",
        f"--expire-time={timeout_ms}",
        # Show the screenshot itself when we have one
        f"--icon={image_path or icon}",
        title,
        body,
    ]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=5).returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def notify_capture_success(filepath: str) -> None:
    send("Screenshot Captured", filepath, image_path=filepath)


def notify_upload_success(url: str) -> None:
    send("Upload Complete", f"Link copied to clipboard:\n{url}", icon="emblem-web")


def notify_error(message: str) -> None:
    send("LinuxShot Error", message, icon="dialog-error",
         urgency="critical", timeout_ms=5000)
