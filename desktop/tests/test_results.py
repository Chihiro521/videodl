import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest
from PySide6.QtWidgets import QApplication

from desktop.app import Window
from desktop.results import ResultCatalog
from desktop.storage import load_json


def summary(index=0, key="a" * 64, title="示例标题"):
    return {"index": index, "item_key": key, "title": title, "source": "ExampleVideoClient", "ext": "mp4",
            "audio_ext": "m4a", "has_cover": True, "separate_audio": False, "media_kind": "video"}


def test_result_types_refresh_and_group_only_selected_content():
    catalog = ResultCatalog()
    rows = catalog.replace_summary("https://example.test/a", [summary()])
    assert [row["kind"] for row in rows] == ["video", "audio", "cover"]
    selected = [row for row in rows if row["kind"] != "cover"]
    plans = catalog.plan(selected)
    assert len(plans) == 1
    assert plans[0]["options"] == {"video": True, "audio": True, "cover": False}
    assert plans[0]["item_keys"] == ["a" * 64]
    catalog.replace_summary("https://example.test/a", [summary(index=1, title="更新后的标题")])
    assert len(catalog.rows) == 3
    assert all(row["index"] == 1 for row in catalog.rows)
    assert len(catalog.visible("audio", "更新")) == 1
    catalog.replace_summary("https://example.test/b", [{**summary(key="b" * 64), "media_kind": "audio", "has_cover": False}])
    assert len(catalog.rows) == 4
    assert catalog.rows[-1]["kind"] == "audio"


def test_partial_result_tracks_success_for_each_type():
    catalog = ResultCatalog()
    rows = catalog.replace_summary("https://example.test/a", [summary()])
    job = {"id": "test-job", "result_ids": [row["id"] for row in rows], "status": "waiting", "files": []}
    catalog.link_job(job)
    job.update(status="partial", detail="音频下载未完成", files=[{"kind": "video", "path": "D:/output/a.mp4", "item_key": "a" * 64}])
    catalog.sync_job(job)
    assert next(row for row in rows if row["kind"] == "video")["status"] == "done"
    assert next(row for row in rows if row["kind"] == "audio")["status"] == "failed"
    assert next(row for row in rows if row["kind"] == "cover")["file"] == ""


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


def spin(application, condition, timeout=90):
    deadline = time.monotonic() + timeout
    while condition() and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.02)
    assert not condition(), "background operation did not finish"


def test_batch_extract_filter_select_download_and_restore(application, tmp_path, monkeypatch, media_server):
    server, _ = media_server
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    window = Window()
    window.destination.setText(str(tmp_path / "下载"))
    window.common.setChecked(False)
    window.links.setPlainText(server + "/sample.mp4\n" + server + "/audio.m4a")
    window.start_preview()
    spin(application, lambda: bool(window.extraction_active or window.extraction_waiting))
    assert not window.extraction_failures
    assert len(window.catalog.rows) == 3
    assert len(window.jobs) == 0, "manual extraction must not start downloads"
    window.type_filter.setCurrentIndex(window.type_filter.findData("video"))
    assert window.results_table.rowCount() == 1
    window.select_visible(True)
    window.download_selected()
    spin(application, lambda: bool(window.running))
    assert len(window.jobs) == 1
    assert window.jobs[0]["options"] == {"video": True, "audio": False, "cover": False}
    video = next(row for row in window.catalog.rows if row["kind"] == "video")
    assert video["status"] == "done", window.jobs[0]["detail"]
    assert window.jobs[0]["cache_hit"], "download should reuse the extracted object in a live engine"
    assert video["file"].endswith(".mp4")
    assert all(row["status"] == "idle" for row in window.catalog.rows if row["kind"] == "audio")
    stored = load_json(tmp_path / "appdata/results.json", [])
    assert len(stored) == 3
    assert all("download_url" not in row and "thumbnail" not in row for row in stored)
    window.close()
    restored = Window()
    assert len(restored.catalog.rows) == 3
    assert next(row for row in restored.catalog.rows if row["kind"] == "video")["file"] == video["file"]
    restored.clear_results()
    assert len(restored.jobs) == 1, "clearing results must preserve download history"
    assert __import__("pathlib").Path(video["file"]).is_file()
    restored.close()


