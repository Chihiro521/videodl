from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QFont, QFontDatabase
from pathlib import Path
import math


def apply_theme(application):
    # Qt's offscreen Windows plugin does not enumerate installed fonts.
    if not QFontDatabase.families():
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf"):
            path = Path("C:/Windows/Fonts") / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
    application.setFont(QFont("Microsoft YaHei UI", 9))
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE)


def icon(name, color="#5d6470", size=22):
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 12, size / 12)
    painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if name == "download":
        painter.drawLine(12, 3, 12, 15)
        painter.drawLine(7, 10, 12, 15)
        painter.drawLine(12, 15, 17, 10)
        painter.drawLine(4, 15, 4, 20)
        painter.drawLine(4, 20, 20, 20)
        painter.drawLine(20, 20, 20, 15)
    elif name == "audio":
        painter.drawLine(10, 17, 10, 5)
        painter.drawLine(10, 5, 20, 3)
        painter.drawLine(20, 3, 20, 15)
        painter.drawEllipse(QRectF(3, 15, 7, 5))
        painter.drawEllipse(QRectF(13, 13, 7, 5))
    elif name == "video":
        painter.drawRoundedRect(QRectF(3, 5, 18, 15), 3, 3)
        painter.drawLine(3, 10, 21, 10)
        painter.drawLine(8, 5, 8, 10)
        painter.drawLine(16, 5, 16, 10)
    elif name == "cover":
        painter.drawRoundedRect(QRectF(3, 4, 18, 16), 3, 3)
        painter.drawEllipse(QRectF(7, 7, 3, 3))
        painter.drawLine(4, 17, 10, 12)
        painter.drawLine(10, 12, 16, 18)
        painter.drawLine(14, 15, 18, 11)
        painter.drawLine(18, 11, 21, 14)
    elif name == "queue":
        for y in (6, 12, 18):
            painter.drawLine(8, y, 21, y)
            painter.drawPoint(3, y)
    elif name == "link":
        painter.translate(12, 12)
        painter.rotate(-42)
        painter.drawRoundedRect(QRectF(-10, -4, 12, 8), 4, 4)
        painter.drawRoundedRect(QRectF(-2, -4, 12, 8), 4, 4)
    elif name == "close":
        painter.drawLine(6, 6, 18, 18)
        painter.drawLine(6, 18, 18, 6)
    elif name == "more":
        for x in (5, 12, 19):
            painter.drawEllipse(QRectF(x - 0.7, 11.3, 1.4, 1.4))
    elif name == "settings":
        painter.drawEllipse(QRectF(5, 5, 14, 14))
        painter.drawEllipse(QRectF(9, 9, 6, 6))
        for step in range(8):
            angle = step * math.pi / 4
            painter.drawLine(int(12 + 8 * math.cos(angle)), int(12 + 8 * math.sin(angle)),
                             int(12 + 10 * math.cos(angle)), int(12 + 10 * math.sin(angle)))
    elif name == "clear":
        painter.drawLine(4, 7, 20, 7)
        painter.drawLine(6, 7, 7, 21)
        painter.drawLine(7, 21, 17, 21)
        painter.drawLine(17, 21, 18, 7)
        painter.drawLine(9, 4, 15, 4)
        painter.drawLine(10, 11, 10, 17)
        painter.drawLine(14, 11, 14, 17)
    elif name == "folder":
        painter.drawRoundedRect(QRectF(3, 7, 18, 13), 2, 2)
        painter.drawLine(3, 7, 3, 4)
        painter.drawLine(3, 4, 10, 4)
        painter.drawLine(10, 4, 13, 7)
    else:
        painter.drawArc(QRectF(4, 4, 16, 16), 45 * 16, 280 * 16)
        painter.drawLine(18, 3, 20, 7)
        painter.drawLine(20, 7, 15, 7)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


