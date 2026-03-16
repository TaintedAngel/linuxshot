"""System tray icon for LinuxShot using Qt (native KDE Plasma support)."""

import os
import shutil
import signal
import sys
import threading

from .app import App
from .capture import CaptureMode
from .config import Config

# Icon paths - try installed location first, fall back to source tree
_ICON_SEARCH_PATHS = [
    os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps/linuxshot.svg"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "resources", "icons", "linuxshot.svg"),
    "/usr/share/icons/hicolor/scalable/apps/linuxshot.svg",
]


def _ensure_icon_installed() -> None:
    """Auto-install the SVG icon if it hasn't been installed yet."""
    installed = os.path.expanduser(
        "~/.local/share/icons/hicolor/scalable/apps/linuxshot.svg"
    )
    if os.path.isfile(installed):
        return
    src = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "resources", "icons", "linuxshot.svg",
    )
    if os.path.isfile(src):
        os.makedirs(os.path.dirname(installed), exist_ok=True)
        shutil.copy2(src, installed)


def _find_icon() -> str:
    """Return the best available icon path."""
    for path in _ICON_SEARCH_PATHS:
        if os.path.isfile(path):
            return path
    return "camera-photo"


class TrayIcon:
    """System tray icon with a ShareX-style context menu (Qt-based)."""

    def __init__(self):
        self.app_logic = App()
        self.config = Config.get()

    def run(self) -> None:
        _ensure_icon_installed()

        from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
        from PySide6.QtGui import QIcon, QAction

        self._qt_app = QApplication.instance() or QApplication(sys.argv)
        self._qt_app.setQuitOnLastWindowClosed(False)

        icon_path = _find_icon()
        icon = QIcon(icon_path) if os.path.isfile(icon_path) else QIcon.fromTheme("camera-photo")

        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("LinuxShot")

        # ── Build context menu ─────────────────────────────────────
        menu = QMenu()

        header = menu.addAction("LinuxShot")
        header.setEnabled(False)
        menu.addSeparator()

        region = menu.addAction("Capture Region")
        region.triggered.connect(lambda: self._on_capture(CaptureMode.REGION))

        fullscreen = menu.addAction("Capture Fullscreen")
        fullscreen.triggered.connect(lambda: self._on_capture(CaptureMode.FULLSCREEN))

        window = menu.addAction("Capture Window")
        window.triggered.connect(lambda: self._on_capture(CaptureMode.WINDOW))

        menu.addSeparator()

        upload_last = menu.addAction("Upload Last Capture")
        upload_last.triggered.connect(self._on_upload_last)

        menu.addSeparator()

        auto_upload = menu.addAction("Auto Upload")
        auto_upload.setCheckable(True)
        auto_upload.setChecked(self.config["auto_upload"])
        auto_upload.toggled.connect(self._on_toggle_auto_upload)

        menu.addSeparator()

        open_dir = menu.addAction("Open Screenshots Folder")
        open_dir.triggered.connect(self._on_open_dir)

        settings = menu.addAction("Settings...")
        settings.triggered.connect(self._on_settings)

        menu.addSeparator()

        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._qt_app.quit)

        self._tray.setContextMenu(menu)
        self._tray.show()

        # Register keyboard shortcuts and listen for them via DBus
        # (must happen in main thread after DBusGMainLoop is set)
        self._setup_global_shortcuts()

        # Hint about shortcut setup
        desktop_file = os.path.expanduser(
            "~/.local/share/applications/linuxshot.desktop"
        )
        if not os.path.isfile(desktop_file):
            print(
                "Tip: Run 'linuxshot setup' to register shortcuts and install desktop file."
            )

        print("LinuxShot tray is running. Right-click the tray icon for options.")

        # Handle SIGINT/SIGTERM so Ctrl+C works
        signal.signal(signal.SIGINT, lambda *_: self._qt_app.quit())
        signal.signal(signal.SIGTERM, lambda *_: self._qt_app.quit())
        # Timer lets Python process signals while Qt event loop runs
        from PySide6.QtCore import QTimer
        timer = QTimer()
        timer.start(500)
        timer.timeout.connect(lambda: None)

        sys.exit(self._qt_app.exec())

    # ── Menu action handlers ───────────────────────────────────────

    def _on_capture(self, mode: CaptureMode) -> None:
        threading.Thread(
            target=self.app_logic.run_capture, args=(mode,), daemon=True
        ).start()

    def _on_upload_last(self) -> None:
        threading.Thread(target=self.app_logic.upload_last, daemon=True).start()

    def _on_toggle_auto_upload(self, checked: bool) -> None:
        self.config["auto_upload"] = checked
        self.config.save()

    def _on_open_dir(self) -> None:
        self.app_logic.open_screenshots_dir()

    def _setup_global_shortcuts(self) -> None:
        """Register shortcuts via DBus AND listen for the signals.

        KGlobalAccel emits globalShortcutPressed on
        /component/linuxshot_desktop when our shortcuts fire.
        """
        # Must set GLib main loop as default BEFORE any dbus.SessionBus()
        import dbus as _dbus
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib
        DBusGMainLoop(set_as_default=True)

        # Step 1: Register shortcuts
        try:
            from .shortcuts import _register_shortcuts_dbus
            msgs = _register_shortcuts_dbus()
            for m in msgs:
                if m:
                    print(m)
        except Exception as e:
            print(f"Shortcut registration error: {e}")

        # Step 2: Listen for globalShortcutPressed via dbus-python + GLib
        try:
            bus = _dbus.SessionBus()
            bus.add_signal_receiver(
                self._on_global_shortcut,
                signal_name="globalShortcutPressed",
                dbus_interface="org.kde.kglobalaccel.Component",
                path="/component/linuxshot",
            )
            # GLib main loop in a daemon thread dispatches DBus signals
            self._glib_loop = GLib.MainLoop()
            threading.Thread(
                target=self._glib_loop.run, daemon=True
            ).start()
            print("Listening for global shortcuts on DBus.")
        except Exception as e:
            print(f"DBus signal listener failed: {e}")
            print("Global keyboard shortcuts will not work.")

    def _on_global_shortcut(self, component, shortcut, timestamp) -> None:
        """Called by KGlobalAccel when one of our shortcuts is pressed."""
        action_map = {
            "CaptureRegion": CaptureMode.REGION,
            "CaptureFullscreen": CaptureMode.FULLSCREEN,
            "CaptureWindow": CaptureMode.WINDOW,
        }
        mode = action_map.get(str(shortcut))
        if mode:
            print(f"Shortcut pressed: {shortcut}")
            threading.Thread(
                target=self.app_logic.run_capture, args=(mode,), daemon=True
            ).start()

    def _on_settings(self) -> None:
        """Show the Qt Settings dialog."""
        # Check if dialog exists and is still alive (not deleted by WA_DeleteOnClose)
        try:
            if self._settings_dlg.isVisible():
                self._settings_dlg.activateWindow()
                return
        except (AttributeError, RuntimeError):
            pass  # Not created yet, or C++ object deleted
        self._settings_dlg = SettingsDialog(self.config)
        self._settings_dlg.show()


