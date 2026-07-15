"""Pin a capture to the screen as a floating always-on-top window.

Useful for keeping a reference image visible while working - error
messages, designs to compare against, that sort of thing.
"""


from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from .. import clipboard
from .icons import app_icon

MAX_INITIAL_FRACTION = 0.6
SCALE_STEP = 1.1
MIN_SIZE = 80


class PinWindow(QWidget):
    def __init__(self, filepath: str):
        super().__init__()
        self.filepath = filepath
        self.pixmap = QPixmap(filepath)
        self.setWindowTitle("LinuxShot Pin")
        self.setWindowIcon(app_icon())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        size = self.pixmap.size()
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableSize() * MAX_INITIAL_FRACTION
            if (size.width() > available.width()
                    or size.height() > available.height()):
                size.scale(available, Qt.AspectRatioMode.KeepAspectRatio)
        self.resize(size)
        self.setToolTip("Drag to move, scroll to resize, Esc or double-click to close")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self.pixmap)
        painter.setPen(Qt.GlobalColor.gray)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Compositor-side move: works on Wayland where manual
            # geometry updates don't.
            self.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event) -> None:
        self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()

    def wheelEvent(self, event) -> None:
        factor = SCALE_STEP if event.angleDelta().y() > 0 else 1 / SCALE_STEP
        width = max(MIN_SIZE, int(self.width() * factor))
        height = max(MIN_SIZE, int(self.height() * factor))
        self.resize(width, height)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        copy = menu.addAction("Copy image")
        copy.triggered.connect(lambda: clipboard.copy_image(self.filepath))
        close = menu.addAction("Close pin")
        close.triggered.connect(self.close)
        menu.exec(event.globalPos())


def run_pin_standalone(filepath: str) -> None:
    """Show a single pin and block until it's closed (CLI entry)."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("LinuxShot")
    window = PinWindow(filepath)
    window.show()
    app.exec()
