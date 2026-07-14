"""Settings form, shared between the main window and the tray dialog."""

import json
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
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
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

        upload = QGroupBox("Upload")
        form = QFormLayout(upload)
        self.upload_service = QComboBox()
        self.upload_service.addItems(["imgbb", "imgur", "catbox", "0x0", "custom"])
        form.addRow("Destination:", self.upload_service)

        self.service_pages = QStackedWidget()
        self.service_pages.addWidget(self._imgbb_page())
        self.service_pages.addWidget(self._imgur_page())
        self.service_pages.addWidget(self._catbox_page())
        self.service_pages.addWidget(self._0x0_page())
        self.service_pages.addWidget(self._custom_page())
        self.upload_service.currentIndexChanged.connect(self._switch_service_page)
        self._switch_service_page(0)
        form.addRow(self.service_pages)

        self.auto_upload = QCheckBox("Upload automatically after every capture")
        form.addRow("", self.auto_upload)
        self.copy_url = QCheckBox("Copy URL to clipboard after upload")
        form.addRow("", self.copy_url)
        layout.addWidget(upload)

        capture = QGroupBox("Capture")
        form = QFormLayout(capture)
        self.open_editor = QCheckBox("Open the annotation editor after each capture")
        form.addRow("", self.open_editor)
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

    def _switch_service_page(self, index: int) -> None:
        # Only let the visible page drive the stack's height, otherwise
        # every service reserves room for the tallest one.
        for i in range(self.service_pages.count()):
            page = self.service_pages.widget(i)
            vertical = (QSizePolicy.Policy.Preferred if i == index
                        else QSizePolicy.Policy.Ignored)
            page.setSizePolicy(QSizePolicy.Policy.Preferred, vertical)
        self.service_pages.setCurrentIndex(index)
        self.service_pages.adjustSize()

    def _imgbb_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.imgbb_api_key = QLineEdit()
        self.imgbb_api_key.setPlaceholderText("Get one at api.imgbb.com")
        self.imgbb_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API key:", self.imgbb_api_key)
        return page

    def _imgur_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.imgur_client_id = QLineEdit()
        self.imgur_client_id.setPlaceholderText("Register at api.imgur.com/oauth2/addclient")
        self.imgur_client_id.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Client ID:", self.imgur_client_id)
        return page

    def _catbox_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.catbox_userhash = QLineEdit()
        self.catbox_userhash.setPlaceholderText("Optional; enables deleting uploads")
        self.catbox_userhash.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("User hash:", self.catbox_userhash)
        return page

    def _0x0_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        note = QLabel("<small>No account needed. Files expire after up to a year.</small>")
        note.setWordWrap(True)
        form.addRow(note)
        return page

    def _custom_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.custom_uploader = QPlainTextEdit()
        self.custom_uploader.setPlaceholderText(
            '{\n  "request_url": "https://host/api/upload",\n'
            '  "file_form_name": "file",\n  "headers": {"Authorization": "..."},\n'
            '  "response_type": "json",\n  "url_key": "files.0.url"\n}'
        )
        self.custom_uploader.setMaximumHeight(140)
        form.addRow("Request spec:", self.custom_uploader)
        return page

    def load(self) -> None:
        cfg = self.config
        self.key_region.setKeySequence(QKeySequence.fromString(cfg["shortcut_region"] or ""))
        self.key_fullscreen.setKeySequence(
            QKeySequence.fromString(cfg["shortcut_fullscreen"] or ""))
        self.key_window.setKeySequence(QKeySequence.fromString(cfg["shortcut_window"] or ""))
        self.override_spectacle.setChecked(bool(cfg["override_spectacle"]))
        service = cfg["upload_service"] or "imgbb"
        index = self.upload_service.findText(service)
        self.upload_service.setCurrentIndex(index if index >= 0 else 0)
        self._switch_service_page(self.upload_service.currentIndex())
        self.imgbb_api_key.setText(cfg["imgbb_api_key"] or "")
        self.imgur_client_id.setText(cfg["imgur_client_id"] or "")
        self.catbox_userhash.setText(cfg["catbox_userhash"] or "")
        spec = cfg["custom_uploader"]
        self.custom_uploader.setPlainText(json.dumps(spec, indent=2) if spec else "")
        self.auto_upload.setChecked(bool(cfg["auto_upload"]))
        self.copy_url.setChecked(bool(cfg["copy_url_to_clipboard"]))
        self.open_editor.setChecked(bool(cfg["open_editor_after_capture"]))
        self.copy_image.setChecked(bool(cfg["copy_image_to_clipboard"]))
        self.show_notification.setChecked(bool(cfg["show_notification"]))
        self.image_format.setCurrentText(cfg["image_format"] or "png")
        self.jpg_quality.setValue(int(cfg["jpg_quality"]))
        self.capture_delay.setValue(int(cfg["capture_delay"]))
        self.screenshot_dir.setText(cfg["screenshot_dir"] or "")

    def apply(self) -> bool:
        """Write the form back to config and re-register KDE shortcuts if
        they changed. Returns False if a field failed validation.
        """
        custom_text = self.custom_uploader.toPlainText().strip()
        custom_spec = {}
        if custom_text:
            try:
                custom_spec = json.loads(custom_text)
            except json.JSONDecodeError as e:
                QMessageBox.warning(self, "Custom uploader",
                                    f"The request spec is not valid JSON:\n{e}")
                return False

        cfg = self.config
        old_keys = (cfg["shortcut_region"], cfg["shortcut_fullscreen"],
                    cfg["shortcut_window"], cfg["override_spectacle"])

        cfg["shortcut_region"] = self.key_region.keySequence().toString()
        cfg["shortcut_fullscreen"] = self.key_fullscreen.keySequence().toString()
        cfg["shortcut_window"] = self.key_window.keySequence().toString()
        cfg["override_spectacle"] = self.override_spectacle.isChecked()
        cfg["upload_service"] = self.upload_service.currentText()
        cfg["imgbb_api_key"] = self.imgbb_api_key.text().strip()
        cfg["imgur_client_id"] = self.imgur_client_id.text().strip()
        cfg["catbox_userhash"] = self.catbox_userhash.text().strip()
        cfg["custom_uploader"] = custom_spec
        cfg["auto_upload"] = self.auto_upload.isChecked()
        cfg["copy_url_to_clipboard"] = self.copy_url.isChecked()
        cfg["open_editor_after_capture"] = self.open_editor.isChecked()
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
        return True

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
