"""Main window, laid out like ShareX: action sidebar on the left, task
history filling the rest.
"""

import os
import subprocess
import sys
import threading

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, clipboard
from ..app import App
from ..capture import CaptureMode
from ..config import Config
from ..history import History, HistoryEntry
from .editor import EditorBridge, open_editor
from .icons import app_icon, theme_icon
from .pin import PinWindow
from .settings import SettingsForm

THUMBNAIL_SIZE = QSize(64, 40)
VIDEO_SUFFIXES = (".mp4", ".webm", ".gif", ".mkv")


def is_video(filepath: str) -> bool:
    return filepath.lower().endswith(VIDEO_SUFFIXES)


class MainWindow(QMainWindow):
    # Emitted from worker threads once a capture or upload finishes.
    task_done = Signal(str, bool)  # status message, reshow window

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LinuxShot")
        self.setWindowIcon(app_icon())
        self.resize(920, 560)

        self.app = App()
        self.config = Config.get()
        self.history = History()
        self.editor_bridge = EditorBridge()
        self._pins: list[PinWindow] = []

        self.task_done.connect(self._on_task_done)
        self._build()
        self.refresh_history()

    def _build(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        root.addWidget(self._build_sidebar())

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_history_page())
        self.pages.addWidget(self._build_settings_page())
        root.addWidget(self.pages, 1)

        self.statusBar().showMessage("Ready")

    # -- Sidebar -----------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setFixedWidth(190)
        sidebar.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(2)

        def header(text: str) -> None:
            label = QLabel(text)
            label.setStyleSheet("font-weight: bold; padding: 8px 6px 2px 6px;")
            layout.addWidget(label)

        def button(text: str, icon: QIcon, slot) -> QPushButton:
            btn = QPushButton(f"  {text}")
            btn.setIcon(icon)
            btn.setFlat(True)
            btn.setStyleSheet("text-align: left; padding: 7px 8px;")
            btn.clicked.connect(slot)
            layout.addWidget(btn)
            return btn

        header("Capture")
        button("Region", theme_icon("select-rectangular", "edit-select-all"),
               lambda: self.start_capture(CaptureMode.REGION))
        button("Fullscreen", theme_icon("view-fullscreen"),
               lambda: self.start_capture(CaptureMode.FULLSCREEN))
        button("Active window", theme_icon("window", "preferences-system-windows"),
               lambda: self.start_capture(CaptureMode.WINDOW))
        button("Record screen", theme_icon("media-record"),
               lambda: self.toggle_record("screen"))
        button("Record region", theme_icon("media-record"),
               lambda: self.toggle_record("region"))

        header("Upload")
        button("Upload file...", theme_icon("document-send"), self.upload_file_dialog)
        button("Upload last capture", theme_icon("go-up"), self.upload_last)

        header("Tools")
        button("OCR - copy text", theme_icon("scanner", "edit-find"), self.run_ocr_tool)
        button("Pick color", theme_icon("color-picker", "colormanagement"),
               self.pick_color_tool)
        button("Pin last capture", theme_icon("window-pin", "pin"), self.pin_last)

        header("Application")
        button("History", theme_icon("view-history", "document-open-recent"),
               lambda: self.pages.setCurrentIndex(0))
        button("Settings", theme_icon("configure", "preferences-system"),
               lambda: self.pages.setCurrentIndex(1))
        button("Screenshots folder", theme_icon("folder-pictures", "folder"),
               self.app.open_screenshots_dir)

        layout.addStretch()
        version = QLabel(f"LinuxShot {__version__}")
        version.setStyleSheet("color: gray; padding: 4px 6px;")
        layout.addWidget(version)
        return sidebar

    # -- History page --------------------------------------------------------

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        toolbar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter history...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.search_box)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_history)
        toolbar.addWidget(refresh)

        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear_history)
        toolbar.addWidget(clear)
        layout.addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Time", "Mode", "Size", "URL"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIconSize(THUMBNAIL_SIZE)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._history_menu)
        self.tree.itemDoubleClicked.connect(self._open_entry)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 150)
        self.tree.setColumnWidth(2, 90)
        self.tree.setColumnWidth(3, 70)
        self.tree.currentItemChanged.connect(self._update_preview)

        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(self._build_preview_pane())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        return page

    def _build_preview_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(8, 0, 0, 0)

        self.preview_image = QLabel("Select a capture")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumWidth(220)
        layout.addWidget(self.preview_image, 1)

        self.preview_name = QLabel("")
        self.preview_name.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.preview_name.setWordWrap(True)
        layout.addWidget(self.preview_name)

        self.preview_url = QLabel("")
        self.preview_url.setOpenExternalLinks(True)
        self.preview_url.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        self.preview_url.setWordWrap(True)
        layout.addWidget(self.preview_url)
        return pane

    def _update_preview(self, item, _previous=None) -> None:
        entry = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if entry is None:
            self.preview_image.setText("Select a capture")
            self.preview_image.setPixmap(QPixmap())
            self.preview_name.clear()
            self.preview_url.clear()
            return
        if is_video(entry.filepath):
            self.preview_image.setPixmap(QPixmap())
            self.preview_image.setText("Video - double-click to play")
            self.preview_name.setText(os.path.basename(entry.filepath))
            self.preview_url.setText("")
            return
        pixmap = QPixmap(entry.filepath)
        if pixmap.isNull():
            self.preview_image.setText("File no longer exists")
        else:
            width = max(220, self.preview_image.width() - 8)
            self.preview_image.setPixmap(pixmap.scaledToWidth(
                min(width, pixmap.width()),
                Qt.TransformationMode.SmoothTransformation))
        self.preview_name.setText(os.path.basename(entry.filepath))
        self.preview_url.setText(
            f'<a href="{entry.upload_url}">{entry.upload_url}</a>'
            if entry.upload_url else "")

    def refresh_history(self) -> None:
        self.history.load()
        self.tree.clear()
        for entry in self.history.get_entries(limit=200):
            item = QTreeWidgetItem([
                os.path.basename(entry.filepath),
                entry.timestamp[:19].replace("T", " "),
                entry.mode,
                f"{entry.filesize / 1024:.0f} KB" if entry.filesize else "",
                entry.upload_url,
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            if is_video(entry.filepath):
                item.setIcon(0, theme_icon("video-x-generic"))
            elif os.path.isfile(entry.filepath):
                # QIcon loads the pixmap lazily, on first paint
                item.setIcon(0, QIcon(entry.filepath))
            else:
                item.setIcon(0, theme_icon("image-missing"))
                item.setForeground(0, Qt.GlobalColor.gray)
            self.tree.addTopLevelItem(item)
        self._apply_filter(self.search_box.text())

    def _apply_filter(self, text: str) -> None:
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            haystack = " ".join(item.text(col) for col in range(5)).lower()
            item.setHidden(bool(text) and text not in haystack)

    def _selected_entry(self) -> HistoryEntry | None:
        item = self.tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def _history_menu(self, pos) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        exists = os.path.isfile(entry.filepath)
        image = exists and not is_video(entry.filepath)

        menu = QMenu(self)

        def add(text: str, slot, enabled: bool = True) -> QAction:
            action = menu.addAction(text)
            action.triggered.connect(slot)
            action.setEnabled(enabled)
            return action

        add("Open", lambda: self._open_entry(), exists)
        add("Edit", lambda: self._edit_entry(entry), image)
        add("Open containing folder", lambda: self._open_folder(entry))
        menu.addSeparator()
        add("Pin to screen", lambda: self.pin_file(entry.filepath), image)
        add("Copy image", lambda: self._copy_image(entry), image)
        add("Copy URL", lambda: self._copy_url(entry), bool(entry.upload_url))
        add("Upload", lambda: self.upload_path(entry.filepath), exists)
        add("Open delete link",
            lambda: QDesktopServices.openUrl(QUrl(entry.delete_url)),
            bool(entry.delete_url))
        menu.addSeparator()
        add("Remove from history", lambda: self._remove_entry(entry))
        add("Delete file", lambda: self._delete_entry(entry), exists)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _open_entry(self, *_args) -> None:
        entry = self._selected_entry()
        if entry and os.path.isfile(entry.filepath):
            QDesktopServices.openUrl(QUrl.fromLocalFile(entry.filepath))

    def _edit_entry(self, entry: HistoryEntry) -> None:
        if open_editor(entry.filepath) == "done":
            self.refresh_history()
            self.statusBar().showMessage("Image saved", 4000)

    def _open_folder(self, entry: HistoryEntry) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(entry.filepath)))

    def _copy_image(self, entry: HistoryEntry) -> None:
        if clipboard.copy_image(entry.filepath):
            self.statusBar().showMessage("Image copied to clipboard", 4000)
        else:
            self.statusBar().showMessage("Could not copy image", 4000)

    def _copy_url(self, entry: HistoryEntry) -> None:
        if clipboard.copy_text(entry.upload_url):
            self.statusBar().showMessage("URL copied to clipboard", 4000)

    def _remove_entry(self, entry: HistoryEntry) -> None:
        self.history.remove(entry.filepath, entry.timestamp)
        self.refresh_history()

    def _delete_entry(self, entry: HistoryEntry) -> None:
        answer = QMessageBox.question(
            self, "Delete file",
            f"Delete {os.path.basename(entry.filepath)} from disk?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(entry.filepath)
        except OSError as e:
            QMessageBox.warning(self, "Delete failed", str(e))
            return
        self.history.remove(entry.filepath, entry.timestamp)
        self.refresh_history()

    def _clear_history(self) -> None:
        answer = QMessageBox.question(
            self, "Clear history",
            "Remove all history entries? Files on disk are kept.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.history.clear()
            self.refresh_history()

    # -- Settings page -----------------------------------------------------

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_form = SettingsForm(self.config)
        scroll.setWidget(self.settings_form)
        layout.addWidget(scroll)

        buttons = QHBoxLayout()
        buttons.addStretch()
        save = QPushButton("Save settings")
        save.clicked.connect(self._save_settings)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        return page

    def _save_settings(self) -> None:
        if self.settings_form.apply():
            self.statusBar().showMessage("Settings saved", 4000)

    # -- Capture / upload actions ------------------------------------------

    def start_capture(self, mode: CaptureMode) -> None:
        """Hide the window, capture, then come back with history refreshed."""
        self.hide()
        editor = (self.editor_bridge.edit
                  if self.config["open_editor_after_capture"] else None)

        def worker() -> None:
            ok = self.app.run_capture(mode, editor=editor)
            self.task_done.emit(
                "Capture finished" if ok else "Capture cancelled", True
            )

        # Give the compositor a moment to actually unmap the window,
        # otherwise it shows up in its own screenshot.
        QTimer.singleShot(300, lambda: threading.Thread(target=worker, daemon=True).start())

    def upload_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Upload image", self.config.get_screenshot_dir(),
            "Images (*.png *.jpg *.jpeg *.webp *.gif);;All files (*)",
        )
        if path:
            self.upload_path(path)

    def upload_last(self) -> None:
        self.statusBar().showMessage("Uploading...")

        def worker() -> None:
            url = self.app.upload_last()
            self.task_done.emit(f"Uploaded: {url}" if url else "Upload failed", False)

        threading.Thread(target=worker, daemon=True).start()

    def upload_path(self, filepath: str) -> None:
        self.statusBar().showMessage("Uploading...")

        def worker() -> None:
            url = self.app.upload_file(filepath)
            self.task_done.emit(f"Uploaded: {url}" if url else "Upload failed", False)

        threading.Thread(target=worker, daemon=True).start()

    def toggle_record(self, mode: str) -> None:
        from .. import recording

        starting = recording.current() is None
        if starting:
            self.hide()
        else:
            self.statusBar().showMessage("Finalizing recording...")

        def worker() -> None:
            path = self.app.toggle_recording(mode)
            if path:
                self.task_done.emit(f"Recording saved: {os.path.basename(path)}", True)
            elif starting:
                self.task_done.emit(
                    "Recording... use the tray or this button again to stop", False)
            else:
                self.task_done.emit("Recording failed", True)

        QTimer.singleShot(
            300 if starting else 0,
            lambda: threading.Thread(target=worker, daemon=True).start())

    def run_ocr_tool(self) -> None:
        self.hide()

        def worker() -> None:
            text = self.app.run_ocr()
            self.task_done.emit(
                f"OCR: copied {len(text)} characters" if text else "OCR: no text",
                True)

        QTimer.singleShot(300, lambda: threading.Thread(target=worker, daemon=True).start())

    def pick_color_tool(self) -> None:
        # The portal color picker needs its own GLib loop; a subprocess
        # keeps that out of this process entirely.
        def worker() -> None:
            result = subprocess.run(
                [sys.executable, "-m", "linuxshot", "pick-color"],
                capture_output=True, text=True, timeout=180)
            color = result.stdout.strip()
            self.task_done.emit(
                f"Color copied: {color}" if result.returncode == 0 and color
                else "Color picking cancelled", False)

        self.statusBar().showMessage("Click a pixel anywhere on screen...")
        threading.Thread(target=worker, daemon=True).start()

    def pin_last(self) -> None:
        entries = self.history.get_entries(limit=1)
        if not entries or not os.path.isfile(entries[0].filepath):
            self.statusBar().showMessage("Nothing to pin yet", 4000)
            return
        self.pin_file(entries[0].filepath)

    def pin_file(self, filepath: str) -> None:
        pin = PinWindow(filepath)
        pin.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._pins.append(pin)
        pin.destroyed.connect(lambda: self._pins.remove(pin) if pin in self._pins else None)
        pin.show()

    def _on_task_done(self, message: str, reshow: bool) -> None:
        if reshow:
            self.show()
            self.raise_()
            self.activateWindow()
        self.refresh_history()
        self.statusBar().showMessage(message, 6000)

    def show_settings(self) -> None:
        self.pages.setCurrentIndex(1)
        self.show()
        self.raise_()
        self.activateWindow()


def run_gui() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("LinuxShot")
    app.setDesktopFileName("linuxshot")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
