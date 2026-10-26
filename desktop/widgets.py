"""Small Qt widgets shared by the extraction page and download queue."""

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QObject, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QAbstractItemView, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QToolButton, QVBoxLayout

from .theme import set_symbol


class SegmentedControl(QFrame):
    """Native buttons with the small selection API used by existing filters."""
    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("segmented")
        self.items = []
        self.index = -1
        self.group = QButtonGroup(self)
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(3, 3, 3, 3)
        self.box.setSpacing(2)
        self.group.idClicked.connect(self.setCurrentIndex)

    def addItem(self, text, data=None):
        control = button(text, role="segment")
        control.setCheckable(True)
        self.group.addButton(control, len(self.items))
        self.box.addWidget(control)
        self.items.append(data)
        if self.index < 0:
            self.setCurrentIndex(0)

    def count(self):
        return len(self.items)

    def currentIndex(self):
        return self.index

    def currentData(self):
        return self.items[self.index] if self.index >= 0 else None

    def findData(self, data):
        return next((i for i, value in enumerate(self.items) if value == data), -1)

    def setCurrentIndex(self, index):
        if not 0 <= index < len(self.items) or index == self.index:
            return
        self.index = index
        self.group.button(index).setChecked(True)
        self.currentIndexChanged.emit(index)


class LinkInput(QPlainTextEdit):
    heightChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.height_timer = QTimer(self)
        self.height_timer.setSingleShot(True)
        self.height_timer.timeout.connect(self.fit_height)
        self.textChanged.connect(lambda: self.height_timer.start(0))
        self.setFixedHeight(46)
        self.setTabChangesFocus(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.height_timer.start(0)

    def fit_height(self):
        block, lines = self.document().begin(), 0
        while block.isValid() and lines < 4:
            lines += max(1, block.layout().lineCount())
            block = block.next()
        height = max(46, min(4, lines) * self.fontMetrics().lineSpacing() + 24)
        if height != self.height():
            self.setFixedHeight(height)
            self.heightChanged.emit(height)


class QualityComboBox(QComboBox):
    """Scrolling past a row must not silently change its download format."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            parent = self.parentWidget()
            while parent is not None and not isinstance(parent, QAbstractItemView):
                parent = parent.parentWidget()
            if parent is not None:
                QApplication.sendEvent(parent.viewport(), event)
            else:
                event.ignore()


class SmoothScroll(QObject):
    """Animate wheel ticks; preserve native pixel scrolling on touchpads."""
    def __init__(self, table):
        super().__init__(table)
        self.table = table
        self.animation = QPropertyAnimation(table.verticalScrollBar(), b"value", self)
        self.animation.setDuration(140)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        table.viewport().installEventFilter(self)
        table.verticalScrollBar().sliderPressed.connect(self.animation.stop)

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.Wheel or event.modifiers() or not event.pixelDelta().isNull():
            return False
        delta = event.angleDelta().y()
        bar = self.table.verticalScrollBar()
        if not delta or not bar.maximum():
            return False
        running = self.animation.state() == QAbstractAnimation.State.Running
        origin = self.animation.endValue() if running else bar.value()
        target = max(bar.minimum(), min(bar.maximum(), round(origin - delta / 120 * 96)))
        self.animation.stop()
        self.animation.setStartValue(bar.value())
        self.animation.setEndValue(target)
        self.animation.start()
        event.accept()
        return True


def label(text, role=None):
    widget = QLabel(text)
    if role:
        widget.setObjectName(role)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def button(text, callback=None, role=None, symbol=None):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        widget.clicked.connect(callback)
    if role:
        widget.setObjectName(role)
    if symbol:
        set_symbol(widget, symbol)
        widget.setIconSize(QSize(18, 18))
    return widget


def tool_button(symbol, tooltip, callback=None):
    widget = QToolButton()
    widget.setObjectName("iconButton")
    set_symbol(widget, symbol)
    widget.setIconSize(QSize(19, 19))
    widget.setToolTip(tooltip)
    widget.setAccessibleName(tooltip)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        widget.clicked.connect(callback)
    return widget


def card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(15)
    return frame, layout
