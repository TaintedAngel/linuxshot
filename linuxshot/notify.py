"""Desktop notifications for LinuxShot."""

import subprocess

from .utils import has_command


def send(
    title: str,
    body: str = "",
    icon: str = "image-x-generic",
    urgency: str = "normal",
    timeout_ms: int = 3000,
    image_path: str | None = None,
) -> bool:
    """Send a desktop notification using notify-send.

    Args:
        title: Notification title.
        body: Notification body text.
        icon: Icon name or path.
        urgency: One of 'low', 'normal', 'critical'.
        timeout_ms: Auto-dismiss timeout in milliseconds.
        image_path: Optional path to image to show in notification.
    """
    if not has_command("notify-send"):
        return False

    cmd = [
        "notify-send",
        "--app-name=LinuxShot",
        f"--urgency={urgency}",
        f"--expire-time={timeout_ms}",
    ]

    # Use the screenshot itself as the notification icon if available
    if image_path:
        cmd.append(f"--icon={image_path}")
    else:
        cmd.append(f"--icon={icon}")

    cmd.extend([title, body])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def notify_capture_success(filepath: str) -> None:
    """Notify that a screenshot was captured successfully."""
    send(
        "Screenshot Captured",
        filepath,
        image_path=filepath,
    )


def notify_upload_success(url: str) -> None:
    """Notify that upload was successful, URL copied."""
    send(
        "Upload Complete",
        f"Link copied to clipboard:\n{url}",
        icon="emblem-web",
    )


def notify_error(message: str) -> None:
    """Notify about an error."""
    send(
        "LinuxShot Error",
        message,
        icon="dialog-error",
        urgency="critical",
        timeout_ms=5000,
    )