STYLE = """
* { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; color: #182230; }
QMainWindow, QWidget#root, QWidget#page, QWidget#resultsPanel { background: #f8fafc; }
QFrame#sidebar { background: #fff; border-right: 1px solid #edf0f4; }
QFrame#inputPanel { background: white; border-bottom: 1px solid #f0f2f6; }
QFrame#destinationBar { background: #fff; border-top: 1px solid #e8edf3; }
QFrame#card { background: white; border: 1px solid #e7edf4; border-radius: 10px; }
QFrame#emptyState { background: transparent; }
QLabel { background: transparent; border: none; }
QLabel#muted { color: #7b8797; font-size: 12px; }
QLabel#title { font-size: 20px; font-weight: 650; }
QLabel#section { font-size: 15px; font-weight: 600; }
QLabel#brand { font-size: 19px; font-weight: 700; }
QLabel#emptyTitle { color: #64748b; font-size: 15px; padding: 10px; }
QPushButton { background: white; border: 1px solid #dde3eb; border-radius: 7px; padding: 8px 12px; }
QPushButton:hover { background: #eff6ff; border-color: #b6cdfa; }
QPushButton:pressed { background: #dbeafe; }
QPushButton:disabled { color: #a3acb9; background: #f5f7fa; border-color: #e7ebf1; }
QPushButton#primary, QToolButton#extractButton { background: #1d4ed8; color: white; border: 1px solid #1d4ed8; border-radius: 7px; font-weight: 600; padding: 9px 15px; }
QPushButton#primary:hover, QToolButton#extractButton:hover { background: #1e40af; }
QPushButton#primary:disabled, QToolButton#extractButton:disabled { color: white; background: #96b4f5; border-color: #96b4f5; }
QToolButton#extractButton::menu-button { border-left: 1px solid #7798ea; width: 29px; }
QToolButton#extractButton::menu-arrow { image: url(ARROW_ASSET); width: 12px; height: 12px; }
QPushButton#nav { text-align: left; border: none; background: transparent; color: #475569; padding: 11px 12px; }
QPushButton#nav:hover { background: #f1f5f9; }
QPushButton#nav:checked { background: #dbeafe; color: #1d4ed8; font-weight: 600; }
QPushButton#small { padding: 5px 9px; font-size: 12px; }
QToolButton { border: none; background: transparent; border-radius: 6px; padding: 7px; }
QToolButton:hover { background: #eaf1ff; }
QToolButton#iconButton::menu-indicator { image: none; }
QToolButton#resultDownload::menu-indicator { image: none; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background: white; border: 1px solid #dce2eb; border-radius: 7px; padding: 8px 10px; selection-background-color: #bfdbfe; }
QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #6495ed; }
QPlainTextEdit#linkInput { padding: 10px 12px; }
QComboBox { min-height: 19px; padding-right: 24px; }
QComboBox::drop-down { border: none; width: 23px; }
QComboBox::down-arrow { image: url(ARROW_DARK_ASSET); width: 11px; height: 11px; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #cbd5e1; border-radius: 4px; background: white; }
QCheckBox::indicator:checked { background: #2563eb; border: 1px solid #2563eb; image: url(CHECK_ASSET); }
QCheckBox::indicator:indeterminate { background: #2563eb; border: 1px solid #2563eb; image: url(MINUS_ASSET); }
QProgressBar { background: #e8eef8; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }
QProgressBar::chunk { background: #3b82f6; border-radius: 3px; }
QTableWidget { background: white; alternate-background-color: #fbfdff; border: 1px solid #e9edf3; border-radius: 9px; gridline-color: #f1f4f8; outline: none; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #f1f4f8; }
QTableWidget::item:selected { background: #eff6ff; color: #172554; }
QHeaderView::section { background: #fdfefe; border: none; border-bottom: 1px solid #edf0f5; padding: 12px 7px; color: #8290a2; font-size: 12px; }
QMenu { background: white; border: 1px solid #dde5ef; padding: 5px; }
QMenu::item { padding: 7px 19px; border-radius: 4px; }
QMenu::item:selected { background: #eff6ff; color: #1d4ed8; }
QMenu::separator { height: 1px; background: #edf0f5; margin: 4px 7px; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #d4dce8; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { background: #fff; color: #8390a1; font-size: 11px; }
"""
for placeholder, filename in (("CHECK_ASSET", "check.svg"), ("MINUS_ASSET", "minus.svg"),
                              ("ARROW_ASSET", "chevron.svg"), ("ARROW_DARK_ASSET", "chevron-dark.svg")):
    STYLE = STYLE.replace(placeholder, '"' + (Path(__file__).with_name("assets") / filename).as_posix() + '"')
