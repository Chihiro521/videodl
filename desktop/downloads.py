"""Persistent download queue, independent of extraction-page layout."""

import uuid
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QTableWidgetItem, QWidget

from .process import Worker
from .storage import public_host
from .widgets import button
from .quality import recommended_formats
from .theme import colors
from PySide6.QtGui import QColor

STATES = {"waiting": "等待中", "active": "下载中", "done": "已完成", "failed": "失败",
          "partial": "部分完成", "cancelled": "已取消", "interrupted": "已中断", "idle": "待下载"}
KINDS = {"cover": "封面", "audio": "音频", "video": "视频"}


class DownloadQueue:
    def enqueue(self, groups, navigate=False):
        output = self.output_directory()
        if not output:
            return 0
        added = 0
        save_mode = self.save_mode.currentData()
        for group in groups:
            existing = next((job for job in self.jobs if job["url"] == group["url"]
                and job["options"] == group["options"] and job["output"] == output
                and job.get("indices") == group.get("indices")
                and job.get("item_keys") == group.get("item_keys")
                and job.get("format_ids", {}) == group.get("format_ids", {})
                and job.get("save_mode", "flat") == save_mode
                and job["status"] in ("waiting", "active")), None)
            if existing:
                existing["result_ids"] = list(dict.fromkeys(existing.get("result_ids", []) + group.get("result_ids", [])))
                self.catalog.link_job(existing)
                self.catalog.sync_job(existing)
                continue
            job = {**group, "id": uuid.uuid4().hex, "output": output, "common": self.common.isChecked(), "save_mode": save_mode,
                "status": "waiting", "percent": 0, "detail": "等待下载", "files": [],
                "created": datetime.now().isoformat(timespec="seconds")}
            self.jobs.append(job)
            self.catalog.link_job(job)
            added += 1
        self.persist()
        self.render_results()
        if navigate:
            self.navigate(1)
        self.say(f"已加入 {added} 个下载任务，可在当前列表查看状态。")
        self.pump()
        return added

    def add_jobs(self):
        """Retain the original direct-enqueue API for existing integrations."""
        from .storage import parse_links
        options = {kind: check.isChecked() for kind, check in self.options.items()}
        urls = parse_links(self.links.toPlainText())
        if not urls or not any(options.values()):
            self.say("请提供有效链接，并选择下载内容。")
            return
        if len(urls) > 200:
            self.say("单次最多添加 200 个链接，请分批添加。")
            return
        self.enqueue([{"url": url, "title": public_host(url), "options": options.copy(), "indices": None,
                       "item_keys": None, "result_ids": []} for url in urls], navigate=True)

    def pump(self, *_):
        if self.closing or self.paused:
            return
        for job in self.jobs:
            if len(self.running) >= self.concurrency.value():
                break
            if job["status"] != "waiting":
                continue
            job.update(status="active", detail="正在准备下载")
            command = {"action": "download", **{key: job.get(key) for key in
                ("url", "output", "options", "indices", "item_keys", "common", "format_ids", "identity_version", "save_mode", "item_folders")}}
            worker = Worker(command, self)
            self.running[job["id"]] = worker
            worker.event.connect(lambda event, current=job: self.job_event(current, event))
            worker.finished.connect(lambda code, current=job: self.job_finished(current, code))
            worker.start()
            self.catalog.sync_job(job)
        self.persist()
        self.render_queue()
        self.refresh_result_status()

    def job_event(self, job, event):
        kind = event["event"]
        if kind == "destination":
            job.setdefault("item_folders", {})[event["item_key"]] = event["folder"]
            self.persist()
            return
        if kind == "parsed" and event.get("items"):
            items = event["items"]
            job["cache_hit"] = event.get("cache_hit", False)
            job["parse_seconds"] = event.get("parse_seconds", 0)
            legacy = job.get("identity_version", 1) < 2
            selected_keys = event.get("selected_item_keys") or (job.get("item_keys") if not legacy else None)
            if selected_keys:
                items = [item for item in items if item.get("item_key") in selected_keys]
            elif job.get("indices") is not None:
                items = [item for item in items if item["index"] in job["indices"]]
            if items:
                job["title"] = items[0]["title"] + (f" 等 {len(items)} 个条目" if len(items) > 1 else "")
                if legacy:
                    job.update(identity_version=2, item_keys=[item["item_key"] for item in items])
                for row in self.catalog.rows:
                    if row["id"] not in job.get("result_ids", []):
                        continue
                    item = items[0] if legacy and len(items) == 1 else next((item for item in items if item["index"] == row["index"]), None)
                    if item:
                        row.update(title=item["title"], item_key=item["item_key"], index=item["index"], identity_version=2)
                        if row["kind"] == "video":
                            row["formats"] = item.get("formats", [])
                            if not row.get("format_id") and row["formats"]:
                                row["format_id"] = recommended_formats(row["formats"])[0]["id"]
                self.render_results()
            self.render_queue()
        elif kind == "progress":
            job.update(detail=event.get("detail", "正在下载"), percent=event.get("percent", -1))
            self.pending_progress[job["id"]] = job
            if not self.progress_timer.isActive():
                self.progress_timer.start()
            return
        elif kind == "file":
            job["files"].append({key: event[key] for key in ("path", "kind", "item_key", "format_id") if key in event})
        elif kind == "result":
            self.pending_progress.pop(job["id"], None)
            job["status"] = event.get("status", "done")
            job["files"] = event.get("files", job["files"])
            job["detail"] = "；".join(event.get("errors", [])) or "下载完成"
            job["percent"] = 100 if job["status"] == "done" else 0
        elif kind == "error":
            self.pending_progress.pop(job["id"], None)
            job.update(status="partial" if job["files"] else "failed", detail=event["message"], percent=0)
        self.catalog.sync_job(job)
        self.refresh_result_status()
        if kind in ("file", "result", "error"):
            self.persist()
            self.render_queue()

    def job_finished(self, job, code):
        self.pending_progress.pop(job["id"], None)
        worker = self.running.pop(job["id"], None)
        if worker and worker.cancelled:
            job.update(status="cancelled", detail="任务已取消，已完成文件保留。")
        elif job["status"] == "active":
            job.update(status="partial" if job["files"] else "failed", detail="下载进程已结束，点击重试可重新下载。")
        if worker:
            worker.deleteLater()
        self.catalog.sync_job(job)
        self.persist()
        self.render_queue()
        self.refresh_result_status()
        if not self.closing and job["status"] in ("done", "partial", "failed", "cancelled"):
            self.say(f"{STATES[job['status']]} · {job.get('title', '下载任务')}")
        if not self.closing:
            QTimer.singleShot(0, self.pump)

    def update_progress(self, job):
        row = self.queue_row_map.get(job["id"])
        if row is None:
            return
        progress = self.table.cellWidget(row, 3)
        percent = job.get("percent", 0)
        progress.setRange(0, 0 if percent < 0 and job["status"] == "active" else 100)
        progress.setValue(round(max(0, percent)))
        progress.setToolTip(job.get("detail", ""))
        self.table.item(row, 0).setToolTip(job.get("detail", ""))

    def flush_progress(self):
        jobs, self.pending_progress = self.pending_progress, {}
        for job in jobs.values():
            self.update_progress(job)
            self.refresh_result_status(job["id"])

    def render_queue(self):
        self.queue_search_timer.stop()
        scroll = self.table.verticalScrollBar().value()
        self.table.setUpdatesEnabled(False)
        try:
            self._render_queue()
        finally:
            self.table.verticalScrollBar().setValue(scroll)
            self.table.setUpdatesEnabled(True)

    def _render_queue(self):
        selected = self.queue_filter.currentData()
        query = self.queue_search.text().strip().casefold()
        jobs = [job for job in reversed(self.jobs) if (not selected or job["status"] in selected)
                and (not query or query in job.get("title", "").casefold())]
        identifiers = [job["id"] for job in jobs]
        if identifiers != list(self.queue_row_map):
            self.table.setRowCount(0)
            self.queue_signatures.clear()
        self.queue_row_map = {}
        self.table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            self.queue_row_map[job["id"]] = row
            signature = (job.get("title"), job["url"], repr(job["options"]), job["status"], bool(job.get("files")))
            if self.queue_signatures.get(job["id"]) == signature:
                self.update_progress(job)
                self.table.item(row, 2).setToolTip(job.get("detail", ""))
                continue
            self.queue_signatures[job["id"]] = signature
            for column in (3, 4):
                previous_widget = self.table.cellWidget(row, column)
                if previous_widget:
                    previous_widget.hide()
            self.table.setRowHeight(row, 56)
            title = QTableWidgetItem(job.get("title", "未命名") + "\n" + public_host(job["url"]))
            title.setToolTip(job.get("detail", ""))
            self.table.setItem(row, 0, title)
            self.table.setItem(row, 1, QTableWidgetItem(" / ".join(KINDS[kind] for kind, value in job["options"].items() if value and kind in KINDS)))
            state = QTableWidgetItem(STATES.get(job["status"], job["status"]))
            state.setForeground(QColor(colors()["done"] if job["status"] == "done" else colors()["error"] if job["status"] in ("failed", "partial") else colors()["muted"]))
            state.setToolTip(job.get("detail", ""))
            self.table.setItem(row, 2, state)
            progress = QProgressBar()
            progress.setTextVisible(False)
            self.table.setCellWidget(row, 3, progress)
            self.update_progress(job)
            actions = QWidget()
            buttons = QHBoxLayout(actions)
            buttons.setContentsMargins(4, 10, 4, 10)
            buttons.setSpacing(5)
            if job["status"] in ("active", "waiting"):
                buttons.addWidget(button("取消", lambda _, current=job: self.cancel_job(current), "small"))
            elif job["status"] != "done":
                buttons.addWidget(button("重试", lambda _, current=job: self.retry_job(current), "small"))
            if job.get("files"):
                buttons.addWidget(button("文件", lambda _, current=job: self.open_job(current), "small"))
            buttons.addStretch()
            self.table.setCellWidget(row, 4, actions)
        done = sum(job["status"] == "done" for job in self.jobs)
        active = sum(job["status"] == "active" for job in self.jobs)
        waiting = sum(job["status"] == "waiting" for job in self.jobs)
        self.queue_summary.setText(f"共 {len(self.jobs)} 项 · {active} 项下载中 · {waiting} 项等待 · {done} 项完成")
        self.nav[1].setText("队列" + (f" {active + waiting}" if active + waiting else ""))
        self.nav[1].setToolTip(self.queue_summary.text())

    def cancel_job(self, job):
        if job["id"] in self.running:
            job["detail"] = "正在取消…"
            self.running[job["id"]].cancel()
        else:
            job.update(status="cancelled", detail="已从等待队列取消。")
        self.catalog.sync_job(job)
        self.persist()
        self.render_queue()
        self.refresh_result_status()

    def retry_job(self, job):
        if job["id"] in self.running:
            return
        job.update(status="waiting", percent=0, detail="等待重试", files=[])
        self.catalog.link_job(job)
        self.persist()
        self.pump()

    def retry_unfinished(self):
        for job in self.jobs:
            if job["status"] in ("failed", "partial", "interrupted", "cancelled") and job["id"] not in self.running:
                job.update(status="waiting", percent=0, detail="等待重试", files=[])
                self.catalog.link_job(job)
        self.persist()
        self.pump()

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.setText("继续队列" if self.paused else "暂停队列")
        self.say("队列已暂停，正在下载的任务会继续完成。" if self.paused else "队列已继续。")
        self.pump()

    def clear_finished(self):
        self.jobs = [job for job in self.jobs if job["status"] in ("active", "waiting") or job["id"] in self.running]
        self.persist()
        self.render_queue()
