"""Selection, filtering, row actions, and live download state in the result table."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QHBoxLayout, QMenu, QTableWidgetItem, QToolButton, QWidget

from .downloads import STATES
from .results import KINDS
from .storage import public_host
from .theme import icon
from .widgets import tool_button


class ResultView:
    def visible_results(self):
        return self.catalog.visible(self.type_filter.currentData() or "", self.result_search.text())

    def render_results(self, *_):
        rows = self.visible_results()
        self.result_row_map = {}
        self.results_table.setRowCount(len(rows))
        for number, row in enumerate(rows):
            self.result_row_map[row["id"]] = number
            self.results_table.setRowHeight(number, 58)
            check = QCheckBox()
            check.setAccessibleName(f"选择{KINDS[row['kind']]}：{row['title']}")
            check.setChecked(row.get("checked", False))
            check.toggled.connect(lambda value, current=row: self.set_result_checked(current, value))
            wrapper = QWidget()
            check_box = QHBoxLayout(wrapper)
            check_box.setContentsMargins(10, 0, 0, 0)
            check_box.addWidget(check)
            self.results_table.setCellWidget(number, 0, wrapper)
            title = QTableWidgetItem(row["title"])
            title.setToolTip(f"{row['title']}\n{public_host(row['url'])}")
            self.results_table.setItem(number, 1, title)
            text = ("视频 · " + (row.get("ext") or "原始格式").upper()) if row["kind"] == "video" else "音频 · 原始音轨" if row["kind"] == "audio" else "图片 · 原始封面"
            if row["kind"] == "video":
                combo = QComboBox()
                combo.setObjectName("qualityChoice")
                combo.setAccessibleName(f"下载画质：{row['title']}")
                formats = row.get("formats") or [{"id": "", "label": "来源画质-" + (row.get("ext") or "mp4").upper()}]
                for entry in formats:
                    combo.addItem(icon("video", "#64748b", 18), entry["label"], entry["id"])
                combo.setCurrentIndex(max(0, combo.findData(row.get("format_id", ""))))
                combo.setEnabled(self.row_state(row)[0] not in ("waiting", "active"))
                combo.setToolTip("选择本条视频的下载画质" if len(formats) > 1 else "来源当前提供这一档画质")
                combo.currentIndexChanged.connect(lambda _, current=row, control=combo: self.set_result_format(current, control.currentData()))
                wrapper = QWidget()
                layout = QHBoxLayout(wrapper)
                layout.setContentsMargins(7, 8, 7, 8)
                layout.addWidget(combo)
                self.results_table.setCellWidget(number, 2, wrapper)
            else:
                self.results_table.setCellWidget(number, 2, None)
                self.results_table.setItem(number, 2, QTableWidgetItem(icon(row["kind"], "#64748b", 18), text))
            self.results_table.setItem(number, 3, QTableWidgetItem())
            actions = QWidget()
            actions_box = QHBoxLayout(actions)
            actions_box.setContentsMargins(0, 0, 0, 0)
            actions_box.setSpacing(0)
            action = tool_button("download", "下载该项", lambda _, current=row: self.result_action(current))
            action.setObjectName("resultDownload")
            actions_box.addWidget(action)
            more = tool_button("more", "更多操作")
            more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(more)
            menu.addAction("复制标题", lambda checked=False, current=row: QApplication.clipboard().setText(current["title"]))
            menu.addAction("复制来源链接", lambda checked=False, current=row: QApplication.clipboard().setText(current["url"]))
            menu.addAction("查看下载队列", lambda: self.navigate(1))
            menu.addSeparator()
            menu.addAction("重新下载该项", lambda checked=False, current=row: self.download_results([current], force=True))
            menu.addAction("从列表移除此项", lambda checked=False, current=row: self.remove_result(current))
            more.setMenu(menu)
            actions_box.addWidget(more)
            self.results_table.setCellWidget(number, 4, actions)
        self.result_stack.setCurrentIndex(1 if self.catalog.rows else 0)
        counts = {kind: sum(row["kind"] == kind for row in self.catalog.rows) for kind in KINDS}
        detail = " · ".join(f"{count} 项{KINDS[kind]}" for kind, count in counts.items() if count)
        prefix = f"显示 {len(rows)} / 共 {len(self.catalog.rows)} 项" if self.type_filter.currentData() or self.result_search.text() else f"共 {len(self.catalog.rows)} 项"
        self.result_summary.setText(f"{prefix}（{detail}）" if detail else "暂无提取结果")
        self.refresh_result_status()

    def set_result_format(self, row, format_id):
        if row.get("format_id", "") == format_id:
            return
        row.update(format_id=format_id, file="", job_id="", status="idle", detail="已切换画质，等待下载")
        self.persist()
        self.refresh_result_status()
        self.update_selection()

    def set_result_checked(self, row, checked):
        row["checked"] = checked
        self.update_selection()

    def update_selection(self):
        rows = self.visible_results()
        checked = sum(bool(row.get("checked")) for row in rows)
        self.select_all.setEnabled(bool(rows))
        self.select_all.blockSignals(True)
        state = Qt.CheckState.Unchecked if not checked else Qt.CheckState.Checked if checked == len(rows) else Qt.CheckState.PartiallyChecked
        self.select_all.setCheckState(state)
        self.select_all.blockSignals(False)
        self.download_selected_button.setText(f"下载选中（{checked}）" if checked else "下载选中")
        self.download_selected_button.setEnabled(any(row.get("checked") and self.downloadable(row) for row in rows))
        self.download_all_button.setEnabled(any(self.downloadable(row) for row in rows))

    def select_visible(self, checked):
        for row in self.visible_results():
            row["checked"] = checked
        self.render_results()

    def row_state(self, row):
        job = next((job for job in self.jobs if job["id"] == row.get("job_id")), None)
        if row.get("file"):
            return "done", job
        return (job["status"] if job else row.get("status", "idle")), job

    def downloadable(self, row):
        return self.row_state(row)[0] not in ("done", "waiting", "active")

    def refresh_result_status(self):
        for row in self.catalog.rows:
            position = self.result_row_map.get(row["id"])
            if position is None:
                continue
            state, job = self.row_state(row)
            detail = job.get("detail", "") if job else row.get("detail", "")
            text = "未完成" if state == "partial" else STATES.get(state, state)
            percent = job.get("percent", -1) if job else -1
            if state == "active" and percent >= 0:
                text += f" · {percent}%"
            status = self.results_table.item(position, 3)
            status.setText(text)
            status.setToolTip(detail)
            color = "#16a34a" if state == "done" else "#2563eb" if state in ("waiting", "active") else "#dc2626" if state in ("failed", "partial") else "#64748b"
            status.setForeground(QColor(color))
            quality_cell = self.results_table.cellWidget(position, 2)
            quality = quality_cell.findChild(QComboBox, "qualityChoice") if quality_cell else None
            if quality:
                quality.setEnabled(state not in ("waiting", "active"))
            action = self.results_table.cellWidget(position, 4).findChild(QToolButton, "resultDownload")
            action.setIcon(icon("folder" if state == "done" else "queue" if state in ("waiting", "active") else "download", "#2563eb", 19))
            action.setToolTip("打开文件所在位置" if state == "done" else "查看下载进度" if state in ("waiting", "active") else "下载该项")
        self.update_selection()

    def download_visible(self):
        self.download_results(self.visible_results())

    def download_selected(self):
        self.download_results([row for row in self.visible_results() if row.get("checked")])

    def download_results(self, rows, force=False):
        rows = [row for row in rows if self.downloadable(row) or (force and self.row_state(row)[0] not in ("waiting", "active"))]
        if rows:
            self.enqueue(self.catalog.plan(rows))

    def result_action(self, row):
        state, _ = self.row_state(row)
        if state == "done":
            path = Path(row["file"])
            if path.is_file():
                self.open_folder(str(path.parent))
            else:
                self.say("文件已不在原位置，可在更多操作中重新下载。")
        elif state in ("waiting", "active"):
            self.navigate(1)
        else:
            self.download_results([row])

    def remove_result(self, row):
        self.catalog.rows = [current for current in self.catalog.rows if current["id"] != row["id"]]
        self.persist()
        self.render_results()

    def clear_results(self):
        if self.extraction_active:
            self.say("请先停止提取，再清空列表。")
            return
        self.catalog.rows.clear()
        self.persist()
        self.render_results()
        self.say("提取列表已清空，下载任务和文件保留。")
