"""Presentation-only source headers for the shared media result table."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from .theme import colors
from .widgets import button


class ElidedLabel(QLabel):
    def __init__(self, text):
        super().__init__()
        self.full_text = text
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setToolTip(text)
        self.setAccessibleName(text)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideMiddle, self.width()))


class SourceHeader(QFrame):
    def __init__(self, window, url):
        super().__init__()
        self.setObjectName("sourceGroup")
        self.signature = None
        box = QHBoxLayout(self)
        box.setContentsMargins(9, 5, 9, 5)
        box.setSpacing(12)
        self.number = QLabel()
        self.number.setObjectName("sourceNumber")
        self.number.setFixedWidth(30)
        box.addWidget(self.number)
        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(3)
        self.address = ElidedLabel(url)
        info.addWidget(self.address)
        self.detail = QLabel()
        self.detail.setObjectName("sourceState")
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        self.detail.setMinimumWidth(0)
        self.detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addWidget(self.detail)
        box.addLayout(info, 1)
        self.select = QCheckBox("选择本组")
        self.select.setTristate(True)
        self.select.setAccessibleName(f"选择本组：{url}")
        self.select.clicked.connect(lambda checked: window.select_source(url, checked))
        box.addWidget(self.select)
        self.retry = button("重试", lambda: window.retry_source(url), "small")
        self.retry.setAccessibleName(f"重试链接：{url}")
        box.addWidget(self.retry)
        self.download = button("下载本组", lambda: window.download_source(url), "small")
        self.download.setAccessibleName(f"下载本组：{url}")
        box.addWidget(self.download)

    def update_summary(self, number, text, state, detail=""):
        signature = (number, text, state, detail, colors()["error"])
        if signature == self.signature:
            return
        self.signature = signature
        self.number.setText(f"{number:02}")
        self.detail.setText(text)
        self.detail.setToolTip(detail or text)
        self.detail.setStyleSheet("color: " + colors()["error" if state == "failed" else "muted"] + "; font-size: 12px;")
        self.retry.setVisible(state in ("failed", "cancelled"))

    def update_selection(self, rows, available):
        checked = sum(bool(row.get("checked")) for row in rows)
        state = Qt.CheckState.Unchecked if not checked else Qt.CheckState.Checked if checked == len(rows) else Qt.CheckState.PartiallyChecked
        self.select.blockSignals(True)
        self.select.setCheckState(state)
        self.select.blockSignals(False)
        self.select.setEnabled(bool(rows))
        self.download.setEnabled(available)
