"""Page layouts for the single-screen extraction-to-download workflow."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLineEdit, QScrollArea, QSizePolicy, QSpinBox,
    QTableWidget, QVBoxLayout, QWidget)

from . import REPOSITORY, __version__
from .results import KINDS
from .updates import build_info
from .widgets import SegmentedControl, SmoothScroll, button, card, label
from .layouts import build_shell, build_download_page


class WorkbenchPages:
    def _build(self):
        build_shell(self)

    def page(self, title, subtitle=""):
        content = QWidget()
        content.setObjectName("page")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(25, 22, 25, 20)
        layout.setSpacing(16)
        if title:
            layout.addWidget(label(title, "title"))
        if subtitle:
            layout.addWidget(label(subtitle, "muted"))
        return content, layout

    def _new_page(self):
        return build_download_page(self)

    @staticmethod
    def make_table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        table.setMouseTracking(True)
        table.smooth_scroll = SmoothScroll(table)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setMinimumSectionSize(28)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return table

    def _queue_page(self):
        page, layout = self.page("下载队列", "查看下载进度、完成记录与未完成的任务。")
        toolbar = QHBoxLayout()
        self.queue_summary = label("暂无任务", "muted")
        self.queue_summary.setWordWrap(False)
        self.queue_summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(self.queue_summary, 1)
        toolbar.addWidget(label("同时下载", "muted"))
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 3)
        self.concurrency.setMinimumHeight(34)
        self.concurrency.setValue(max(1, min(3, int(self.settings.get("concurrency", 1)))))
        self.concurrency.valueChanged.connect(self.pump)
        toolbar.addWidget(self.concurrency)
        self.pause_button = button("暂停队列", self.toggle_pause)
        toolbar.addWidget(self.pause_button)
        toolbar.addWidget(button("重试未完成", self.retry_unfinished))
        toolbar.addWidget(button("清理记录", self.clear_finished))
        layout.addLayout(toolbar)
        filters = QHBoxLayout()
        self.queue_filter = QComboBox()
        for text, states in (("全部任务", None), ("下载中 / 等待中", ["active", "waiting"]),
                             ("已完成", ["done"]), ("未完成", ["failed", "partial", "cancelled", "interrupted"])):
            self.queue_filter.addItem(text, states)
        self.queue_filter.currentIndexChanged.connect(self.render_queue)
        filters.addWidget(self.queue_filter)
        self.queue_search = QLineEdit()
        self.queue_search.setPlaceholderText("搜索下载记录")
        self.queue_search.setClearButtonEnabled(True)
        self.queue_search_timer = QTimer(self)
        self.queue_search_timer.setSingleShot(True)
        self.queue_search_timer.setInterval(150)
        self.queue_search_timer.timeout.connect(self.render_queue)
        self.queue_search.textChanged.connect(lambda: self.queue_search_timer.start())
        filters.addWidget(self.queue_search, 1)
        layout.addLayout(filters)
        self.table = self.make_table(["任务", "下载内容", "状态", "进度", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 105), (2, 90), (3, 115), (4, 140)):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)
        layout.addWidget(label("暂停队列会保留当前任务继续下载；重试会重新获取链接并从头下载。", "muted"))
        return page

    def _settings_page(self):
        page, layout = self.page("设置", "调整提取方式与下载偏好。")
        frame, box = card()
        box.addWidget(label("外观", "section"))
        self.theme_control = SegmentedControl()
        self.theme_control.setAccessibleName("界面主题")
        for text, value in (("跟随系统", "system"), ("浅色", "light"), ("深色", "dark")):
            self.theme_control.addItem(text, value)
        self.theme_control.setCurrentIndex(self.theme_control.findData(self.settings.get("theme", "system")))
        self.theme_control.currentIndexChanged.connect(self.change_theme)
        box.addWidget(self.theme_control)
        layout.addWidget(frame)
        frame, box = card()
        box.addWidget(label("提取设置", "section"))
        self.common = QCheckBox("平台提取失败时，继续尝试通用解析")
        self.common.setChecked(bool(self.settings.get("common", True)))
        self.common.toggled.connect(self.persist)
        box.addWidget(self.common)
        box.addWidget(label("开启后可尝试更多来源，部分链接的等待时间会增加。", "muted"))
        form = QFormLayout()
        self.extract_concurrency = QSpinBox()
        self.extract_concurrency.setMinimumHeight(36)
        self.extract_concurrency.setMaximumWidth(120)
        self.extract_concurrency.setRange(1, 3)
        self.extract_concurrency.setValue(max(1, min(3, int(self.settings.get("extract_concurrency", 2)))))
        self.extract_concurrency.valueChanged.connect(self.persist)
        form.addRow("同时提取的链接", self.extract_concurrency)
        box.addLayout(form)
        layout.addWidget(frame)
        from .bilibili_auth import load_cookies
        frame, box = card()
        box.addWidget(label("B站高清画质", "section"))
        self.bilibili_status = label("B站已登录 · 提取时优先获取账号可访问的高清画质" if load_cookies()
                                     else "B站未登录 · 登录后可获取更多高清画质", "muted")
        box.addWidget(self.bilibili_status)
        row = QHBoxLayout()
        row.addWidget(button("扫码登录B站", self.login_bilibili, "primary"))
        row.addWidget(button("清除本机登录", self.logout_bilibili))
        row.addStretch()
        box.addLayout(row)
        layout.addWidget(frame)
        frame, box = card()
        box.addWidget(label("自动下载的内容", "section"))
        box.addWidget(label("首页开启“提取后自动下载”时，按以下选项处理新结果。", "muted"))
        self.options = {}
        choices = QHBoxLayout()
        defaults = self.settings.get("options", {})
        for kind in ("video", "audio", "cover"):
            check = QCheckBox(KINDS[kind])
            check.setChecked(bool(defaults.get(kind, True)))
            check.toggled.connect(self.persist)
            self.options[kind] = check
            choices.addWidget(check)
        choices.addStretch()
        box.addLayout(choices)
        layout.addWidget(frame)
        frame, box = card()
        box.addWidget(label("本地记录", "section"))
        box.addWidget(label("提取结果、下载记录和偏好会在下次打开时继续保留。"))
        row = QHBoxLayout()
        row.addWidget(button("打开数据文件夹", lambda: self.open_folder(str(self.store)), symbol="folder"))
        row.addStretch()
        box.addLayout(row)
        layout.addWidget(frame)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _updates_page(self):
        page, layout = self.page("关于与更新", "VideoDL Desktop")
        frame, box = card()
        box.addWidget(label("VideoDL Desktop", "brand"))
        info = build_info()
        box.addWidget(label(f"桌面版 {__version__}  ·  下载内核 {info.get('core_version', '未知')}"))
        box.addWidget(label("对应上游提交：" + info.get("upstream_revision", "未知")[:12], "muted"))
        self.update_status = label("点击检查获取最新桌面发行版。", "muted")
        box.addWidget(self.update_status)
        row = QHBoxLayout()
        self.update_button = button("检查更新", self.start_updates, "primary")
        row.addWidget(self.update_button)
        row.addWidget(button("下载新版", lambda: QDesktopServices.openUrl(QUrl(self.release_url))))
        row.addWidget(button("项目主页", lambda: QDesktopServices.openUrl(QUrl(f"https://github.com/{REPOSITORY}/tree/desktop"))))
        row.addStretch()
        box.addLayout(row)
        layout.addWidget(frame)
        layout.addStretch()
        return page
