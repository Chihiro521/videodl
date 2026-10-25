"""Native Windows interface, persistent batch queue, and release discovery."""

import base64
import os
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)

from . import REPOSITORY, __version__
from .process import Worker
from .storage import data_dir, load_json, parse_links, public_host, save_json
from .theme import STYLE, icon, apply_theme
from .updates import build_info

STATES = {"waiting": "等待中", "active": "处理中", "done": "已完成", "failed": "失败", "partial": "部分完成", "cancelled": "已取消", "interrupted": "已中断"}
KINDS = {"cover": "封面", "audio": "音频", "video": "视频"}


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
        widget.setIcon(icon(symbol))
        widget.setIconSize(QSize(18, 18))
    return widget


def card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 16, 22, 16)
    layout.setSpacing(11)
    return frame, layout


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoDL Desktop")
        self.setWindowIcon(icon("download", "#79649f", 48))
        self.resize(1180, 860)
        self.setMinimumSize(940, 690)
        self.store = data_dir()
        self.settings = load_json(self.store / "settings.json", {})
        self.jobs = load_json(self.store / "queue.json", [])
        if not isinstance(self.jobs, list):
            self.jobs = []
        self.jobs = [j for j in self.jobs if isinstance(j, dict) and all(k in j for k in ("id", "url", "options", "output", "status"))]
        for job in self.jobs:
            if job["status"] in ("active", "waiting"):
                job["status"] = "interrupted"
                job["detail"] = "上次退出时未完成，点击重试可重新解析下载。"
        self.running = {}
        self.preview = None
        self.preview_url = ""
        self.preview_worker = None
        self.update_worker = None
        self.closing = False
        self.paused = False
        self.release_url = f"https://github.com/{REPOSITORY}/releases"
        self._build()
        self.render_queue()
        self.persist()

    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(194)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 29, 18, 22)
        side.setSpacing(8)
        brand = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(icon("download", "#79649f", 28).pixmap(28, 28))
        brand.addWidget(mark)
        brand.addWidget(label("VideoDL", "brand"))
        brand.addStretch()
        side.addLayout(brand)
        side.addWidget(label("DESKTOP  /  视频与声音", "muted"))
        side.addSpacing(33)
        self.nav = []
        self.pages = QStackedWidget()
        for index, (text, symbol) in enumerate((("新建下载", "download"), ("下载队列", "queue"), ("版本与更新", "update"))):
            nav = button(text, lambda _, i=index: self.navigate(i), "nav", symbol)
            nav.setCheckable(True)
            self.nav.append(nav)
            side.addWidget(nav)
        side.addStretch()
        side.addWidget(label("上游内核 · 独立桌面界面", "muted"))
        side.addWidget(label(f"桌面版 {__version__}", "muted"))
        outer.addWidget(sidebar)
        outer.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.pages.addWidget(self._new_page())
        self.pages.addWidget(self._queue_page())
        self.pages.addWidget(self._updates_page())
        self.navigate(0)
        self.statusBar().showMessage("准备就绪 · 粘贴链接开始")

    def page(self, title, subtitle):
        content = QWidget()
        content.setObjectName("page")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)
        layout.addWidget(label(title, "title"))
        layout.addWidget(label(subtitle, "muted"))
        return content, layout

    def _new_page(self):
        page, layout = self.page("下载工作台", "保存喜欢的画面，也留下声音。")
        frame, box = card()
        head = QHBoxLayout()
        head.addWidget(label("粘贴视频链接", "section"))
        head.addStretch()
        head.addWidget(button("粘贴", self.paste, "small"))
        box.addLayout(head)
        self.links = QPlainTextEdit()
        self.links.setPlaceholderText("粘贴 Bilibili、抖音、YouTube 等链接\n批量添加时，每行一个链接，也支持直接粘贴分享文本")
        self.links.setFixedHeight(82)
        box.addWidget(self.links)
        parse_row = QHBoxLayout()
        self.common = QCheckBox("启用上游通用解析")
        self.common.setChecked(bool(self.settings.get("common", True)))
        parse_row.addWidget(self.common)
        parse_row.addStretch()
        self.parse_button = button("解析预览", self.start_preview, "primary")
        parse_row.addWidget(self.parse_button)
        box.addLayout(parse_row)
        preview_row = QHBoxLayout()
        preview_row.setSpacing(15)
        self.thumbnail = QLabel()
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setFixedSize(140, 79)
        self.thumbnail.setStyleSheet("background:#f0eff4; border-radius:10px;")
        self.thumbnail.setPixmap(icon("video", "#b3adc0", 32).pixmap(32, 32))
        preview_row.addWidget(self.thumbnail)
        meta = QVBoxLayout()
        self.preview_title = label("解析后在这里预览", "section")
        self.preview_meta = label("标题、封面和格式由上游解析器返回", "muted")
        meta.addWidget(self.preview_title)
        meta.addWidget(self.preview_meta)
        self.parts = QComboBox()
        self.parts.hide()
        meta.addWidget(self.parts)
        preview_row.addLayout(meta, 1)
        box.addLayout(preview_row)
        layout.addWidget(frame)
        options_frame, options_box = card()
        heading = QHBoxLayout()
        heading.addWidget(label("选择下载内容", "section"))
        heading.addStretch()
        heading.addWidget(label("可同时选择多项", "muted"))
        options_box.addLayout(heading)
        self.options = {}
        for key, title, description in (("cover", "视频封面", "保存原始封面图片"), ("audio", "独立音频", "优先下载独立音轨，否则提取原始音频"), ("video", "视频", "保存解析器提供的视频，可与音频、封面一起下载")):
            row = QFrame()
            row.setObjectName("option")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(15, 9, 15, 9)
            symbol = QLabel()
            symbol.setPixmap(icon(key, "#857397", 24).pixmap(24, 24))
            row_layout.addWidget(symbol)
            text = QVBoxLayout()
            text.setSpacing(3)
            text.addWidget(label(title, "section"))
            text.addWidget(label(description, "muted"))
            row_layout.addLayout(text, 1)
            check = QCheckBox()
            check.setAccessibleName(title)
            check.setChecked(self.settings.get("options", {}).get(key, True))
            self.options[key] = check
            row_layout.addWidget(check)
            options_box.addWidget(row)
        options_box.addWidget(label("视频画质与格式以解析结果为准 · 音频提取保留原始编码", "muted"))
        layout.addWidget(options_frame)
        destination = QHBoxLayout()
        self.destination = QLineEdit(self.settings.get("output", str(Path.home() / "Downloads" / "VideoDL")))
        self.destination.setPlaceholderText("保存文件夹")
        destination.addWidget(self.destination, 1)
        destination.addWidget(button("选择目录", self.choose_directory, symbol="folder"))
        layout.addLayout(destination)
        footer = QHBoxLayout()
        self.link_count = label("支持批量添加 · 每个任务保存独立的下载选项", "muted")
        footer.addWidget(self.link_count, 1)
        footer.addWidget(button("加入下载队列", self.add_jobs, "primary", "download"))
        layout.addLayout(footer)
        self.message = label("", "muted")
        layout.addWidget(self.message)
        layout.addStretch()
        self.links.textChanged.connect(self.update_link_count)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _queue_page(self):
        page, layout = self.page("下载队列", "任务在后台处理，已完成的文件会保留在保存目录。")
        toolbar = QHBoxLayout()
        self.queue_summary = label("暂无任务", "muted")
        toolbar.addWidget(self.queue_summary, 1)
        toolbar.addWidget(label("同时下载", "muted"))
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 3)
        self.concurrency.setValue(int(self.settings.get("concurrency", 1)))
        self.concurrency.valueChanged.connect(self.pump)
        toolbar.addWidget(self.concurrency)
        self.pause_button = button("暂停队列", self.toggle_pause)
        toolbar.addWidget(self.pause_button)
        toolbar.addWidget(button("重试未完成", self.retry_unfinished))
        toolbar.addWidget(button("清理记录", self.clear_finished))
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["任务", "下载内容", "状态", "进度", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 106), (2, 84), (3, 120), (4, 140)):
            self.table.setColumnWidth(col, width)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)
        layout.addWidget(label("重试会重新解析链接；关闭窗口后，未完成的任务可在下次启动时重试。", "muted"))
        return page

    def _updates_page(self):
        page, layout = self.page("版本与更新", "桌面版发布经过验证的上游适配，更新记录可以追溯。")
        frame, box = card()
        box.addWidget(label("VideoDL Desktop", "brand"))
        info = build_info()
        box.addWidget(label(f"桌面版 {__version__}  ·  上游内核 {info.get('core_version', '未知')}"))
        box.addWidget(label("当前适配的上游提交：" + info.get("upstream_revision", "未知")[:12], "muted"))
        self.update_status = label("点击检查以获取桌面发行版和上游状态。", "muted")
        box.addWidget(self.update_status)
        row = QHBoxLayout()
        self.update_button = button("检查更新", self.start_updates, "primary")
        row.addWidget(self.update_button)
        row.addWidget(button("打开下载页面", lambda: QDesktopServices.openUrl(QUrl(self.release_url))))
        row.addStretch()
        box.addLayout(row)
        layout.addWidget(frame)
        frame, box = card()
        box.addWidget(label("维护方式", "section"))
        box.addWidget(label("上游更新 → 同步 PR → 适配与测试 → 桌面版发布"))
        box.addWidget(label("版本标签以 desktop-v 开头。原项目、桌面界面与用户下载数据分别管理。", "muted"))
        row = QHBoxLayout()
        row.addWidget(button("项目主页", lambda: QDesktopServices.openUrl(QUrl(f"https://github.com/{REPOSITORY}/tree/desktop"))))
        row.addWidget(button("打开本地数据目录", lambda: self.open_folder(str(self.store))))
        row.addStretch()
        box.addLayout(row)
        layout.addWidget(frame)
        layout.addStretch()
        return page

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)

    def say(self, message):
        self.message.setText(message)
        self.statusBar().showMessage(message, 15000)

    def paste(self):
        self.links.setPlainText(QApplication.clipboard().text())

    def update_link_count(self):
        count = len(parse_links(self.links.toPlainText()))
        self.link_count.setText(f"已识别 {count} 个链接" if count else "支持批量添加 · 每个任务保存独立的下载选项")

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择保存目录", self.destination.text())
        if directory:
            self.destination.setText(directory)
            self.persist()

    def output_directory(self):
        text = self.destination.text().strip()
        if not text:
            self.say("请先选择保存目录。")
            return None
        path = Path(text).expanduser()
        if not path.is_absolute():
            self.say("请选择完整的保存目录路径。")
            return None
        return str(path)

    def start_preview(self):
        urls = parse_links(self.links.toPlainText())
        output = self.output_directory()
        if not urls or not output:
            if not urls:
                self.say("请先粘贴有效的视频链接。")
            return
        if self.preview_worker:
            return
        self.preview = None
        self.preview_url = urls[0]
        self.parts.clear()
        self.parts.hide()
        self.thumbnail.setPixmap(icon("video", "#b3adc0", 32).pixmap(32, 32))
        self.preview_title.setText("正在解析…")
        self.preview_meta.setText("批量输入时，先预览第一个链接。")
        self.parse_button.setEnabled(False)
        self.parse_button.setText("解析中…")
        worker = Worker({"action": "parse", "url": urls[0], "output": output, "common": self.common.isChecked()}, self)
        self.preview_worker = worker
        worker.event.connect(self.preview_event)
        worker.finished.connect(self.preview_finished)
        worker.start()

    def preview_event(self, event):
        if event["event"] == "result":
            self.preview = event
            items = event.get("items", [])
            if items:
                self.preview_title.setText(items[0]["title"])
                source = items[0]["source"].removesuffix("VideoClient")
                self.preview_meta.setText(f"{source}  ·  {items[0]['ext'].upper()}  ·  共 {len(items)} 个条目")
                if len(items) > 1:
                    self.parts.addItem(f"下载全部 {len(items)} 个条目", None)
                    for item in items:
                        self.parts.addItem(item["title"], [item["index"]])
                    self.parts.show()
            if event.get("thumbnail"):
                image = QPixmap()
                if image.loadFromData(base64.b64decode(event["thumbnail"])):
                    self.thumbnail.setPixmap(image.scaled(self.thumbnail.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.say("解析完成，可选择内容并加入队列。")
        elif event["event"] == "error":
            self.preview_title.setText("解析未完成")
            self.preview_meta.setText(event["message"])
            self.say(event["message"])
        elif event["event"] == "progress":
            self.statusBar().showMessage(event.get("detail", "正在解析"))

    def preview_finished(self, code):
        self.parse_button.setEnabled(True)
        self.parse_button.setText("解析预览")
        if not self.preview and code:
            self.preview_title.setText("解析未完成")
        self.preview_worker.deleteLater()
        self.preview_worker = None

    def add_jobs(self):
        urls = parse_links(self.links.toPlainText())
        output = self.output_directory()
        options = {k: check.isChecked() for k, check in self.options.items()}
        if not urls or not output or not any(options.values()):
            self.say("请提供有效链接、保存目录，并选择至少一种下载内容。")
            return
        if len(urls) > 200:
            self.say("单次最多添加 200 个链接，请分批添加。")
            return
        added = 0
        for url in urls:
            if any(j["url"] == url and j["options"] == options and j["output"] == output and j["status"] in ("waiting", "active") for j in self.jobs):
                continue
            preview = self.preview if url == self.preview_url else None
            self.jobs.append({"id": uuid.uuid4().hex, "url": url, "title": preview["items"][0]["title"] if preview and preview.get("items") else public_host(url),
                              "options": options.copy(), "output": output, "common": self.common.isChecked(),
                              "indices": self.parts.currentData() if preview and self.parts.count() else None,
                              "status": "waiting", "percent": 0, "detail": "等待开始", "files": [], "created": datetime.now().isoformat(timespec="seconds")})
            added += 1
        self.persist()
        self.render_queue()
        self.navigate(1)
        self.say(f"已加入 {added} 个任务。")
        self.pump()

    def pump(self, *_):
        if self.closing or self.paused:
            return
        for job in self.jobs:
            if len(self.running) >= self.concurrency.value():
                break
            if job["status"] != "waiting":
                continue
            job["status"] = "active"
            job["detail"] = "正在启动解析器"
            worker = Worker({"action": "download", **{k: job.get(k) for k in ("url", "output", "options", "indices", "common")}}, self)
            self.running[job["id"]] = worker
            worker.event.connect(lambda e, j=job: self.job_event(j, e))
            worker.finished.connect(lambda code, j=job: self.job_finished(j, code))
            worker.start()
        self.persist()
        self.render_queue()

    def job_event(self, job, event):
        kind = event["event"]
        if kind == "parsed" and event.get("items"):
            job["title"] = event["items"][0]["title"]
            if len(event["items"]) > 1 and job.get("indices") is None:
                job["title"] += f" 等 {len(event['items'])} 个条目"
            self.render_queue()
        elif kind == "progress":
            job["detail"] = event.get("detail", "正在处理")
            job["percent"] = event.get("percent", -1)
            self.update_progress(job)
        elif kind == "file":
            job["files"].append({"path": event["path"], "kind": event["kind"]})
            self.persist()
        elif kind == "result":
            job["status"] = event.get("status", "done")
            job["files"] = event.get("files", job["files"])
            job["detail"] = "；".join(event.get("errors", [])) or "下载完成"
            job["percent"] = 100 if job["status"] == "done" else 0
            self.persist()
            self.render_queue()
        elif kind == "error":
            job["status"] = "partial" if job["files"] else "failed"
            job["detail"] = event["message"]
            job["percent"] = 0
            self.persist()
            self.render_queue()

    def job_finished(self, job, code):
        worker = self.running.pop(job["id"], None)
        if worker and worker.cancelled:
            job["status"] = "cancelled"
            job["detail"] = "任务已取消，已完成文件保留。"
        elif job["status"] == "active":
            job["status"] = "partial" if job["files"] else "failed"
            job["detail"] = "后台进程结束，点击重试可重新解析。"
        if worker:
            worker.deleteLater()
        self.persist()
        self.render_queue()
        if not self.closing:
            QTimer.singleShot(0, self.pump)

    def update_progress(self, job):
        for row, item in enumerate(reversed(self.jobs)):
            if item["id"] == job["id"]:
                progress = self.table.cellWidget(row, 3)
                if isinstance(progress, QProgressBar):
                    percent = job.get("percent", 0)
                    progress.setRange(0, 0 if percent < 0 and job["status"] == "active" else 100)
                    progress.setValue(max(0, percent))
                    progress.setToolTip(job.get("detail", ""))
                title = self.table.item(row, 0)
                if title:
                    title.setToolTip(job.get("detail", ""))
                break

    def render_queue(self):
        self.table.setRowCount(len(self.jobs))
        for row, job in enumerate(reversed(self.jobs)):
            self.table.setRowHeight(row, 72)
            title = QTableWidgetItem(job.get("title", "未命名") + "\n" + public_host(job["url"]))
            title.setToolTip(job.get("detail", ""))
            self.table.setItem(row, 0, title)
            self.table.setItem(row, 1, QTableWidgetItem(" / ".join(KINDS[k] for k, v in job["options"].items() if v and k in KINDS)))
            state = QTableWidgetItem(STATES.get(job["status"], job["status"]))
            state.setToolTip(job.get("detail", ""))
            self.table.setItem(row, 2, state)
            progress = QProgressBar()
            progress.setTextVisible(False)
            self.table.setCellWidget(row, 3, progress)
            self.update_progress(job)
            actions = QWidget()
            actions.setStyleSheet("background:transparent;")
            buttons = QHBoxLayout(actions)
            buttons.setContentsMargins(5, 10, 5, 10)
            buttons.setSpacing(5)
            if job["status"] in ("active", "waiting"):
                buttons.addWidget(button("取消", lambda _, j=job: self.cancel_job(j), "small"))
            elif job["status"] != "done":
                buttons.addWidget(button("重试", lambda _, j=job: self.retry_job(j), "small"))
            if job.get("files"):
                buttons.addWidget(button("文件", lambda _, j=job: self.open_job(j), "small"))
            buttons.addStretch()
            self.table.setCellWidget(row, 4, actions)
        done = sum(j["status"] == "done" for j in self.jobs)
        active = sum(j["status"] == "active" for j in self.jobs)
        waiting = sum(j["status"] == "waiting" for j in self.jobs)
        self.queue_summary.setText(f"共 {len(self.jobs)} 项 · {active} 项处理中 · {waiting} 项等待 · {done} 项完成")

    def cancel_job(self, job):
        if job["id"] in self.running:
            job["detail"] = "正在取消…"
            self.running[job["id"]].cancel()
        else:
            job["status"] = "cancelled"
            job["detail"] = "已从等待队列取消。"
        self.persist()
        self.render_queue()

    def retry_job(self, job):
        if job["id"] in self.running:
            return
        job.update(status="waiting", percent=0, detail="等待重试", files=[])
        self.persist()
        self.pump()

    def retry_unfinished(self):
        for job in self.jobs:
            if job["status"] in ("failed", "partial", "interrupted", "cancelled") and job["id"] not in self.running:
                job.update(status="waiting", percent=0, detail="等待重试", files=[])
        self.persist()
        self.pump()

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.setText("继续队列" if self.paused else "暂停队列")
        self.say("队列已暂停，正在处理的任务会继续完成。" if self.paused else "队列已继续。")
        self.pump()

    def clear_finished(self):
        self.jobs = [j for j in self.jobs if j["status"] in ("active", "waiting") or j["id"] in self.running]
        self.persist()
        self.render_queue()

    def open_folder(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))

    def open_job(self, job):
        paths = [Path(f["path"]) for f in job.get("files", []) if Path(f["path"]).exists()]
        self.open_folder(str(paths[0].parent if paths else Path(job["output"])))

    def start_updates(self):
        if self.update_worker:
            return
        self.update_button.setEnabled(False)
        self.update_status.setText("正在检查 GitHub 发行版和上游状态…")
        worker = Worker({"action": "updates"}, self)
        self.update_worker = worker
        worker.event.connect(self.update_event)
        worker.finished.connect(self.update_finished)
        worker.start()

    def update_event(self, event):
        if event["event"] == "result":
            self.release_url = event["release_url"]
            prefix = "发现新版本" if event["available"] else "当前发行状态"
            self.update_status.setText(f"{prefix}：{event['latest']}\n上游最新提交：{event.get('upstream_revision', '未知')[:12]}\n上游变化经适配验证后，会作为新的桌面版本发布。")
        elif event["event"] == "error":
            self.update_status.setText(event["message"])

    def update_finished(self, code):
        self.update_button.setEnabled(True)
        self.update_worker.deleteLater()
        self.update_worker = None

    def persist(self):
        if not hasattr(self, "destination"):
            return
        self.settings.update(output=self.destination.text(), common=self.common.isChecked(),
                             options={k: v.isChecked() for k, v in self.options.items()}, concurrency=self.concurrency.value())
        try:
            save_json(self.store / "settings.json", self.settings)
            save_json(self.store / "queue.json", self.jobs)
        except OSError:
            self.statusBar().showMessage("本地记录保存失败，请检查数据目录的可写权限。")

    def closeEvent(self, event):
        self.closing = True
        workers = list(self.running.values()) + [w for w in (self.preview_worker, self.update_worker) if w]
        for worker in workers:
            worker.cancel()
        for worker in workers:
            if not worker.process.waitForFinished(4000):
                worker.process.kill()
                worker.process.waitForFinished(1000)
        self.persist()
        event.accept()


def main():
    application = QApplication(sys.argv)
    application.setApplicationName("VideoDL Desktop")
    application.setOrganizationName("VideoDL Desktop")
    apply_theme(application)
    lock = QLockFile(str(data_dir() / "desktop.lock"))
    if not lock.tryLock(0):
        QMessageBox.information(None, "VideoDL Desktop", "程序已在运行，请切换到已打开的窗口。")
        return 0
    window = Window()
    window.show()
    smoke_report = os.environ.get("VIDEODL_GUI_SMOKE_REPORT")
    if smoke_report:
        def capture_smoke():
            path = Path(smoke_report)
            save_json(path, {"visible": window.isVisible(), "width": window.width(), "height": window.height()})
            window.grab().save(str(path.with_suffix(".png")))
            window.close()
        QTimer.singleShot(500, capture_smoke)
    return application.exec()
