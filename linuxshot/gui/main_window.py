"""Main window, laid out like ShareX: action sidebar on the left, task
history filling the rest.
"""

import os
import sys
import threading

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon
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
from .icons import app_icon, theme_icon
from .settings import SettingsForm

THUMBNAIL_SIZE = QSize(64, 40)


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

        header("Upload")
        button("Upload file...", theme_icon("document-send"), self.upload_file_dialog)
        button("Upload last capture", theme_icon("go-up"), self.upload_last)

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
        layout.addWidget(self.tree)
        return page

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
            if os.path.isfile(entry.filepath):
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

        menu = QMenu(self)

        def add(text: str, slot, enabled: bool = True) -> QAction:
            action = menu.addAction(text)
            action.triggered.connect(slot)
            action.setEnabled(enabled)
            return action

        add("Open image", lambda: self._open_entry(), exists)
        add("Open containing folder", lambda: self._open_folder(entry))
        menu.addSeparator()
        add("Copy image", lambda: self._copy_image(entry), exists)
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

        def worker() -> None:
            ok = self.app.run_capture(mode)
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
