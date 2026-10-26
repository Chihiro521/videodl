from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QAbstractButton
from pathlib import Path
import math
from functools import lru_cache


LIGHT = dict(bg="#ffffff", surface="#f3f3f3", hover="#e9e9e9", line="#dedede", border="#a9a9a9",
             text="#151515", muted="#707070", primary="#101010", on_primary="#ffffff",
             selection="#ededed", disabled="#969696", done="#267752", error="#b52c3a")
DARK = dict(bg="#111111", surface="#1e1e1e", hover="#2d2d2d", line="#353535", border="#686868",
            text="#efefef", muted="#a5a5a5", primary="#efefef", on_primary="#111111",
            selection="#292929", disabled="#767676", done="#7bdbab", error="#ff8c98")


def colors():
    return getattr(QApplication.instance(), "desktop_colors", LIGHT)


def apply_theme(application, mode="system"):
    dark = mode == "dark" or (mode == "system" and application.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    current = DARK if dark else LIGHT
    if getattr(application, "desktop_theme", None) == ("dark" if dark else "light"):
        return current
    # Qt's offscreen Windows plugin does not enumerate installed fonts.
    if not QFontDatabase.families():
        for name in ("consola.ttf", "consolab.ttf", "msyh.ttc", "msyhbd.ttc", "segoeui.ttf"):
            path = Path("C:/Windows/Fonts") / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
    font = QFont()
    font.setFamilies(["Consolas", "Microsoft YaHei UI"])
    font.setPixelSize(14)
    application.setFont(font)
    if application.style().objectName().lower() != "fusion":
        application.setStyle("Fusion")
    application.desktop_colors = current
    application.desktop_theme = "dark" if dark else "light"
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, current["bg"]), (QPalette.ColorRole.WindowText, current["text"]),
                        (QPalette.ColorRole.Base, current["bg"]), (QPalette.ColorRole.Text, current["text"]),
                        (QPalette.ColorRole.Button, current["surface"]), (QPalette.ColorRole.ButtonText, current["text"]),
                        (QPalette.ColorRole.Highlight, current["primary"]), (QPalette.ColorRole.HighlightedText, current["on_primary"]),
                        (QPalette.ColorRole.ToolTipBase, current["surface"]), (QPalette.ColorRole.ToolTipText, current["text"])):
        palette.setColor(role, QColor(color))
    application.setPalette(palette)
    application.setStyleSheet(build_style(current, dark))
    return current


def icon(name, color=None, size=22):
    return _draw_icon(name, color or colors()["text"], size)


def set_symbol(widget, name):
    widget.setProperty("symbol", name)
    current = colors()
    active = widget.objectName() in ("primary", "extractButton") or (widget.objectName() == "nav" and widget.isChecked())
    widget.setIcon(icon(name, current["on_primary"] if active else current["text"]))


def refresh_icons(root):
    for widget in root.findChildren(QAbstractButton):
        if name := widget.property("symbol"):
            set_symbol(widget, name)


