"""Post-capture annotation editor.

A QGraphicsScene stacked on top of the screenshot: every annotation is
a graphics item, so undo is just removing the last one and nothing is
destructive until the final render. Blur is the exception - it samples
the underlying image once, at draw time.

The editor resolves to one of three outcomes: DONE (annotations applied
and written back to the file), SKIP (continue with the untouched
capture), or DISCARD (drop the capture entirely).
"""

import math
import os
import threading

from PySide6.QtCore import QEventLoop, QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QFont,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QToolBar,
    QWidget,
)

from .icons import app_icon

DONE = "done"
SKIP = "skip"
DISCARD = "discard"

TOOLS = ("arrow", "line", "rect", "ellipse", "highlight", "text", "step",
         "blur", "pixelate", "crop")
PIXELATE_FACTOR = 14
BLUR_SHRINK = 8
BLUR_PASSES = 3
HIGHLIGHT_COLOR = QColor(255, 235, 59, 90)


class ArrowItem(QGraphicsPathItem):
    def __init__(self, start: QPointF, color: QColor, width: int):
        super().__init__()
        self.start = start
        self.setPen(QPen(color, width, Qt.PenStyle.SolidLine,
                         Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        self.setBrush(QBrush(color))
        self.set_end(start)

    def set_end(self, end: QPointF) -> None:
        path = QPainterPath(self.start)
        path.lineTo(end)

        angle = math.atan2(end.y() - self.start.y(), end.x() - self.start.x())
        size = max(10.0, self.pen().widthF() * 4)
        for offset in (math.pi / 7, -math.pi / 7):
            tip = QPointF(
                end.x() - size * math.cos(angle + offset),
                end.y() - size * math.sin(angle + offset),
            )
            path.addPolygon(QPolygonF([end, tip]))
        self.setPath(path)


class EditorView(QGraphicsView):
    """Forwards mouse events to the window's tool logic and zooms on
    Ctrl+wheel."""

    def __init__(self, scene: QGraphicsScene, editor: "EditorWindow"):
        super().__init__(scene)
        self.editor = editor
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.editor.begin_draw(self.mapToScene(event.position().toPoint())):
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.editor.update_draw(self.mapToScene(event.position().toPoint())):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.editor.end_draw(self.mapToScene(event.position().toPoint())):
                return
        super().mouseReleaseEvent(event)


class EditorWindow(QMainWindow):
    finished = Signal(str)  # DONE | SKIP | DISCARD

    def __init__(self, filepath: str):
        super().__init__()
        self.filepath = filepath
        self.setWindowTitle(f"LinuxShot Editor - {os.path.basename(filepath)}")
        self.setWindowIcon(app_icon())

        self.base = QPixmap(filepath)
        self.scene = QGraphicsScene()
        self.scene.addItem(QGraphicsPixmapItem(self.base))
        self.scene.setSceneRect(QRectF(self.base.rect()))

        self.view = EditorView(self.scene, self)
        self.setCentralWidget(self.view)

        self.tool = "arrow"
        self.color = QColor("#e53935")
        self.pen_width = 3
        self.step_counter = 1
        self._active_item = None
        self._draw_origin = QPointF()
        self._undo_stack: list[list] = []
        self._crop_rect: QRectF | None = None
        self._crop_marquee: QGraphicsRectItem | None = None
        self._outcome: str | None = None

        self._build_toolbar()
        self.resize(min(self.base.width() + 60, 1200),
                    min(self.base.height() + 120, 800))

    def _build_toolbar(self) -> None:
        bar = QToolBar("Tools")
        bar.setMovable(False)
        self.addToolBar(bar)

        group = QActionGroup(self)
        labels = {
            "arrow": "Arrow", "line": "Line", "rect": "Box", "ellipse": "Ellipse",
            "highlight": "Highlight", "text": "Text", "step": "Step",
            "blur": "Blur", "pixelate": "Pixelate", "crop": "Crop",
        }
        tips = {
            "blur": "Soften an area (cosmetic - not for secrets)",
            "pixelate": "Mosaic an area; use this to redact keys and passwords",
        }
        for name in TOOLS:
            action = QAction(labels[name], self)
            action.setCheckable(True)
            action.setChecked(name == self.tool)
            if name in tips:
                action.setToolTip(tips[name])
            action.triggered.connect(lambda _=False, n=name: self._set_tool(n))
            group.addAction(action)
            bar.addAction(action)

        bar.addSeparator()

        self.color_button = QPushButton()
        self.color_button.setFixedSize(28, 22)
        self.color_button.setToolTip("Annotation color")
        self.color_button.clicked.connect(self._pick_color)
        self._refresh_color_button()
        bar.addWidget(self.color_button)

        width_spin = QSpinBox()
        width_spin.setRange(1, 20)
        width_spin.setValue(self.pen_width)
        width_spin.setToolTip("Line width")
        width_spin.valueChanged.connect(lambda v: setattr(self, "pen_width", v))
        bar.addWidget(width_spin)

        undo = QAction("Undo", self)
        undo.setShortcut(QKeySequence.StandardKey.Undo)
        undo.triggered.connect(self.undo)
        bar.addAction(undo)

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy(),
                             spacer.sizePolicy().verticalPolicy())
        spacer.setMinimumWidth(24)
        bar.addWidget(spacer)

        discard = QAction("Discard capture", self)
        discard.triggered.connect(lambda: self._finish(DISCARD))
        bar.addAction(discard)

        skip = QAction("Skip", self)
        skip.setToolTip("Continue with the unedited screenshot")
        skip.triggered.connect(lambda: self._finish(SKIP))
        bar.addAction(skip)

        done = QAction("Done", self)
        done.setShortcut("Ctrl+Return")
        done.setToolTip("Apply annotations and continue (Ctrl+Enter)")
        done.triggered.connect(lambda: self._finish(DONE))
        bar.addAction(done)

    def _set_tool(self, name: str) -> None:
        self.tool = name

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(self.color, self, "Annotation color")
        if color.isValid():
            self.color = color
            self._refresh_color_button()

    def _refresh_color_button(self) -> None:
        self.color_button.setStyleSheet(
            f"background-color: {self.color.name()}; border: 1px solid gray;")

    # -- Drawing -------------------------------------------------------------

    def begin_draw(self, pos: QPointF) -> bool:
        self._draw_origin = pos
        pen = QPen(self.color, self.pen_width)

        if self.tool == "arrow":
            self._active_item = ArrowItem(pos, self.color, self.pen_width)
        elif self.tool == "line":
            path = QPainterPath(pos)
            self._active_item = QGraphicsPathItem(path)
            self._active_item.setPen(pen)
        elif self.tool in ("rect", "blur", "pixelate", "crop"):
            self._active_item = QGraphicsRectItem(QRectF(pos, pos))
            if self.tool == "rect":
                self._active_item.setPen(pen)
            else:
                dashed = QPen(Qt.GlobalColor.white, 1, Qt.PenStyle.DashLine)
                self._active_item.setPen(dashed)
        elif self.tool == "ellipse":
            self._active_item = QGraphicsEllipseItem(QRectF(pos, pos))
            self._active_item.setPen(pen)
        elif self.tool == "highlight":
            self._active_item = QGraphicsRectItem(QRectF(pos, pos))
            self._active_item.setPen(QPen(Qt.PenStyle.NoPen))
            self._active_item.setBrush(QBrush(HIGHLIGHT_COLOR))
        elif self.tool == "text":
            self._add_text(pos)
            return True
        elif self.tool == "step":
            self._add_step(pos)
            return True
        else:
            return False

        self.scene.addItem(self._active_item)
        return True

    def update_draw(self, pos: QPointF) -> bool:
        item = self._active_item
        if item is None:
            return False
        if isinstance(item, ArrowItem):
            item.set_end(pos)
        elif isinstance(item, QGraphicsPathItem):
            path = QPainterPath(self._draw_origin)
            path.lineTo(pos)
            item.setPath(path)
        elif isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            item.setRect(QRectF(self._draw_origin, pos).normalized())
        return True

    def end_draw(self, pos: QPointF) -> bool:
        item = self._active_item
        if item is None:
            return False
        self.update_draw(pos)
        self._active_item = None

        if self.tool in ("blur", "pixelate"):
            rect = item.rect().toRect().intersected(self.base.rect())
            self.scene.removeItem(item)
            if rect.width() > 4 and rect.height() > 4:
                factory = (self._add_blurred if self.tool == "blur"
                           else self._add_pixelated)
                self._push_undo([factory(rect)])
        elif self.tool == "crop":
            self._set_crop(item)
        else:
            rect = getattr(item, "rect", lambda: None)()
            if rect is not None and rect.width() < 3 and rect.height() < 3:
                self.scene.removeItem(item)  # accidental click
            else:
                self._push_undo([item])
        return True

    def _add_pixelated(self, rect) -> QGraphicsPixmapItem:
        source = self.base.copy(rect).toImage()
        # Smooth downscale averages each block (a real mosaic); the fast
        # upscale keeps the blocks crisp instead of re-smoothing them.
        small = source.scaled(
            max(1, rect.width() // PIXELATE_FACTOR),
            max(1, rect.height() // PIXELATE_FACTOR),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        coarse = small.scaled(
            rect.width(), rect.height(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        item = QGraphicsPixmapItem(QPixmap.fromImage(coarse))
        item.setPos(rect.topLeft())
        self.scene.addItem(item)
        return item

    def _add_blurred(self, rect) -> QGraphicsPixmapItem:
        # Repeated smooth down/upscaling approximates a strong gaussian
        # blur and, unlike QGraphicsBlurEffect, renders identically
        # everywhere.
        image = self.base.copy(rect).toImage()
        for _ in range(BLUR_PASSES):
            small = image.scaled(
                max(1, rect.width() // BLUR_SHRINK),
                max(1, rect.height() // BLUR_SHRINK),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            image = small.scaled(
                rect.width(), rect.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        item = QGraphicsPixmapItem(QPixmap.fromImage(image))
        item.setPos(rect.topLeft())
        self.scene.addItem(item)
        return item

    def _set_crop(self, marquee: QGraphicsRectItem) -> None:
        if self._crop_marquee is not None:
            self.scene.removeItem(self._crop_marquee)
        rect = marquee.rect().intersected(QRectF(self.base.rect()))
        if rect.width() < 8 or rect.height() < 8:
            self.scene.removeItem(marquee)
            self._crop_marquee = None
            self._crop_rect = None
            return
        marquee.setRect(rect)
        self._crop_marquee = marquee
        self._crop_rect = rect

    def _add_text(self, pos: QPointF) -> None:
        item = QGraphicsTextItem()
        item.setDefaultTextColor(self.color)
        item.setFont(QFont("sans-serif", 12 + self.pen_width * 2, QFont.Weight.Bold))
        item.setPos(pos)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.scene.addItem(item)
        item.setFocus()
        self._push_undo([item])

    def _add_step(self, pos: QPointF) -> None:
        radius = 14 + self.pen_width * 2
        circle = QGraphicsEllipseItem(
            pos.x() - radius, pos.y() - radius, radius * 2, radius * 2)
        circle.setBrush(QBrush(self.color))
        circle.setPen(QPen(Qt.GlobalColor.white, 2))

        label = QGraphicsSimpleTextItem(str(self.step_counter), circle)
        label.setBrush(QBrush(Qt.GlobalColor.white))
        label.setFont(QFont("sans-serif", radius - 4, QFont.Weight.Bold))
        bounds = label.boundingRect()
        label.setPos(pos.x() - bounds.width() / 2, pos.y() - bounds.height() / 2)

        self.scene.addItem(circle)
        self.step_counter += 1
        self._push_undo([circle])

    def _push_undo(self, items: list) -> None:
        self._undo_stack.append(items)

    def undo(self) -> None:
        if not self._undo_stack:
            if self._crop_marquee is not None:
                self.scene.removeItem(self._crop_marquee)
                self._crop_marquee = None
                self._crop_rect = None
            return
        for item in self._undo_stack.pop():
            self.scene.removeItem(item)

    # -- Finish --------------------------------------------------------------

    def has_changes(self) -> bool:
        return bool(self._undo_stack) or self._crop_rect is not None

    def render_result(self) -> QImage:
        if self._crop_marquee is not None:
            self._crop_marquee.hide()
        # Drop focus so no text cursor gets rendered
        self.scene.clearFocus()

        source = self._crop_rect or QRectF(self.base.rect())
        image = QImage(int(source.width()), int(source.height()),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.scene.render(painter, QRectF(image.rect()), source)
        painter.end()
        return image

    def _finish(self, outcome: str) -> None:
        if outcome == DONE:
            if self.has_changes():
                if not self.render_result().save(self.filepath):
                    self.statusBar().showMessage("Could not save the image", 5000)
                    return
            else:
                outcome = SKIP
        self._outcome = outcome
        self.close()

    def closeEvent(self, event) -> None:
        if self._outcome is None:
            self._outcome = SKIP
        self.finished.emit(self._outcome)
        super().closeEvent(event)


def open_editor(filepath: str) -> str:
    """Show the editor and block (with a nested event loop) until it
    resolves. Needs a running QApplication; returns DONE/SKIP/DISCARD.
    """
    window = EditorWindow(filepath)
    loop = QEventLoop()
    result = {}

    def on_finished(outcome: str) -> None:
        result["outcome"] = outcome
        loop.quit()

    window.finished.connect(on_finished)
    window.show()
    window.raise_()
    window.activateWindow()
    loop.exec()
    return result.get("outcome", SKIP)


def run_editor_standalone(filepath: str) -> str:
    """Editor entry point for CLI processes with no Qt app running yet."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("LinuxShot")
    return open_editor(filepath)


class EditorBridge(QObject):
    """Lets capture worker threads open the editor on the Qt main
    thread and wait for the outcome.
    """

    _request = Signal(object)

    def __init__(self):
        super().__init__()
        self._request.connect(self._on_request)

    def edit(self, filepath: str) -> str:
        job = {"path": filepath, "event": threading.Event(), "outcome": SKIP}
        self._request.emit(job)
        job["event"].wait()
        return job["outcome"]

    def _on_request(self, job: dict) -> None:
        try:
            job["outcome"] = open_editor(job["path"])
        finally:
            job["event"].set()
