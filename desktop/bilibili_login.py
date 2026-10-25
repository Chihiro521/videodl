"""Nonblocking native QR dialog; login material never enters worker IPC files."""

import time

import qrcode
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from .bilibili_auth import QRLogin, save_cookies


class LoginThread(QThread):
    qr = Signal(object)
    state = Signal(str)
    logged_in = Signal()

    def run(self):
        client = QRLogin()
        try:
            qr = qrcode.QRCode(border=4)
            qr.add_data(client.generate())
            qr.make(fit=True)
            self.qr.emit(qr.get_matrix())
            deadline = time.monotonic() + 180
            while not self.isInterruptionRequested() and time.monotonic() < deadline:
                code, cookies = client.poll()
                if self.isInterruptionRequested():
                    return
                if code == 0:
                    save_cookies(cookies)
                    self.logged_in.emit()
                    return
                if code == 86038:
                    self.state.emit("二维码已过期，请点击重新获取。")
                    return
                self.state.emit("已扫码，请在手机上确认登录。" if code == 86090 else "请用哔哩哔哩 App 扫码登录。")
                for _ in range(20):
                    if self.isInterruptionRequested():
                        return
                    self.msleep(100)
            if not self.isInterruptionRequested():
                self.state.emit("二维码已过期，请点击重新获取。")
        except Exception:
            self.state.emit("登录未完成，请检查网络后重新获取二维码。")
        finally:
            client.session.close()


class LoginDialog(QDialog):
    logged_in = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("B站登录 · 获取高清画质")
        self.setMinimumWidth(360)
        self.thread = None
        self.pending_close = False
        layout = QVBoxLayout(self)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image)
        self.status = QLabel("正在获取二维码…")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)
        tip = QLabel("登录后自动获取账号可访问的最高画质。\n登录失效时重新扫码即可。")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tip)
        self.retry = QPushButton("重新获取二维码")
        self.retry.clicked.connect(self.start)
        layout.addWidget(self.retry)
        self.start()

    def start(self):
        if self.thread and self.thread.isRunning():
            return
        self.image.clear()
        self.status.setText("正在获取二维码…")
        self.retry.setEnabled(False)
        self.thread = LoginThread(self)
        self.thread.qr.connect(self.show_qr)
        self.thread.state.connect(self.status.setText)
        self.thread.logged_in.connect(self.success)
        self.thread.finished.connect(self.finished_login)
        self.thread.start()

    def show_qr(self, matrix):
        side = len(matrix)
        image = QImage(side, side, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    image.setPixelColor(x, y, QColor("black"))
        self.image.setPixmap(QPixmap.fromImage(image).scaled(side * 5, side * 5))

    def success(self):
        self.image.clear()
        self.status.setText("登录成功，之后提取会自动获取高清画质。")
        self.logged_in.emit()

    def finished_login(self):
        self.retry.setEnabled(True)
        if self.pending_close:
            self.close()

    def reject(self):
        self.close()

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.thread.requestInterruption()
            self.pending_close = True
            self.hide()
            event.ignore()
        else:
            event.accept()
