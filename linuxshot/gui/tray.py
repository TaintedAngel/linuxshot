"""System tray daemon.

Runs the Qt event loop, owns the (lazily created) main window, and
listens on DBus for the KGlobalAccel shortcuts registered by
linuxshot.shortcuts.
"""

import signal
import sys
import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ..app import App
from ..capture import CaptureMode
from ..config import Config
from .icons import app_icon, ensure_icon_installed
from .main_window import MainWindow

SHORTCUT_ACTIONS = {
    "CaptureRegion": CaptureMode.REGION,
    "CaptureFullscreen": CaptureMode.FULLSCREEN,
    "CaptureWindow": CaptureMode.WINDOW,
}


class Tray(QObject):
    # Relays DBus shortcut presses (which arrive on a GLib thread) onto
    # the Qt main thread.
    shortcut_pressed = Signal(str)

    def __init__(self, qt_app: QApplication):
        super().__init__()
        self.qt_app = qt_app
        self.app = App()
        self.config = Config.get()
        self._window: MainWindow | None = None

        self.icon = QSystemTrayIcon(app_icon())
        self.icon.setToolTip("LinuxShot")
        self.icon.setContextMenu(self._build_menu())
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

        self.shortcut_pressed.connect(self._on_shortcut)

    def _build_menu(self) -> QMenu:
        menu = QMenu()

        open_action = menu.addAction("Open LinuxShot")
        open_action.triggered.connect(self.show_window)
        menu.addSeparator()

        for label, mode in (
            ("Capture Region", CaptureMode.REGION),
            ("Capture Fullscreen", CaptureMode.FULLSCREEN),
            ("Capture Window", CaptureMode.WINDOW),
        ):
            action = menu.addAction(label)
            action.triggered.connect(lambda _=False, m=mode: self.capture(m))

        menu.addSeparator()
        upload_last = menu.addAction("Upload Last Capture")
        upload_last.triggered.connect(
            lambda: threading.Thread(target=self.app.upload_last, daemon=True).start()
        )

        auto_upload = menu.addAction("Auto Upload")
        auto_upload.setCheckable(True)
        auto_upload.setChecked(bool(self.config["auto_upload"]))
        auto_upload.toggled.connect(self._toggle_auto_upload)

        menu.addSeparator()
        folder = menu.addAction("Open Screenshots Folder")
        folder.triggered.connect(self.app.open_screenshots_dir)

        settings = menu.addAction("Settings...")
        settings.triggered.connect(self.show_settings)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.qt_app.quit)

        self._menu = menu  # keep alive; the tray icon doesn't own it
        return menu

    # -- Actions ------------------------------------------------------------

    def capture(self, mode: CaptureMode) -> None:
        threading.Thread(
            target=self.app.run_capture, args=(mode,), daemon=True
        ).start()

    def show_window(self) -> None:
        window = self._get_window()
        window.refresh_history()
        window.show()
        window.raise_()
        window.activateWindow()

    def show_settings(self) -> None:
        self._get_window().show_settings()

    def _get_window(self) -> MainWindow:
        if self._window is None:
            self._window = MainWindow()
        return self._window

    def _toggle_auto_upload(self, checked: bool) -> None:
        self.config["auto_upload"] = checked
        self.config.save()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._window and self._window.isVisible():
                self._window.hide()
            else:
                self.show_window()

    def _on_shortcut(self, action: str) -> None:
        mode = SHORTCUT_ACTIONS.get(action)
        if mode:
            self.capture(mode)

    # -- Global shortcuts over DBus -------------------------------------------

    def setup_global_shortcuts(self) -> None:
        """Register our KGlobalAccel shortcuts and subscribe to their
        globalShortcutPressed signals. Quietly does nothing off KDE.
        """
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            from gi.repository import GLib
        except ImportError as e:
            print(f"warning: dbus/GLib not available, global shortcuts disabled: {e}")
            return

        # Must be the default main loop before the first SessionBus()
        DBusGMainLoop(set_as_default=True)

        try:
            from ..shortcuts import register_shortcuts_dbus
            for msg in register_shortcuts_dbus():
                if msg:
                    print(msg)
        except Exception as e:
            print(f"warning: shortcut registration failed: {e}")

        try:
            bus = dbus.SessionBus()
            bus.add_signal_receiver(
                self._on_dbus_shortcut,
                signal_name="globalShortcutPressed",
                dbus_interface="org.kde.kglobalaccel.Component",
                path="/component/linuxshot",
            )
        except Exception as e:
            print(f"warning: DBus signal listener failed: {e}")
            print("Global keyboard shortcuts will not work this session.")
            return

        # A GLib loop on a daemon thread dispatches the DBus signals;
        # the actual capture is bounced back to the Qt thread via
        # shortcut_pressed.
        self._glib_loop = GLib.MainLoop()
        threading.Thread(target=self._glib_loop.run, daemon=True).start()
        print("Listening for global shortcuts on DBus.")

    def _on_dbus_shortcut(self, component, shortcut, timestamp) -> None:
        self.shortcut_pressed.emit(str(shortcut))


def run_tray() -> None:
    ensure_icon_installed()

    qt_app = QApplication.instance() or QApplication(sys.argv)
    qt_app.setApplicationName("LinuxShot")
    qt_app.setDesktopFileName("linuxshot")
    qt_app.setQuitOnLastWindowClosed(False)

    tray = Tray(qt_app)
    tray.setup_global_shortcuts()

    print("LinuxShot tray is running. Right-click the tray icon for options.")

    # Let Ctrl+C and SIGTERM stop the loop; the timer gives the Python
    # interpreter a chance to run its signal handlers.
    signal.signal(signal.SIGINT, lambda *_: qt_app.quit())
    signal.signal(signal.SIGTERM, lambda *_: qt_app.quit())
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    sys.exit(qt_app.exec())
