"""Native batch extraction, media results, and persistent downloads."""

import os
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from . import REPOSITORY
from .downloads import DownloadQueue
from .extraction import ExtractionController
from .pages import WorkbenchPages
from .process import Worker
from .results import ResultCatalog
from .resultview import ResultView
from .storage import data_dir, load_json, parse_links, save_json
from .theme import apply_theme, icon


class Window(QMainWindow, WorkbenchPages, DownloadQueue, ExtractionController, ResultView):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoDL Desktop")
        self.setWindowIcon(icon("download", "#2563eb", 48))
        self.resize(1180, 800)
        self.setMinimumSize(980, 680)
        self.store = data_dir()
        self.settings = load_json(self.store / "settings.json", {})
        if not isinstance(self.settings, dict):
            self.settings = {}
        loaded = load_json(self.store / "queue.json", [])
        self.jobs = [job for job in loaded if isinstance(job, dict) and all(key in job for key in
            ("id", "url", "options", "output", "status"))] if isinstance(loaded, list) else []
        for job in self.jobs:
            job.setdefault("files", [])
            if job["status"] in ("active", "waiting"):
                job.update(status="interrupted", detail="上次退出时未完成，点击重试可重新下载。")
        self.catalog = ResultCatalog(load_json(self.store / "results.json", []))
        for job in self.jobs:
            self.catalog.sync_job(job)
        self.running = {}
        self.extraction_active = {}
        self.extraction_waiting = []
        self.extraction_failures = {}
        self.extraction_succeeded = set()
        self.extraction_total = 0
        self.extraction_completed = 0
        self.extraction_cancelled = False
        self.update_worker = None
        self.closing = False
        self.paused = False
        self.result_row_map = {}
        self.queue_row_map = {}
        self.release_url = f"https://github.com/{REPOSITORY}/releases"
        self._build()
        self.render_results()
        self.render_queue()
        self.persist()

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for current, nav in enumerate(self.nav):
            nav.setChecked(current == index)

    def say(self, text):
        self.message.setText(text)
        self.message.setToolTip(text)
        self.statusBar().showMessage(text, 15000)

    def paste(self):
        self.links.setPlainText(QApplication.clipboard().text())

    def paste_and_extract(self):
        self.paste()
        self.start_preview()

    def update_link_count(self):
        count = len(parse_links(self.links.toPlainText()))
        self.link_count.setText(f"已识别 {count} 个链接 · Ctrl+Enter 提取" if count else "支持 Bilibili、抖音、YouTube 等链接")

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择保存文件夹", self.destination.text())
        if directory:
            self.destination.setText(directory)
            self.persist()

    def output_directory(self):
        text = self.destination.text().strip()
        path = Path(text).expanduser()
        if not text or not path.is_absolute():
            self.say("请先选择完整的保存文件夹路径。")
            return None
        return str(path)

    def open_folder(self, path):
        if path.strip():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))

    def open_job(self, job):
        paths = [Path(item["path"]) for item in job.get("files", []) if Path(item["path"]).is_file()]
        self.open_folder(str(paths[0].parent if paths else Path(job["output"])))

    def start_updates(self):
        if self.update_worker:
            return
        self.update_button.setEnabled(False)
        self.update_status.setText("正在检查最新版本…")
        worker = Worker({"action": "updates"}, self)
        self.update_worker = worker
        worker.event.connect(self.update_event)
        worker.finished.connect(self.update_finished)
        worker.start()

    def update_event(self, event):
        if event["event"] == "result":
            self.release_url = event["release_url"]
            prefix = "发现新版本" if event["available"] else "当前发行版本"
            self.update_status.setText(f"{prefix}：{event['latest']}\n上游最新提交：{event.get('upstream_revision', '未知')[:12]}")
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
            options={kind: check.isChecked() for kind, check in self.options.items()},
            concurrency=self.concurrency.value(), extract_concurrency=self.extract_concurrency.value(),
            auto_download=self.auto_download.isChecked())
        try:
            save_json(self.store / "settings.json", self.settings)
            save_json(self.store / "queue.json", self.jobs)
            save_json(self.store / "results.json", self.catalog.rows)
        except OSError:
            self.statusBar().showMessage("本地记录保存失败，请检查数据文件夹的可写权限。")

    def closeEvent(self, event):
        self.closing = True
        self.extraction_waiting.clear()
        workers = list(self.running.values()) + list(self.extraction_active.values())
        if self.update_worker:
            workers.append(self.update_worker)
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
        from .smoke import schedule_capture
        schedule_capture(window, smoke_report)
    return application.exec()
