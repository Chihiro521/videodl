from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QFont, QFontDatabase
from pathlib import Path


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
* { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; color: #222631; }
QMainWindow, QWidget#root, QWidget#page { background: #f7f8fa; }
QFrame#sidebar { background: #ffffff; border-right: 1px solid #e9ebef; }
QFrame#card { background: white; border: 1px solid #e6e8ed; border-radius: 16px; }
QFrame#option { background: #ffffff; border: 1px solid #e6e8ed; border-radius: 12px; }
QLabel { background: transparent; border: none; }
QLabel#muted { color: #818795; font-size: 12px; }
QLabel#title { font-size: 25px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#section { font-size: 15px; font-weight: 600; }
QLabel#brand { font-size: 18px; font-weight: 700; }
QLabel#badge { color: #7162aa; background: #f0ecfa; border-radius: 9px; padding: 4px 9px; font-size: 11px; }
QPushButton { background: white; border: 1px solid #e1e4ea; border-radius: 9px; padding: 9px 14px; }
QPushButton:hover { background: #f3f2f8; border-color: #c9c1df; }
QPushButton:disabled { color: #a9aeba; background: #f1f2f5; border-color: #e6e8ed; }
QPushButton#primary { background: #24232c; color: white; border: none; padding: 11px 20px; font-weight: 600; }
QPushButton#primary:hover { background: #494250; }
QPushButton#primary:disabled { background: #b7b5bf; }
QPushButton#nav { text-align: left; border: none; background: transparent; color: #777e8b; padding: 12px 14px; }
QPushButton#nav:checked { background: #f0edf8; color: #675591; font-weight: 600; }
QPushButton#small { padding: 5px 9px; font-size: 12px; border-radius: 6px; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background: #fbfcfd; border: 1px solid #e3e6ed; border-radius: 9px; padding: 9px 12px; selection-background-color: #d6cce9; }
QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #9884bc; }
QComboBox { min-height: 18px; }
QComboBox::drop-down { border: none; width: 24px; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 19px; height: 19px; border: 1px solid #d2d5dd; border-radius: 6px; background: white; }
QCheckBox::indicator:checked { background: #79649f; border: 1px solid #79649f; image: url(CHECK_ASSET); }
QProgressBar { background: #eeedf2; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }
QProgressBar::chunk { background: #8b74b3; border-radius: 4px; }
QTableWidget { background: white; border: 1px solid #e7e9ee; border-radius: 12px; gridline-color: #f1f2f5; outline: none; }
QTableWidget::item { padding: 10px; border-bottom: 1px solid #f0f1f4; }
QTableWidget::item:selected { background: #f4f0fa; color: #332b43; }
QHeaderView::section { background: #fafbfc; border: none; border-bottom: 1px solid #e9ebef; padding: 12px 8px; color: #8a909c; font-size: 12px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 3px; }
QScrollBar::handle:vertical { background: #d9dbe2; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { background: #f7f8fa; color: #777e8b; font-size: 12px; }
"""
STYLE = STYLE.replace("CHECK_ASSET", (Path(__file__).with_name("assets") / "check.svg").as_posix())
