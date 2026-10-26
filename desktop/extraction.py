"""Cancellable, concurrent extraction of every submitted source link."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from .process import Worker
from .storage import parse_links


class ExtractionController:
    def start_preview(self):
        if not self.extraction_active and not self.extraction_waiting:
            self.begin_extraction(parse_links(self.links.toPlainText()))

    def begin_extraction(self, urls, replace=True):
        if self.extraction_active:
            return
        output = self.output_directory()
        if not urls or not output:
            self.say("请先粘贴有效链接，并选择保存文件夹。")
            return
        if len(urls) > 200:
            self.say("单次最多提取 200 个链接，请分批添加。")
            return
        if self.auto_download.isChecked() and not any(check.isChecked() for check in self.options.values()):
            self.say("请先选择自动下载的内容。")
            self.navigate(2)
            return
        if replace:
            self.batch_started = True
            self.catalog.rows.clear()
            self.jobs = [job for job in self.jobs if job["id"] in self.running]
            self.extraction_failures.clear()
            self.result_search.clear()
            self.type_filter.setCurrentIndex(0)
            self.queue_search.clear()
            self.queue_filter.setCurrentIndex(0)
            self.retry_extract_button.hide()
            self.extract_errors_button.hide()
            self.render_results()
            self.render_queue()
            self.persist()
            self.say("正在提取新一批链接…")
        self.extraction_waiting = list(urls)
        self.extraction_output = output
        self.extraction_total = len(urls)
        self.extraction_completed = 0
        self.extraction_cancelled = False
        self.extraction_succeeded.clear()
        for url in urls:
            self.extraction_failures.pop(url, None)
        self.parse_button.setEnabled(False)
        self.stop_extract.show()
        self.extract_progress.setRange(0, 0)
        self.extract_progress.show()
        self.update_workbench_layout()
        self.update_empty_state()
        self.pump_extraction()

    def pump_extraction(self):
        if self.closing:
            return
        while self.extraction_waiting and len(self.extraction_active) < self.extract_concurrency.value():
            url = self.extraction_waiting.pop(0)
            worker = Worker({"action": "parse", "url": url, "output": self.extraction_output,
                             "common": self.common.isChecked()}, self)
            self.extraction_active[url] = worker
            worker.event.connect(lambda event, current=url: self.extraction_event(current, event))
            worker.finished.connect(lambda code, current=url: self.extraction_finished(current, code))
            worker.start()
        self.parse_button.setText(f"提取中 {self.extraction_completed}/{self.extraction_total}")

    def extraction_event(self, url, event):
        if event["event"] == "result":
            self.extraction_succeeded.add(url)
            fresh = self.catalog.replace_summary(url, event.get("items", []))
            self.persist()
            self.render_results()
            if self.auto_download.isChecked():
                self.download_results([row for row in fresh if self.options[row["kind"]].isChecked()])
        elif event["event"] == "error":
            self.extraction_failures[url] = event["message"]

    def extraction_finished(self, url, code):
        worker = self.extraction_active.pop(url, None)
        if worker and not worker.cancelled and url not in self.extraction_succeeded and url not in self.extraction_failures:
            self.extraction_failures[url] = "该链接未完成提取，请稍后重试。"
        if worker:
            worker.deleteLater()
        self.extraction_completed += 1
        self.extract_progress.setRange(0, self.extraction_total)
        self.extract_progress.setValue(self.extraction_completed)
        if self.closing:
            return
        if self.extraction_active or self.extraction_waiting:
            self.pump_extraction()
            return
        self.parse_button.setEnabled(True)
        self.parse_button.setText("提取链接")
        self.stop_extract.hide()
        self.extract_progress.hide()
        failures = len(self.extraction_failures)
        self.retry_extract_button.setVisible(bool(failures))
        self.retry_extract_button.setText(f"重试失败链接（{failures}）")
        self.extract_errors_button.setVisible(bool(failures))
        text = "提取已停止，已取得的结果保留。" if self.extraction_cancelled else f"提取完成，当前共 {len(self.catalog.rows)} 项内容。"
        if failures:
            text += f" {failures} 个链接未完成，可查看详情或重试。"
        self.say(text)
        self.render_results()

    def cancel_extraction(self):
        self.extraction_cancelled = True
        self.extraction_waiting.clear()
        for worker in list(self.extraction_active.values()):
            worker.cancel()
        self.say("正在停止提取，已取得的结果会保留。")

    def retry_extraction(self):
        if not self.extraction_active and self.extraction_failures:
            self.begin_extraction(list(self.extraction_failures), replace=False)

    def show_extraction_errors(self):
        box = QMessageBox(self)
        box.setWindowTitle("未完成的链接")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText("\n\n".join(f"{url}\n{detail}" for url, detail in self.extraction_failures.items()))
        box.exec()
