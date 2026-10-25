"""Small Qt widgets shared by the extraction page and download queue."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QToolButton, QVBoxLayout

from .theme import icon


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
        widget.setIcon(icon(symbol, "#ffffff" if role == "primary" else "#64748b"))
        widget.setIconSize(QSize(18, 18))
    return widget


def tool_button(symbol, tooltip, callback=None):
    widget = QToolButton()
    widget.setObjectName("iconButton")
    widget.setIcon(icon(symbol, "#2563eb"))
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