def test_selected_types_of_one_item_use_one_queue_job(application, tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    window = Window()
    window.paused = True
    window.destination.setText(str(tmp_path / "output"))
    rows = window.catalog.replace_summary("https://example.test/a", [summary()])
    window.render_results()
    for row in rows:
        row["checked"] = row["kind"] != "cover"
    window.download_selected()
    assert len(window.jobs) == 1
    assert len(window.jobs[0]["result_ids"]) == 2
    assert window.jobs[0]["options"] == {"video": True, "audio": True, "cover": False}
    window.download_selected()
    assert len(window.jobs) == 1
    window.close()


def test_auto_download_respects_type_preferences(application, tmp_path, monkeypatch, media_server):
    server, _ = media_server
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    window = Window()
    window.destination.setText(str(tmp_path / "output"))
    window.common.setChecked(False)
    for kind, check in window.options.items():
        check.setChecked(kind == "audio")
    window.auto_download.setChecked(True)
    window.links.setPlainText(server + "/sample.mp4")
    window.start_preview()
    spin(application, lambda: bool(window.extraction_active or window.extraction_waiting or window.running))
    assert len(window.jobs) == 1
    assert window.jobs[0]["status"] == "done", window.jobs[0]["detail"]
    assert window.jobs[0]["cache_hit"], "auto-download must wait for the parsing engine to be reusable"
    assert [entry["kind"] for entry in window.jobs[0]["files"]] == ["audio"]
    assert next(row for row in window.catalog.rows if row["kind"] == "video")["status"] == "idle"
    window.close()


def test_inline_quality_survives_filter_and_changes_download_plan(application, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QComboBox
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    window = Window()
    window.paused = True
    window.destination.setText(str(tmp_path / "output"))
    formats = [{"id": "high", "label": "1080p-MP4"}, {"id": "low", "label": "720p-MP4"}]
    rows = window.catalog.replace_summary("https://example.test/a", [{**summary(), "formats": formats, "identity_version": 2}])
    window.render_results()
    combo = window.results_table.cellWidget(0, 2).findChild(QComboBox, "qualityChoice")
    assert combo.currentData() == "high"
    combo.setCurrentIndex(1)
    window.type_filter.setCurrentIndex(window.type_filter.findData("audio"))
    window.type_filter.setCurrentIndex(window.type_filter.findData("video"))
    combo = window.results_table.cellWidget(0, 2).findChild(QComboBox, "qualityChoice")
    assert combo.currentData() == "low"
    window.download_results([rows[0]])
    assert window.jobs[0]["format_ids"] == {"a" * 64: "low"}
    assert not window.results_table.cellWidget(0, 2).findChild(QComboBox, "qualityChoice").isEnabled()
    window.close()


def test_legacy_failed_record_downloads_without_manual_reextract(application, tmp_path, monkeypatch, media_server):
    server, _ = media_server
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    window = Window()
    window.destination.setText(str(tmp_path / "output"))
    window.common.setChecked(False)
    rows = window.catalog.replace_summary(server + "/sample.mp4", [{**summary(key="legacy-changing-title-key"), "identity_version": 1}])
    rows[0]["status"] = "failed"
    window.download_results([rows[0]])
    spin(application, lambda: bool(window.running))
    assert window.jobs[0]["status"] == "done", window.jobs[0]["detail"]
    assert rows[0]["status"] == "done"
    assert rows[0]["identity_version"] == 2
    assert rows[0]["item_key"] != "legacy-changing-title-key"
    window.close()


def test_new_extract_clears_old_rows_and_pending_jobs_at_click_only(application, tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    window = Window()
    window.paused = True
    window.destination.setText(str(tmp_path / "output"))
    rows = window.catalog.replace_summary("https://example.test/old", [summary()])
    window.download_results([rows[0]])
    pending = window.jobs[0]
    active = {**pending, "id": "active", "status": "active"}
    done = {**pending, "id": "done", "status": "done"}
    saved_file = tmp_path / "downloaded.mp4"
    saved_file.write_bytes(b"saved")
    done["files"] = [{"path": str(saved_file), "kind": "video"}]
    window.jobs += [active, done]
    worker = SimpleNamespace(cancel=lambda: pytest.fail("active download was cancelled"))
    window.running["active"] = worker
    window.links.setPlainText("https://example.test/new")
    assert len(window.catalog.rows) == 3 and len(window.jobs) == 3
    monkeypatch.setattr(window, "pump_extraction", lambda: None)
    window.begin_extraction([])
    assert len(window.catalog.rows) == 3
    window.start_preview()
    assert not window.catalog.rows
    assert window.jobs == [active]
    assert window.running["active"] is worker
    assert saved_file.read_bytes() == b"saved"
    assert not load_json(tmp_path / "appdata/results.json", None)
    assert [j["id"] for j in load_json(tmp_path / "appdata/queue.json", [])] == ["active"]
    window.running.clear()
    window.close()


def test_retry_failed_extraction_keeps_successes(application, tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    window = Window()
    window.destination.setText(str(tmp_path / "output"))
    window.catalog.replace_summary("https://example.test/success", [summary()])
    window.extraction_failures["https://example.test/failed"] = "failed"
    monkeypatch.setattr(window, "pump_extraction", lambda: None)
    window.retry_extraction()
    assert len(window.catalog.rows) == 3
    assert window.extraction_waiting == ["https://example.test/failed"]
    window.close()


def test_compact_menu_advanced_choice_and_mixed_batch(application, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QComboBox, QToolButton
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    window = Window()
    window.paused = True
    window.destination.setText(str(tmp_path / "output"))
    formats = [{"id": f"{p}-{c}", "resolution": p, "codec": c, "ext": "mp4"}
               for p in (1080, 720) for c in ("avc1", "av01")]
    a = window.catalog.replace_summary("https://example.test/a", [{**summary(), "formats": formats}])[0]
    b = window.catalog.replace_summary("https://example.test/b", [{**summary(key="b"*64), "formats": formats}])[0]
    window.type_filter.setCurrentIndex(window.type_filter.findData("video"))
    window.render_results()
    combo = window.results_table.cellWidget(0, 2).findChild(QComboBox, "qualityChoice")
    assert combo.count() == 2 and combo.itemText(0) == "1080p-MP4"
    menus = [button.menu() for button in window.results_table.cellWidget(0, 4).findChildren(QToolButton) if button.menu()]
    versions = menus[0].actions()[0].menu()
    options = [a for group in versions.actions() for a in group.menu().actions()]
    assert len(options) == 4
    window.choose_other_format(a, "1080-av01")
    combo = window.results_table.cellWidget(0, 2).findChild(QComboBox, "qualityChoice")
    assert combo.count() == 2 and combo.currentData() == "1080-av01"
    window.set_result_format(b, "720-avc1")
    window.download_results([a, b])
    assert [list(job["format_ids"].values())[0] for job in window.jobs] == ["1080-av01", "720-avc1"]
    window.close()
