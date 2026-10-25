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
    assert [entry["kind"] for entry in window.jobs[0]["files"]] == ["audio"]
    assert next(row for row in window.catalog.rows if row["kind"] == "video")["status"] == "idle"
    window.close()
