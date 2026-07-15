"""xdg-desktop-portal Screenshot backend.

The portal is the compositor-neutral capture path: it works on any
Wayland desktop that ships a portal implementation, and it is the only
capture mechanism available inside a Flatpak sandbox, where the usual
CLI tools don't exist. The trade-off is interactivity - the portal
shows the desktop's own screenshot dialog rather than honoring an exact
mode, so it's the fallback, not the default.
"""

import os
import secrets
import shutil
import urllib.parse

PORTAL_TIMEOUT = 120


def available() -> bool:
    try:
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
    except ImportError:
        return False
    DBusGMainLoop(set_as_default=True)
    try:
        bus = dbus.SessionBus()
        portal = bus.get_object(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
        props = dbus.Interface(portal, "org.freedesktop.DBus.Properties")
        return int(props.Get("org.freedesktop.portal.Screenshot", "version")) >= 1
    except Exception:
        return False


def take_screenshot(output: str, interactive: bool = True,
                    timeout: int = PORTAL_TIMEOUT) -> bool:
    """Ask the portal for a screenshot and move it to *output*.

    Returns False if the user cancelled or the portal is unusable.
    """
    try:
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib
    except ImportError:
        return False

    DBusGMainLoop(set_as_default=True)
    try:
        bus = dbus.SessionBus()
        portal = bus.get_object(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
        screenshot = dbus.Interface(portal, "org.freedesktop.portal.Screenshot")
    except Exception:
        return False

    token = "linuxshot_" + secrets.token_hex(4)
    sender = bus.get_unique_name()[1:].replace(".", "_")
    request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    loop = GLib.MainLoop()
    result: dict[str, str] = {}

    def on_response(code, results):
        if int(code) == 0 and "uri" in results:
            result["uri"] = str(results["uri"])
        loop.quit()

    try:
        bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface="org.freedesktop.portal.Request",
            path=request_path,
        )
        screenshot.Screenshot("", {
            "handle_token": token,
            "interactive": dbus.Boolean(interactive),
        })
    except Exception:
        return False

    GLib.timeout_add_seconds(timeout, loop.quit)
    loop.run()

    uri = result.get("uri", "")
    if not uri.startswith("file://"):
        return False
    source = urllib.parse.unquote(uri[len("file://"):])
    if not os.path.isfile(source):
        return False
    try:
        shutil.move(source, output)
    except OSError:
        return False
    return os.path.getsize(output) > 0
