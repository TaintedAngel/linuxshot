"""Desktop notifications via notify-send."""

import subprocess

from .utils import has_command


def send(title: str, body: str = "", icon: str = "image-x-generic",
         urgency: str = "normal", timeout_ms: int = 3000,
         image_path: str | None = None) -> bool:
    if not has_command("notify-send"):
        # No libnotify binary (e.g. inside Flatpak): talk to the
        # notification service directly.
        return _send_dbus(title, body, image_path or icon, urgency, timeout_ms)

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


def _send_dbus(title: str, body: str, icon: str,
               urgency: str, timeout_ms: int) -> bool:
    try:
        import dbus
        bus = dbus.SessionBus()
        service = bus.get_object(
            "org.freedesktop.Notifications", "/org/freedesktop/Notifications")
        iface = dbus.Interface(service, "org.freedesktop.Notifications")
        levels = {"low": 0, "normal": 1, "critical": 2}
        hints = {"urgency": dbus.Byte(levels.get(urgency, 1))}
        iface.Notify("LinuxShot", 0, icon, title, body, [], hints, timeout_ms)
        return True
    except Exception:
        return False


def notify_capture_success(filepath: str) -> None:
    send("Screenshot Captured", filepath, image_path=filepath)


def notify_upload_success(url: str) -> None:
    send("Upload Complete", f"Link copied to clipboard:\n{url}", icon="emblem-web")


def notify_error(message: str) -> None:
    send("LinuxShot Error", message, icon="dialog-error",
         urgency="critical", timeout_ms=5000)
