"""Source ownership, concurrent extraction, and group actions in the real table."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QComboBox

from desktop.app import Window
from desktop.results import ResultCatalog
from desktop.storage import load_json, parse_links
from desktop.tests.test_results import media_cell, summary


class ManualWorker(QObject):
    event = Signal(dict)
    finished = Signal(int)

    def __init__(self, command, parent):
        super().__init__(parent)
        self.command = command
        self.cancelled = False
        self.process = SimpleNamespace(waitForFinished=lambda _: True)

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


@pytest.fixture
def window(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "data"))
    monkeypatch.setattr("desktop.extraction.Worker", ManualWorker)
    current = Window()
    current.paused = True
    current.destination.setText(str(tmp_path / "下载"))
    current.show()
    application.processEvents()
    yield current
    current.close()
    application.processEvents()


def item(index=0, title="相同标题"):
    return {**summary(index=index, key=f"item-{index}", title=title), "formats": [
        {"id": "1080", "resolution": 1080, "ext": "mp4"},
        {"id": "720", "resolution": 720, "ext": "mp4"}]}


def complete(window, url, items=None, error=None):
    worker = window.extraction_active[url]
    worker.event.emit({"event": "error", "message": error} if error else {"event": "result", "items": items})
    worker.finished.emit(1 if error else 0)


def assert_ownership(window, urls):
    assert list(window.source_row_map) == urls
    current = None
    for kind, key in window.result_table_keys:
        if kind == "source":
            current = key
            position = window.source_row_map[key]
            assert window.results_table.columnSpan(position, 0) == 5
        else:
            assert window.result_lookup[key]["url"] == current
    assert len(window.result_row_map) == len(window.visible_results())


@pytest.mark.parametrize("text, expected", [
    ("", []),
    ("这段文字没有链接", []),
    ("https://example.test/a https://example.test/b", ["https://example.test/a", "https://example.test/b"]),
    ("来看视频：https://example.test/a。\n复制 https://example.test/b)\nhttps://example.test/a", ["https://example.test/a", "https://example.test/b"]),
    ("http://[ https://example.test:bad/x https://user:pass@example.test/a", []),
])
def test_link_input_recognizes_share_text_and_first_occurrence(text, expected):
    assert parse_links(text) == expected


@pytest.mark.parametrize("count, accepted", [(0, False), (1, True), (200, True), (201, False)])
def test_batch_limits_apply_before_replacing_existing_results(window, count, accepted):
    old = window.catalog.replace_summary("https://example.test/old", [item()])
    window.download_results([old[0]])
    old_job = window.jobs[0]
    urls = [f"https://example.test/{n}" for n in range(count)]
    window.links.setPlainText("\n".join(urls + urls[:2]))
    assert len(parse_links(window.links.toPlainText())) == count
    assert f"{count}" in window.link_count.text() or not count
    window.start_preview()
    if accepted:
        assert window.catalog.source_urls() == urls
        assert not window.catalog.rows and not window.jobs
        assert len(window.source_headers) == count
        assert not window.source_headers[urls[-1]].select.isEnabled()
        assert not window.source_headers[urls[-1]].download.isEnabled()
    else:
        assert window.catalog.rows == old
        assert window.jobs == [old_job]
        assert not window.extraction_active and not window.extraction_waiting


def test_reverse_completion_keeps_groups_and_existing_controls(window):
    urls = [f"https://example.test/{key}" for key in "abc"]
    window.links.setPlainText(" ".join(urls))
    window.start_preview()
    assert_ownership(window, urls)
    assert "提取中" in window.source_headers[urls[0]].detail.text()
    assert "等待" in window.source_headers[urls[2]].detail.text()
    complete(window, urls[1], [item(0), item(1)])
    b = next(row for row in window.catalog.rows if row["url"] == urls[1] and row["kind"] == "video")
    combo = media_cell(window, 2, b).findChild(QComboBox)
    combo.setCurrentIndex(1)
    combo.setFocus()
    b["checked"] = True
    header = window.source_headers[urls[1]]
    complete(window, urls[0], [item(0), item(1), item(2)])
    assert_ownership(window, urls)
    assert media_cell(window, 2, b).findChild(QComboBox) is combo
    assert combo.currentData() == "720" and combo.hasFocus() and b["checked"]
    assert window.source_headers[urls[1]] is header
    complete(window, urls[2], [item(0)])
    assert not window.extraction_active and not window.extraction_waiting
    assert_ownership(window, urls)
    assert [row["index"] for row in window.catalog.rows if row["kind"] == "video"] == [0, 1, 2, 0, 1, 0]
    assert len({row["id"] for row in window.catalog.rows}) == len(window.catalog.rows)
    assert not window.jobs, "headers and extraction must not create download jobs"
    saved = load_json(window.store / "results.json", [])
    restored = ResultCatalog(saved[::-1])
    assert restored.source_urls() == urls
    assert all(row["source_order"] == urls.index(row["url"]) for row in saved)


def test_group_and_global_actions_respect_filters_and_mixed_quality(window):
    a, b = "https://example.test/a", "https://example.test/b"
    rows_a = window.catalog.replace_summary(a, [item(0), item(1)])
    rows_b = window.catalog.replace_summary(b, [item(0)])
    window.render_results()
    window.type_filter.setCurrentIndex(window.type_filter.findData("video"))
    combo = media_cell(window, 2, rows_a[0]).findChild(QComboBox)
    combo.setCurrentIndex(1)
    window.source_headers[a].select.click()
    assert all(row["checked"] == (row["kind"] == "video") for row in rows_a)
    assert not any(row["checked"] for row in rows_b)
    assert window.select_all.checkState().name == "PartiallyChecked"
    window.result_search.setText("无匹配内容")
    window.render_results()
    assert not window.source_headers and window.result_stack.currentIndex() == 0
    window.result_search.clear()
    window.render_results()
    assert rows_a[0]["format_id"] == "720" and rows_a[0]["checked"]
    window.source_headers[b].download.click()
    assert len(window.jobs) == 1 and window.jobs[0]["url"] == b
    assert window.jobs[0]["options"] == {"video": True, "audio": False, "cover": False}
    window.download_selected_button.click()
    assert len(window.jobs) == 3
    assert [job["format_ids"] for job in window.jobs[1:]] == [{"item-0": "720"}, {"item-1": "1080"}]
    window.type_filter.setCurrentIndex(window.type_filter.findData("audio"))
    assert not any(row["checked"] for row in window.visible_results())
    window.download_all_button.click()
    assert len(window.jobs) == 6
    assert all(job["options"] == {"video": False, "audio": True, "cover": False} for job in window.jobs[3:])


def test_failed_source_retries_while_others_continue(window):
    a, b, c = [f"https://example.test/{key}" for key in "abc"]
    window.links.setPlainText("\n".join((a, b, c)))
    window.start_preview()
    b_worker = window.extraction_active[b]
    complete(window, a, error="来源暂时无法访问")
    assert "失败" in window.source_headers[a].detail.text()
    assert window.source_headers[a].retry.isVisible()
    assert window.source_headers[a].detail.toolTip() == "来源暂时无法访问"
    window.source_headers[a].retry.click()
    assert window.extraction_active[b] is b_worker
    assert window.extraction_waiting == [a] and window.extraction_total == 4
    assert "等待" in window.source_headers[a].detail.text()
    complete(window, c, [item()])
    assert a in window.extraction_active
    complete(window, a, [item()])
    complete(window, b, [item()])
    assert not window.extraction_failures
    assert_ownership(window, [a, b, c])
    assert len(window.catalog.rows) == 9
    assert not window.source_headers[a].retry.isVisible()


def test_empty_result_and_cancelled_pending_groups_can_retry(window):
    urls = [f"https://example.test/{key}" for key in "abcd"]
    window.links.setPlainText("\n".join(urls))
    window.start_preview()
    complete(window, urls[0], [])
    assert urls[0] in window.extraction_failures
    window.cancel_extraction()
    for url in list(window.extraction_active):
        window.extraction_active[url].finished.emit(0)
    assert not window.extraction_active and not window.extraction_waiting
    assert window.source_states[urls[3]] == "cancelled"
    assert window.source_headers[urls[3]].retry.isVisible()
    window.source_headers[urls[3]].retry.click()
    assert list(window.extraction_active) == [urls[3]]
    assert urls[0] in window.extraction_failures
    complete(window, urls[3], [item()])
    assert_ownership(window, urls)


def test_legacy_records_group_by_first_appearance_and_keep_media_identity():
    original = ResultCatalog()
    a = original.replace_summary("https://example.test/a", [item()])
    b = original.replace_summary("https://example.test/b", [item()])
    legacy = [{key: value for key, value in row.items() if key != "source_order"} for row in [b[0], a[0], b[1], a[1]]]
    restored = ResultCatalog(legacy)
    assert restored.source_urls() == [b[0]["url"], a[0]["url"]]
    assert [row["id"] for row in restored.rows] == [b[0]["id"], b[1]["id"], a[0]["id"], a[1]["id"]]
    refreshed = restored.replace_summary(a[0]["url"], [item(title="刷新后的标题")])
    assert refreshed[0]["id"] == a[0]["id"]
    assert len(restored.plan(restored.rows)) == 2
