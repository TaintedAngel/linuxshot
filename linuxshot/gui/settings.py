"""Settings form, shared between the main window and the tray dialog."""

import threading

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import Config


class SettingsForm(QWidget):
    """All configurable options as one scroll-friendly form."""

    def __init__(self, config: Config, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self._build()
        self.load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        shortcuts = QGroupBox("Keyboard Shortcuts")
        form = QFormLayout(shortcuts)
        self.key_region = QKeySequenceEdit()
        self.key_fullscreen = QKeySequenceEdit()
        self.key_window = QKeySequenceEdit()
        form.addRow("Capture region:", self.key_region)
        form.addRow("Capture fullscreen:", self.key_fullscreen)
        form.addRow("Capture window:", self.key_window)
        self.override_spectacle = QCheckBox("Replace Spectacle (use PrtSc keys)")
        self.override_spectacle.toggled.connect(self._on_override_toggled)
        form.addRow("", self.override_spectacle)
        hint = QLabel(
            "<small>Shortcuts are applied via KDE's global shortcut service "
            "when you save. On other desktops, bind the CLI commands "
            "(<code>linuxshot region</code> etc.) in your compositor config.</small>"
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        layout.addWidget(shortcuts)

        upload = QGroupBox("Upload (ImgBB)")
        form = QFormLayout(upload)
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText("Get one at api.imgbb.com")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API key:", self.api_key)
        self.auto_upload = QCheckBox("Upload automatically after every capture")
        form.addRow("", self.auto_upload)
        self.copy_url = QCheckBox("Copy URL to clipboard after upload")
        form.addRow("", self.copy_url)
        layout.addWidget(upload)

        capture = QGroupBox("Capture")
        form = QFormLayout(capture)
        self.copy_image = QCheckBox("Copy image to clipboard")
        form.addRow("", self.copy_image)
        self.show_notification = QCheckBox("Show desktop notifications")
        form.addRow("", self.show_notification)
        self.image_format = QComboBox()
        self.image_format.addItems(["png", "jpg", "webp"])
        form.addRow("Image format:", self.image_format)
        self.jpg_quality = QSpinBox()
        self.jpg_quality.setRange(1, 100)
        form.addRow("JPEG quality:", self.jpg_quality)
        self.capture_delay = QSpinBox()
        self.capture_delay.setRange(0, 30)
        self.capture_delay.setSuffix(" s")
        form.addRow("Capture delay:", self.capture_delay)
        layout.addWidget(capture)

        storage = QGroupBox("Storage")
        form = QFormLayout(storage)
        dir_row = QHBoxLayout()
        self.screenshot_dir = QLineEdit()
        self.screenshot_dir.setPlaceholderText("~/Pictures/LinuxShot (default)")
        dir_row.addWidget(self.screenshot_dir)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse)
        form.addRow("Screenshots folder:", dir_row)
        layout.addWidget(storage)

        layout.addStretch()

    def load(self) -> None:
        cfg = self.config
        self.key_region.setKeySequence(QKeySequence.fromString(cfg["shortcut_region"] or ""))
        self.key_fullscreen.setKeySequence(
            QKeySequence.fromString(cfg["shortcut_fullscreen"] or ""))
        self.key_window.setKeySequence(QKeySequence.fromString(cfg["shortcut_window"] or ""))
        self.override_spectacle.setChecked(bool(cfg["override_spectacle"]))
        self.api_key.setText(cfg["imgbb_api_key"] or "")
        self.auto_upload.setChecked(bool(cfg["auto_upload"]))
        self.copy_url.setChecked(bool(cfg["copy_url_to_clipboard"]))
        self.copy_image.setChecked(bool(cfg["copy_image_to_clipboard"]))
        self.show_notification.setChecked(bool(cfg["show_notification"]))
        self.image_format.setCurrentText(cfg["image_format"] or "png")
        self.jpg_quality.setValue(int(cfg["jpg_quality"]))
        self.capture_delay.setValue(int(cfg["capture_delay"]))
        self.screenshot_dir.setText(cfg["screenshot_dir"] or "")

    def apply(self) -> None:
        """Write the form back to config and re-register KDE shortcuts if
        they changed.
        """
        cfg = self.config
        old_keys = (cfg["shortcut_region"], cfg["shortcut_fullscreen"],
                    cfg["shortcut_window"], cfg["override_spectacle"])

        cfg["shortcut_region"] = self.key_region.keySequence().toString()
        cfg["shortcut_fullscreen"] = self.key_fullscreen.keySequence().toString()
        cfg["shortcut_window"] = self.key_window.keySequence().toString()
        cfg["override_spectacle"] = self.override_spectacle.isChecked()
        cfg["imgbb_api_key"] = self.api_key.text().strip()
        cfg["auto_upload"] = self.auto_upload.isChecked()
        cfg["copy_url_to_clipboard"] = self.copy_url.isChecked()
        cfg["copy_image_to_clipboard"] = self.copy_image.isChecked()
        cfg["show_notification"] = self.show_notification.isChecked()
        cfg["image_format"] = self.image_format.currentText()
        cfg["jpg_quality"] = self.jpg_quality.value()
        cfg["capture_delay"] = self.capture_delay.value()
        cfg["screenshot_dir"] = self.screenshot_dir.text().strip()
        cfg.save()

        new_keys = (cfg["shortcut_region"], cfg["shortcut_fullscreen"],
                    cfg["shortcut_window"], cfg["override_spectacle"])
        if new_keys != old_keys:
            threading.Thread(target=self._apply_shortcuts, daemon=True).start()

    def _on_override_toggled(self, checked: bool) -> None:
        if checked:
            self.key_region.setKeySequence(QKeySequence.fromString("Print"))
            self.key_fullscreen.setKeySequence(QKeySequence.fromString("Ctrl+Print"))
            self.key_window.setKeySequence(QKeySequence.fromString("Alt+Print"))

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose Screenshots Folder")
        if path:
            self.screenshot_dir.setText(path)

    @staticmethod
    def _apply_shortcuts() -> None:
        try:
            from ..shortcuts import setup_all
            _, messages = setup_all()
            for msg in messages:
                if msg:
                    print(msg)
        except Exception as e:
            print(f"warning: could not apply shortcuts: {e}")
