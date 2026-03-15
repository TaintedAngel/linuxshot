"""System tray icon for LinuxShot with ShareX-style menu."""

import signal
import sys
import threading

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from .app import App
from .capture import CaptureMode
from .config import Config

# Try AppIndicator3 first (best tray support), fall back to Gtk.StatusIcon
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator3
    HAS_APPINDICATOR = True
except (ValueError, ImportError):
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3
        HAS_APPINDICATOR = True
    except (ValueError, ImportError):
        HAS_APPINDICATOR = False


class TrayIcon:
    """System tray icon with a ShareX-style context menu."""

    def __init__(self):
        self.app = App()
        self.config = Config.get()

    def run(self) -> None:
        """Start the tray icon and GTK main loop."""
        if HAS_APPINDICATOR:
            self._create_appindicator()
        else:
            self._create_status_icon()

        # Handle Ctrl+C gracefully
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, Gtk.main_quit)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)

        print("LinuxShot tray is running. Right-click the tray icon for options.")
        Gtk.main()

    def _build_menu(self) -> Gtk.Menu:
        """Build the tray context menu (mirrors ShareX's tray menu)."""
        menu = Gtk.Menu()

        # ── Header ─────────────────────────────────────────────────
        header = Gtk.MenuItem(label="LinuxShot")
        header.set_sensitive(False)
        menu.append(header)
        menu.append(Gtk.SeparatorMenuItem())

        # ── Capture commands ───────────────────────────────────────
        item_region = Gtk.MenuItem(label="Capture Region")
        item_region.connect("activate", self._on_capture, CaptureMode.REGION)
        menu.append(item_region)

        item_fullscreen = Gtk.MenuItem(label="Capture Fullscreen")
        item_fullscreen.connect("activate", self._on_capture, CaptureMode.FULLSCREEN)
        menu.append(item_fullscreen)

        item_window = Gtk.MenuItem(label="Capture Window")
        item_window.connect("activate", self._on_capture, CaptureMode.WINDOW)
        menu.append(item_window)

        menu.append(Gtk.SeparatorMenuItem())

        # ── Upload ─────────────────────────────────────────────────
        item_upload_last = Gtk.MenuItem(label="Upload Last Capture")
        item_upload_last.connect("activate", self._on_upload_last)
        menu.append(item_upload_last)

        menu.append(Gtk.SeparatorMenuItem())

        # ── Auto-upload toggle ─────────────────────────────────────
        item_auto_upload = Gtk.CheckMenuItem(label="Auto Upload")
        item_auto_upload.set_active(self.config["auto_upload"])
        item_auto_upload.connect("toggled", self._on_toggle_auto_upload)
        menu.append(item_auto_upload)

        menu.append(Gtk.SeparatorMenuItem())

        # ── Utilities ──────────────────────────────────────────────
        item_open_dir = Gtk.MenuItem(label="Open Screenshots Folder")
        item_open_dir.connect("activate", self._on_open_dir)
        menu.append(item_open_dir)

        item_history = Gtk.MenuItem(label="Screenshot History...")
        item_history.connect("activate", self._on_show_history)
        menu.append(item_history)

        menu.append(Gtk.SeparatorMenuItem())

        # ── Quit ───────────────────────────────────────────────────
        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self._on_quit)
        menu.append(item_quit)

        menu.show_all()
        return menu

    # ── AppIndicator (preferred) ───────────────────────────────────

    def _create_appindicator(self) -> None:
        indicator = AppIndicator3.Indicator.new(
            "linuxshot",
            "camera-photo",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        indicator.set_title("LinuxShot")
        indicator.set_menu(self._build_menu())
        self._indicator = indicator

    # ── Gtk.StatusIcon (fallback) ──────────────────────────────────

    def _create_status_icon(self) -> None:
        icon = Gtk.StatusIcon()
        icon.set_from_icon_name("camera-photo")
        icon.set_tooltip_text("LinuxShot")
        icon.set_visible(True)
        icon.connect("popup-menu", self._on_status_icon_popup)
        self._status_icon = icon
        self._menu = self._build_menu()

    def _on_status_icon_popup(self, icon, button, time) -> None:
        self._menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, time)

    # ── Menu action handlers ───────────────────────────────────────

    def _on_capture(self, widget, mode: CaptureMode) -> None:
        """Run capture in a background thread so GTK doesn't freeze."""
        def do_capture():
            self.app.run_capture(mode)
        threading.Thread(target=do_capture, daemon=True).start()

    def _on_upload_last(self, widget) -> None:
        def do_upload():
            self.app.upload_last()
        threading.Thread(target=do_upload, daemon=True).start()

    def _on_toggle_auto_upload(self, widget) -> None:
        self.config["auto_upload"] = widget.get_active()
        self.config.save()

    def _on_open_dir(self, widget) -> None:
        self.app.open_screenshots_dir()

    def _on_show_history(self, widget) -> None:
        """Open a simple history window."""
        try:
            from .ui.main_window import HistoryDialog
            dialog = HistoryDialog()
            dialog.run()
            dialog.destroy()
        except ImportError:
            self.app.open_screenshots_dir()

    def _on_quit(self, widget) -> None:
        Gtk.main_quit()


def run_tray() -> None:
    """Entry point for the tray daemon."""
    tray = TrayIcon()
    tray.run()
