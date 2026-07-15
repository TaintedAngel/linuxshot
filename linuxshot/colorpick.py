"""Screen color picking.

Primary path is the xdg-desktop-portal PickColor call, which works on
KDE and GNOME under both Wayland and X11. wlroots compositors usually
lack that portal, so hyprpicker is the fallback there.
"""

import secrets


def pick_color(timeout: int = 120) -> str | None:
    """Let the user pick a pixel. Returns '#rrggbb' or None if
    cancelled/unsupported.
    """
    color = _pick_via_portal(timeout)
    if color:
        return color
    return _pick_via_hyprpicker()


def _pick_via_portal(timeout: int) -> str | None:
    try:
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib
    except ImportError:
        return None

    DBusGMainLoop(set_as_default=True)
    try:
        bus = dbus.SessionBus()
        portal = bus.get_object(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
        screenshot = dbus.Interface(portal, "org.freedesktop.portal.Screenshot")
    except Exception:
        return None

    # Subscribe to the response before making the call: the request
    # object path is derivable from our unique name plus a token.
    token = "linuxshot_" + secrets.token_hex(4)
    sender = bus.get_unique_name()[1:].replace(".", "_")
    request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    loop = GLib.MainLoop()
    picked: dict[str, str] = {}

    def on_response(code, results):
        if int(code) == 0 and "color" in results:
            picked["hex"] = _rgb_to_hex(*results["color"])
        loop.quit()

    try:
        bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface="org.freedesktop.portal.Request",
            path=request_path,
        )
        screenshot.PickColor("", {"handle_token": token})
    except Exception:
        return None

    GLib.timeout_add_seconds(timeout, loop.quit)
    loop.run()
    return picked.get("hex")


def _pick_via_hyprpicker() -> str | None:
    from .utils import has_command, run_cmd

    if not has_command("hyprpicker"):
        return None
    try:
        result = run_cmd(["hyprpicker", "-n", "-f", "hex"], timeout=120)
    except Exception:
        return None
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        return None
    return value if value.startswith("#") else f"#{value}"


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    """Portal colors are doubles in [0, 1]."""
    def channel(v: float) -> int:
        return max(0, min(255, round(float(v) * 255)))
    return f"#{channel(r):02x}{channel(g):02x}{channel(b):02x}"
