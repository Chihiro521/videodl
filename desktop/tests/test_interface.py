"""Interaction invariants for the compact home and reused result controls."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QToolButton

from desktop.app import Window
from desktop.storage import load_json
from desktop.tests.test_results import media_cell, summary
from desktop.theme import DARK, LIGHT


@pytest.fixture
def window(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    current = Window()
    current.paused = True
    current.destination.setText(str(tmp_path / "output"))
    current.show()
    application.processEvents()
    yield current
    current.close()
    application.processEvents()


def drain(milliseconds=0):
    deadline = time.monotonic() + milliseconds / 1000
    while True:
        QApplication.processEvents()
        if time.monotonic() >= deadline:
            break
        time.sleep(0.005)


def add_rows(window, count=1):
    for i in range(count):
        window.catalog.replace_summary(f"https://example.test/{i}", [{**summary(key=str(i)),
            "formats": [{"id": "1080", "resolution": 1080, "ext": "mp4"}, {"id": "720", "resolution": 720, "ext": "mp4"}]}])
    window.render_results()
    drain()


def test_home_results_no_match_failures_and_clear(window, monkeypatch):
    assert window.home_intro.isVisible() and not window.results_panel.isVisible()
    assert window.input_frame.width() == 720
    window.links.setPlainText("\n".join(f"https://example.test/{i}" for i in range(10)))
    drain(25)
    assert 46 < window.links.height() <= window.links.fontMetrics().lineSpacing() * 4 + 24
    monkeypatch.setattr(window, "pump_extraction", lambda: None)
    window.start_preview()
    assert not window.home_intro.isVisible() and window.results_panel.isVisible()
    window.extraction_waiting.clear()
    window.extraction_failures["https://example.test/0"] = "未完成"
    window.render_results()
    assert window.empty_title.text() == "这次提取未完成"
    add_rows(window)
    window.result_search.setText("不存在的标题")
    assert window.result_search_timer.isActive()
    drain(180)
    assert not window.home_intro.isVisible()
    assert window.result_stack.currentIndex() == 0
    assert window.empty_title.text() == "没有匹配的结果"
    window.clear_results()
    assert window.home_intro.isVisible() and not window.results_panel.isVisible()


def test_controls_scroll_and_latest_metadata_survive_repeated_refresh(window):
    add_rows(window, 40)
    first_check = media_cell(window, 0).findChild(QCheckBox)
    assert first_check.visibleRegion().boundingRect().width() == first_check.width()
    bar = window.results_table.verticalScrollBar()
    bar.setValue(180)
    check = media_cell(window, 0).findChild(QCheckBox)
    combo = media_cell(window, 2).findChild(QComboBox)
    combo.setFocus()
    for _ in range(10):
        window.render_results()
        window.refresh_result_status()
    assert media_cell(window, 2).findChild(QComboBox) is combo
    assert media_cell(window, 0).findChild(QCheckBox) is check
    assert bar.value() == 180 and combo.hasFocus()
    old = window.catalog.rows[0]
    new = window.catalog.replace_summary(old["url"], [{**summary(index=7, key=old["item_key"]), "formats": old["formats"]}])[0]
    assert new is not old
    window.render_results()
    assert media_cell(window, 2).findChild(QComboBox) is combo
    combo.setCurrentIndex(1)
    check.setChecked(True)
    assert new["format_id"] == "720" and new["checked"]
    assert old["format_id"] == "1080" and not old["checked"]
    menus = [control.menu() for control in media_cell(window, 4).findChildren(QToolButton) if control.menu()]
    versions = menus[0].actions()[0].menu()
    choices = [choice for group in versions.actions() for choice in group.menu().actions()]
    assert [choice.data() for choice in choices if choice.isChecked()] == ["720"]
    window.download_selected()
    assert window.jobs[0]["indices"] == [7]
    assert window.jobs[0]["format_ids"] == {"0": "720"}


def test_progress_is_coalesced_and_terminal_state_is_immediate(window, monkeypatch):
    add_rows(window)
    row = window.catalog.rows[0]
    window.download_results([row])
    job = window.jobs[0]
    job["status"] = "active"
    window.catalog.sync_job(job)
    window.render_queue()
    window.refresh_result_status()
    combo = media_cell(window, 2).findChild(QComboBox)
    progress = window.table.cellWidget(0, 3)
    updates = []
    refresh = window.refresh_result_status
    monkeypatch.setattr(window, "refresh_result_status", lambda job_id=None: (updates.append(job_id), refresh(job_id)))
    for percent in range(60):
        window.job_event(job, {"event": "progress", "percent": percent, "detail": "正在下载"})
    assert not updates
    drain(95)
    assert updates == [job["id"]]
    assert progress.value() == 59
    assert media_cell(window, 2).findChild(QComboBox) is combo
    assert window.table.cellWidget(0, 3) is progress
    window.job_event(job, {"event": "progress", "percent": 90})
    window.job_event(job, {"event": "result", "status": "done", "files": [{"path": "D:/file.mp4", "kind": "video", "item_key": "0", "format_id": "1080"}]})
    assert window.results_table.item(window.result_row_map[window.catalog.rows[0]["id"]], 3).text() == "已完成"
    assert job["id"] not in window.pending_progress


def test_wheel_passes_quality_and_theme_preserves_choices(window):
    add_rows(window, 20)
    combo = media_cell(window, 2).findChild(QComboBox)
    combo.setFocus()
    event = QWheelEvent(QPointF(8, 8), QPointF(8, 8), QPoint(), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(combo, event)
    assert combo.currentData() == "1080"
    assert window.results_table.smooth_scroll.animation.endValue() > 0
    combo.setCurrentIndex(1)
    window.select_visible(True)
    for name, palette in (("dark", DARK), ("light", LIGHT), ("dark", DARK)):
        window.theme_control.setCurrentIndex(window.theme_control.findData(name))
        assert QApplication.instance().desktop_colors == palette
        assert window.catalog.rows[0]["format_id"] == "720"
        assert all(row["checked"] for row in window.catalog.rows)
        assert media_cell(window, 2).findChild(QComboBox).currentData() == "720"
    assert load_json(window.store / "settings.json", {})["theme"] == "dark"
    restored = Window()
    assert restored.settings["theme"] == "dark"
    assert not restored.home_intro.isVisible()
    assert media_cell(restored, 2).findChild(QComboBox).currentData() == "720"
    restored.close()


def test_save_mode_is_remembered_and_queue_keeps_its_original_choice(window):
    add_rows(window, 2)
    assert window.save_mode.currentData() == "flat"
    window.save_mode.setCurrentIndex(window.save_mode.findData("by_work"))
    first, second = [row for row in window.catalog.rows if row["kind"] == "video"]
    window.download_results([first])
    window.save_mode.setCurrentIndex(window.save_mode.findData("by_type"))
    window.download_results([second])
    assert [job["save_mode"] for job in window.jobs] == ["by_work", "by_type"]
    for kind in ("audio", "video", "cover"):
        window.type_filter.setCurrentIndex(window.type_filter.findData(kind))
        assert window.download_all_button.text() == "批量下载" + {"audio": "音频", "video": "视频", "cover": "封面"}[kind]
    window.persist()
    restored = Window()
    assert restored.save_mode.currentData() == "by_type"
    assert [job["save_mode"] for job in restored.jobs] == ["by_work", "by_type"]
    restored.close()