@lru_cache(maxsize=128)
def _draw_icon(name, color, size):
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
    elif name == "paste":
        painter.drawRoundedRect(QRectF(5, 5, 14, 16), 2, 2)
        painter.drawRoundedRect(QRectF(8, 3, 8, 5), 1, 1)
    else:
        painter.drawArc(QRectF(4, 4, 16, 16), 45 * 16, 280 * 16)
        painter.drawLine(18, 3, 20, 7)
        painter.drawLine(20, 7, 15, 7)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def build_style(current, dark=False):
    style = """
* { font-family: 'Consolas', 'Microsoft YaHei UI'; font-size: 14px; color: @text@; }
QMainWindow, QDialog, QWidget#root, QWidget#page, QWidget#resultsPanel { background: @bg@; }
QFrame#sidebar { background: @surface@; border-right: 1px solid @line@; }
QFrame#inputPanel, QFrame#emptyState { background: transparent; border: none; }
QFrame#linkBox { background: @bg@; border: 1px solid @border@; border-radius: 9px; }
QFrame#destinationBar { background: @bg@; border-top: 1px solid @line@; }
QFrame#card { background: @bg@; border: 1px solid @line@; border-radius: 8px; }
QFrame#segmented { background: @surface@; border: none; border-radius: 8px; }
QFrame#sourceGroup { background: @surface@; border: none; border-top: 1px solid @line@; border-bottom: 1px solid @line@; }
QLabel#sourceNumber { color: @muted@; font-size: 15px; font-weight: 600; }
QLabel { background: transparent; border: none; }
QLabel#muted { color: @muted@; font-size: 12px; }
QLabel#title { font-size: 22px; font-weight: 600; }
QLabel#section { font-size: 15px; font-weight: 600; }
QLabel#brand { font-size: 24px; font-weight: 600; }
QLabel#sidebarBrand { font-size: 19px; font-weight: 600; }
QLabel#emptyTitle { font-size: 15px; padding: 7px; }
QPushButton { background: @surface@; border: 1px solid @line@; border-radius: 7px; padding: 8px 12px; }
QPushButton:hover { background: @hover@; border-color: @border@; }
QPushButton:pressed { background: @selection@; }
QPushButton:disabled { color: @disabled@; border-color: @line@; }
QPushButton#primary { background: @primary@; color: @on_primary@; border-color: @primary@; }
QPushButton#primary:hover { border-color: @border@; }
QPushButton#primary:disabled { background: @hover@; color: @disabled@; border-color: @line@; }
QPushButton#small { padding: 5px 9px; font-size: 12px; }
QPushButton#segment { background: transparent; border: none; padding: 6px 11px; border-radius: 6px; font-size: 13px; }
QPushButton#segment:hover { background: @hover@; }
QPushButton#segment:checked { background: @primary@; color: @on_primary@; }
QToolButton { border: none; background: transparent; border-radius: 7px; padding: 7px; }
QToolButton:hover { background: @hover@; }
QToolButton#nav { font-size: 11px; color: @muted@; padding: 9px 1px; border-radius: 9px; }
QToolButton#nav:checked { background: @primary@; color: @on_primary@; }
QToolButton::menu-indicator { image: none; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background: @surface@; border: 1px solid @line@; border-radius: 7px; padding: 7px 9px; selection-background-color: @primary@; selection-color: @on_primary@; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: @border@; }
QPlainTextEdit#linkInput { background: transparent; border: none; padding: 9px 10px; }
QComboBox { min-height: 20px; padding-right: 24px; }
QComboBox#qualityChoice { min-height: 18px; padding: 4px 8px; padding-right: 23px; font-size: 13px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url(@arrow@); width: 11px; height: 11px; }
QComboBox QAbstractItemView { background: @surface@; color: @text@; border: 1px solid @border@; selection-background-color: @primary@; selection-color: @on_primary@; padding: 4px; }
QCheckBox { spacing: 7px; background: transparent; font-size: 13px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid @border@; border-radius: 4px; background: @bg@; }
QCheckBox::indicator:checked { background: @primary@; border-color: @primary@; image: url(@check@); }
QCheckBox::indicator:indeterminate { background: @primary@; border-color: @primary@; image: url(@minus@); }
QCheckBox:disabled { color: @disabled@; }
QProgressBar { background: @line@; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }
QProgressBar::chunk { background: @text@; border-radius: 2px; }
QTableWidget { background: @bg@; border: none; gridline-color: @line@; outline: none; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid @line@; }
QTableWidget::item:selected { background: @selection@; color: @text@; }
QHeaderView::section { background: @bg@; border: none; border-bottom: 1px solid @line@; padding: 10px 7px; color: @muted@; font-size: 12px; }
QMenu { background: @surface@; color: @text@; border: 1px solid @line@; padding: 5px; }
QMenu::item { padding: 7px 19px; border-radius: 5px; }
QMenu::item:selected { background: @primary@; color: @on_primary@; }
QMenu::item:disabled { color: @disabled@; }
QMenu::separator { height: 1px; background: @line@; margin: 4px 7px; }
QScrollArea { border: none; background: @bg@; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: @border@; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { background: @bg@; color: @muted@; font-size: 11px; }
QToolTip { background: @surface@; color: @text@; border: 1px solid @border@; padding: 5px; }
"""
    assets = Path(__file__).with_name("assets")
    values = {**current, "arrow": assets / ("chevron.svg" if dark else "chevron-dark.svg"),
              "check": assets / ("check-dark.svg" if dark else "check.svg"),
              "minus": assets / ("minus-dark.svg" if dark else "minus.svg")}
    for name, value in values.items():
        style = style.replace("@" + name + "@", '"' + value.as_posix() + '"' if isinstance(value, Path) else value)
    return style