# ── Settings dialog


class SettingsDialog:
    """Lightweight PySide6 settings window launched from the tray."""

    def __init__(self, config: Config):
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
            QComboBox, QCheckBox, QLineEdit, QPushButton,
            QFileDialog, QGroupBox, QLabel, QKeySequenceEdit,
        )
        from PySide6.QtGui import QKeySequence
        from PySide6.QtCore import Qt

        self.config = config

        self._dlg = QDialog()
        self._dlg.setWindowTitle("LinuxShot Settings")
        self._dlg.setMinimumWidth(460)
        self._dlg.setAttribute(Qt.WA_DeleteOnClose)

        layout = QVBoxLayout(self._dlg)

        # ── Shortcuts group ───────────────────────────────────────
        shortcut_group = QGroupBox("Keyboard Shortcuts")
        shortcut_form = QFormLayout(shortcut_group)

        self._key_region = QKeySequenceEdit(
            QKeySequence.fromString(config["shortcut_region"] or "Ctrl+Shift+4")
        )
        shortcut_form.addRow("Capture Region:", self._key_region)

        self._key_fullscreen = QKeySequenceEdit(
            QKeySequence.fromString(config["shortcut_fullscreen"] or "Ctrl+Shift+3")
        )
        shortcut_form.addRow("Capture Fullscreen:", self._key_fullscreen)

        self._key_window = QKeySequenceEdit(
            QKeySequence.fromString(config["shortcut_window"] or "Ctrl+Shift+5")
        )
        shortcut_form.addRow("Capture Window:", self._key_window)

        self._override_spectacle = QCheckBox("Replace Spectacle (use PrtSc keys)")
        self._override_spectacle.setChecked(config["override_spectacle"])
        self._override_spectacle.toggled.connect(self._on_override_toggled)
        shortcut_form.addRow("", self._override_spectacle)

        shortcut_hint = QLabel(
            '<small>Press the key field and type your shortcut. '
            'Click "Save" then run <code>linuxshot setup</code> to apply.</small>'
        )
        shortcut_hint.setWordWrap(True)
        shortcut_form.addRow(shortcut_hint)

        layout.addWidget(shortcut_group)

        # ── Upload group ───────────────────────────────────────────
        upload_group = QGroupBox("Upload")
        upload_form = QFormLayout(upload_group)

        self._service_combo = QComboBox()
        self._service_combo.addItems(["catbox", "0x0", "imgur"])
        current_service = config["upload_service"] or "catbox"
        idx = self._service_combo.findText(current_service)
        if idx >= 0:
            self._service_combo.setCurrentIndex(idx)
        upload_form.addRow("Upload service:", self._service_combo)

        self._auto_upload = QCheckBox()
        self._auto_upload.setChecked(config["auto_upload"])
        upload_form.addRow("Auto-upload after capture:", self._auto_upload)

        self._copy_url = QCheckBox()
        self._copy_url.setChecked(config["copy_url_to_clipboard"])
        upload_form.addRow("Copy URL to clipboard:", self._copy_url)

        layout.addWidget(upload_group)

        # ── Capture group ──────────────────────────────────────────
        capture_group = QGroupBox("Capture")
        capture_form = QFormLayout(capture_group)

        self._copy_image = QCheckBox()
        self._copy_image.setChecked(config["copy_image_to_clipboard"])
        capture_form.addRow("Copy image to clipboard:", self._copy_image)

        self._show_notif = QCheckBox()
        self._show_notif.setChecked(config["show_notification"])
        capture_form.addRow("Show notifications:", self._show_notif)

        fmt_row = QHBoxLayout()
        self._format_combo = QComboBox()
        self._format_combo.addItems(["png", "jpg", "webp"])
        fmt_idx = self._format_combo.findText(config["image_format"] or "png")
        if fmt_idx >= 0:
            self._format_combo.setCurrentIndex(fmt_idx)
        fmt_row.addWidget(self._format_combo)
        capture_form.addRow("Image format:", fmt_row)

        layout.addWidget(capture_group)

        # ── Storage group ──────────────────────────────────────────
        storage_group = QGroupBox("Storage")
        storage_form = QFormLayout(storage_group)

        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("~/Pictures/LinuxShot (default)")
        self._dir_edit.setText(config["screenshot_dir"] or "")
        dir_row.addWidget(self._dir_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse_btn)
        storage_form.addRow("Screenshots folder:", dir_row)

        layout.addWidget(storage_group)

        # ── Buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._dlg.close)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    # delegate show/isVisible/activateWindow to the underlying QDialog
    def show(self):
        self._dlg.show()

    def isVisible(self):
        return self._dlg.isVisible()

    def activateWindow(self):
        self._dlg.activateWindow()

    def _browse_dir(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self._dlg, "Choose Screenshots Folder")
        if path:
            self._dir_edit.setText(path)

    def _on_override_toggled(self, checked: bool) -> None:
        """When Override Spectacle is checked, auto-fill PrtSc keys."""
        from PySide6.QtGui import QKeySequence
        if checked:
            self._key_region.setKeySequence(QKeySequence.fromString("Print"))
            self._key_fullscreen.setKeySequence(QKeySequence.fromString("Ctrl+Print"))
            self._key_window.setKeySequence(QKeySequence.fromString("Alt+Print"))

    def _save(self) -> None:
        # Shortcuts
        self.config["shortcut_region"] = self._key_region.keySequence().toString()
        self.config["shortcut_fullscreen"] = self._key_fullscreen.keySequence().toString()
        self.config["shortcut_window"] = self._key_window.keySequence().toString()
        self.config["override_spectacle"] = self._override_spectacle.isChecked()
        # Upload
        self.config["upload_service"] = self._service_combo.currentText()
        self.config["auto_upload"] = self._auto_upload.isChecked()
        self.config["copy_url_to_clipboard"] = self._copy_url.isChecked()
        # Capture
        self.config["copy_image_to_clipboard"] = self._copy_image.isChecked()
        self.config["show_notification"] = self._show_notif.isChecked()
        self.config["image_format"] = self._format_combo.currentText()
        # Storage
        self.config["screenshot_dir"] = self._dir_edit.text().strip()
        self.config.save()

        # Auto-apply shortcuts in background
        import threading
        threading.Thread(target=self._apply_shortcuts, daemon=True).start()
        self._dlg.close()

    @staticmethod
    def _apply_shortcuts() -> None:
        """Run shortcut setup after saving config."""
        try:
            from .shortcuts import setup_all
            ok, msgs = setup_all()
            for m in msgs:
                if m:
                    print(m)
        except Exception as e:
            print(f"Shortcut apply error: {e}")


def run_tray() -> None:
    """Entry point for the tray daemon."""
    tray = TrayIcon()
    tray.run()
