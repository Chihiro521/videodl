"""Selection, filtering, row actions, and live download state in the result table."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QHBoxLayout, QMenu, QTableWidgetItem, QToolButton, QWidget

from .downloads import STATES
from .results import KINDS
from .storage import public_host
from .theme import colors, icon, set_symbol
from .quality import choice_label, detail_label, recommended_formats, resolution
from .widgets import QualityComboBox, tool_button


class ResultView:
    def visible_results(self):
        return self.catalog.visible(self.type_filter.currentData() or "", self.result_search.text())

    def render_results(self, *_):
        self.result_search_timer.stop()
        table = self.results_table
        scroll = table.verticalScrollBar().value()
        table.setUpdatesEnabled(False)
        try:
            self._render_results()
        finally:
            table.verticalScrollBar().setValue(scroll)
            table.setUpdatesEnabled(True)

    def _render_results(self):
        rows = self.visible_results()
        self.result_lookup = {row["id"]: row for row in self.catalog.rows}
        identifiers = [row["id"] for row in rows]
        previous = list(self.result_row_map)
        if identifiers[:len(previous)] != previous:
            self.results_table.setRowCount(0)
            self.result_signatures.clear()
            self.result_status_signatures.clear()
        self.result_row_map = {}
        self.results_table.setRowCount(len(rows))
        for number, row in enumerate(rows):
            self.result_row_map[row["id"]] = number
            signature = (row["title"], row["kind"], row["url"], row.get("ext"), row.get("format_id"), repr(row.get("formats")))
            if self.result_signatures.get(row["id"]) == signature:
                check = self.results_table.cellWidget(number, 0).findChild(QCheckBox)
                check.blockSignals(True)
                check.setChecked(bool(row.get("checked")))
                check.blockSignals(False)
                continue
            self.result_signatures[row["id"]] = signature
            self.result_status_signatures.pop(row["id"], None)
            for column in (0, 2, 4):
                previous_widget = self.results_table.cellWidget(number, column)
                if previous_widget:
                    previous_widget.hide()
            self.results_table.setRowHeight(number, 56)
            check = QCheckBox()
            check.setFixedSize(20, 20)
            check.setAccessibleName(f"选择{KINDS[row['kind']]}：{row['title']}")
            check.setChecked(row.get("checked", False))
            check.toggled.connect(lambda value, key=row["id"]: self.result_command(key, "set_result_checked", value))
            wrapper = QWidget()
            check_box = QHBoxLayout(wrapper)
            check_box.setContentsMargins(0, 0, 0, 0)
            check_box.addWidget(check)
            self.results_table.setCellWidget(number, 0, wrapper)
            title = QTableWidgetItem(row["title"])
            title.setToolTip(f"{row['title']}\n{public_host(row['url'])}")
            self.results_table.setItem(number, 1, title)
            text = ("视频 · " + (row.get("ext") or "原始格式").upper()) if row["kind"] == "video" else "音频 · 原始音轨" if row["kind"] == "audio" else "图片 · 原始封面"
            if row["kind"] == "video":
                combo = QualityComboBox()
                combo.setObjectName("qualityChoice")
                combo.setAccessibleName(f"下载画质：{row['title']}")
                raw_formats = row.get("formats") or [{"id": "", "label": "来源画质-" + (row.get("ext") or "mp4").upper(), "ext": row.get("ext") or "mp4"}]
                formats = recommended_formats(raw_formats)
                selected = next((f for f in raw_formats if f["id"] == row.get("format_id")), None)
                if selected:
                    formats = [selected if resolution(f) == resolution(selected) else f for f in formats]
                for entry in formats:
                    combo.addItem(icon("video", colors()["muted"], 18), choice_label(entry), entry["id"])
                    combo.setItemData(combo.count() - 1, detail_label(entry), Qt.ItemDataRole.ToolTipRole)
                combo.setCurrentIndex(max(0, combo.findData(row.get("format_id", ""))))
                combo.setEnabled(self.row_state(row)[0] not in ("waiting", "active"))
                combo.setMaxVisibleItems(10)
                combo.setToolTip("每档展示推荐版本；其他编码可在右侧更多菜单中选择" if len(raw_formats) > len(formats) else "选择本条视频的下载画质")
                combo.currentIndexChanged.connect(lambda _, key=row["id"], control=combo: self.result_command(key, "set_result_format", control.currentData()))
                wrapper = QWidget()
                layout = QHBoxLayout(wrapper)
                layout.setContentsMargins(7, 8, 7, 8)
                layout.addWidget(combo)
                self.results_table.setCellWidget(number, 2, wrapper)
            else:
                self.results_table.setCellWidget(number, 2, None)
                self.results_table.setItem(number, 2, QTableWidgetItem(icon(row["kind"], colors()["muted"], 18), text))
            self.results_table.setItem(number, 3, QTableWidgetItem())
            actions = QWidget()
            actions_box = QHBoxLayout(actions)
            actions_box.setContentsMargins(0, 0, 0, 0)
            actions_box.setSpacing(0)
            action = tool_button("download", "下载该项", lambda _, key=row["id"]: self.result_command(key, "result_action"))
            action.setObjectName("resultDownload")
            actions_box.addWidget(action)
            more = tool_button("more", "更多操作")
            more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(more)
            if row["kind"] == "video" and len(row.get("formats", [])) > 1:
                versions = menu.addMenu("其他编码 / 格式")
                versions.setEnabled(self.row_state(row)[0] not in ("waiting", "active"))
                groups = {}
                for entry in row["formats"]:
                    key = resolution(entry)
                    if key not in groups:
                        groups[key] = versions.addMenu(f"{key}p" if key else "来源画质")
                    option = groups[key].addAction(detail_label(entry))
                    option.setData(entry["id"])
                    option.setCheckable(True)
                    option.setChecked(entry["id"] == row.get("format_id"))
                    option.triggered.connect(lambda checked=False, key=row["id"], chosen=entry["id"]: self.result_command(key, "choose_other_format", chosen))
                menu.addSeparator()
            menu.addAction("复制标题", lambda checked=False, key=row["id"]: self.result_command(key, "copy_result", "title"))
            menu.addAction("复制来源链接", lambda checked=False, key=row["id"]: self.result_command(key, "copy_result", "url"))
            menu.addAction("查看下载队列", lambda: self.navigate(1))
            menu.addSeparator()
            menu.addAction("重新下载该项", lambda checked=False, key=row["id"]: self.result_command(key, "redownload_result"))
            menu.addAction("从列表移除此项", lambda checked=False, key=row["id"]: self.result_command(key, "remove_result"))
            more.setMenu(menu)
            actions_box.addWidget(more)
            self.results_table.setCellWidget(number, 4, actions)
        self.result_stack.setCurrentIndex(1 if rows else 0)
        self.update_empty_state()
        counts = {kind: sum(row["kind"] == kind for row in self.catalog.rows) for kind in KINDS}
        detail = " · ".join(f"{count} 项{KINDS[kind]}" for kind, count in counts.items() if count)
        prefix = f"显示 {len(rows)} / 共 {len(self.catalog.rows)} 项" if self.type_filter.currentData() or self.result_search.text() else f"共 {len(self.catalog.rows)} 项"
        self.result_summary.setText(f"{prefix}（{detail}）" if detail else "暂无提取结果")
        self.result_summary.setToolTip(self.result_summary.text())
        self.update_workbench_layout()
        self.refresh_result_status()

    def result_command(self, row_id, operation, *args):
        row = self.result_lookup.get(row_id)
        if row:
            getattr(self, operation)(row, *args)

    def copy_result(self, row, key):
        QApplication.clipboard().setText(row[key])

    def redownload_result(self, row):
        self.download_results([row], force=True)

    def set_result_format(self, row, format_id):
        if row.get("format_id", "") == format_id:
            return
        row.update(format_id=format_id, file="", job_id="", status="idle", detail="已切换画质，等待下载")
        self.persist()
        self.refresh_result_status()
        self.update_selection()

    def choose_other_format(self, row, format_id):
        self.set_result_format(row, format_id)
        self.render_results()

    def set_result_checked(self, row, checked):
        row["checked"] = checked
        self.update_selection()

    def update_selection(self):
        rows = self.visible_results()
        jobs = {job["id"]: job for job in self.jobs}
        checked = sum(bool(row.get("checked")) for row in rows)
        self.select_all.setEnabled(bool(rows))
        self.select_all.blockSignals(True)
        state = Qt.CheckState.Unchecked if not checked else Qt.CheckState.Checked if checked == len(rows) else Qt.CheckState.PartiallyChecked
        self.select_all.setCheckState(state)
        self.select_all.blockSignals(False)
        self.download_selected_button.setText(f"下载选中（{checked}）" if checked else "下载选中")
        available = [row for row in rows if self.row_state(row, jobs)[0] not in ("done", "waiting", "active")]
        self.download_selected_button.setEnabled(any(row.get("checked") for row in available))
        self.download_all_button.setEnabled(bool(available))

    def select_visible(self, checked):
        for row in self.visible_results():
            row["checked"] = checked
            position = self.result_row_map.get(row["id"])
            if position is not None:
                check = self.results_table.cellWidget(position, 0).findChild(QCheckBox)
                check.blockSignals(True)
                check.setChecked(checked)
                check.blockSignals(False)
        self.update_selection()

    def row_state(self, row, jobs=None):
        job = jobs.get(row.get("job_id")) if jobs is not None else next((job for job in self.jobs if job["id"] == row.get("job_id")), None)
        if row.get("file"):
            return "done", job
        return (job["status"] if job else row.get("status", "idle")), job

    def downloadable(self, row):
        return self.row_state(row)[0] not in ("done", "waiting", "active")

    def refresh_result_status(self, job_id=None):
        jobs = {job["id"]: job for job in self.jobs}
        for row in self.catalog.rows:
            if job_id is not None and row.get("job_id") != job_id:
                continue
            position = self.result_row_map.get(row["id"])
            if position is None:
                continue
            state, job = self.row_state(row, jobs)
            detail = job.get("detail", "") if job else row.get("detail", "")
            percent = job.get("percent", -1) if job else -1
            signature = (state, detail, percent, row.get("format_id"), row.get("file"))
            if self.result_status_signatures.get(row["id"]) == signature:
                continue
            self.result_status_signatures[row["id"]] = signature
            text = "未完成" if state == "partial" else STATES.get(state, state)
            if state == "active" and percent >= 0:
                text += f" · {round(percent)}%"
            status = self.results_table.item(position, 3)
            status.setText(text)
            status.setToolTip(detail)
            palette = colors()
            color = palette["done"] if state == "done" else palette["error"] if state in ("failed", "partial") else palette["text"] if state in ("waiting", "active") else palette["muted"]
            status.setForeground(QColor(color))
            quality_cell = self.results_table.cellWidget(position, 2)
            quality = quality_cell.findChild(QComboBox, "qualityChoice") if quality_cell else None
            if quality:
                quality.setEnabled(state not in ("waiting", "active"))
            action = self.results_table.cellWidget(position, 4).findChild(QToolButton, "resultDownload")
            set_symbol(action, "folder" if state == "done" else "queue" if state in ("waiting", "active") else "download")
            action.setToolTip("打开文件所在位置" if state == "done" else "查看下载进度" if state in ("waiting", "active") else "下载该项")
            for control in self.results_table.cellWidget(position, 4).findChildren(QToolButton):
                if control.menu():
                    for option in control.menu().actions():
                        if option.menu():
                            option.setEnabled(state not in ("waiting", "active"))
                            for group in option.menu().actions():
                                if group.menu():
                                    for choice in group.menu().actions():
                                        choice.setChecked(choice.data() == row.get("format_id"))
        self.update_selection()

    def update_empty_state(self):
        if self.extraction_active or self.extraction_waiting:
            self.empty_title.setText("正在提取内容…")
            self.empty_detail.setText("结果会陆续显示，可随时停止提取")
        elif self.catalog.rows:
            self.empty_title.setText("没有匹配的结果")
            self.empty_detail.setText("换个关键词，或切换“全部类型”")
        elif self.extraction_failures:
            self.empty_title.setText("这次提取未完成")
            self.empty_detail.setText("可重试失败链接，或查看详情")
        elif self.extraction_cancelled:
            self.empty_title.setText("提取已停止")
            self.empty_detail.setText("可修改链接后重新提取")
        else:
            self.empty_title.setText("把想保存的内容，放到这里")
            self.empty_detail.setText("粘贴链接 → 提取内容 → 选择画质并下载")

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
        self.batch_started = False
        self.extraction_failures.clear()
        self.extraction_cancelled = False
        self.retry_extract_button.hide()
        self.extract_errors_button.hide()
        self.persist()
        self.render_results()
        self.say("提取列表已清空，下载任务和文件保留。")
