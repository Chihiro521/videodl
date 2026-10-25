import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from desktop.app import Window
from desktop.storage import load_json, parse_links
import time


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


def test_batch_keeps_options_deduplicates_and_recovers(application, tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "settings"))
    window = Window()
    window.paused = True
    window.destination.setText(str(tmp_path / "下载"))
    window.options["video"].setChecked(False)
    window.links.setPlainText("分享 https://www.bilibili.com/video/BVexample1\nhttps://example.com/video.mp4")
    window.add_jobs()
    assert len(window.jobs) == 2
    window.add_jobs()
    assert len(window.jobs) == 2
    window.options["video"].setChecked(True)
    assert window.jobs[0]["options"]["video"] is False
    window.cancel_job(window.jobs[0])
    assert window.jobs[0]["status"] == "cancelled"
    window.jobs[1]["status"] = "active"
    window.persist()
    window.close()
    restored = Window()
    assert restored.jobs[1]["status"] == "interrupted"
    restored.paused = True
    restored.retry_job(restored.jobs[1])
    assert restored.jobs[1]["status"] == "waiting"
    saved = load_json(tmp_path / "settings" / "queue.json", [])
    assert saved[1]["status"] == "waiting"
    restored.close()


def test_share_text_parsing():
    assert parse_links("来看看：https://example.com/v?id=1。\nhttps://example.com/v?id=1\nhttps://other.test/a)") == ["https://example.com/v?id=1", "https://other.test/a"]
    assert parse_links("https://user:pass@example.com/x") == []
    assert parse_links("http://[ http://example.com:bad") == []


def test_qt_queue_runs_a_real_background_download(application, tmp_path, monkeypatch, media_server):
    server, _ = media_server
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    window = Window()
    window.destination.setText(str(tmp_path / "output"))
    window.links.setPlainText(server + "/sample.mp4")
    window.options["cover"].setChecked(False)
    window.common.setChecked(False)
    window.add_jobs()
    deadline = time.monotonic() + 90
    while window.running and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.02)
    assert not window.running
    assert window.jobs[0]["status"] == "done", window.jobs[0]["detail"]
    assert {f["kind"] for f in window.jobs[0]["files"]} == {"video", "audio"}
    assert not list((tmp_path / "appdata/work").glob("*"))
    window.close()


def test_cancel_stops_worker_and_removes_owned_partial_files(application, tmp_path, monkeypatch):
    import http.server
    import threading
    class SlowMedia(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", "16777216")
            self.end_headers()
        def do_GET(self):
            self.do_HEAD()
            try:
                for _ in range(16384):
                    self.wfile.write(b"x" * 1024)
                    self.wfile.flush()
                    time.sleep(0.02)
            except (OSError, ConnectionError):
                pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SlowMedia)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    window = Window()
    window.destination.setText(str(tmp_path / "output"))
    window.links.setPlainText(f"http://127.0.0.1:{server.server_port}/slow.mp4")
    for kind, check in window.options.items():
        check.setChecked(kind == "video")
    window.common.setChecked(False)
    window.add_jobs()
    worker = next(iter(window.running.values()))
    deadline = time.monotonic() + 60
    while not worker.scratch and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.02)
    assert worker.scratch, "worker did not reach a cancellable download"
    window.cancel_job(window.jobs[0])
    deadline = time.monotonic() + 10
    while window.running and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.02)
    assert not window.running
    assert window.jobs[0]["status"] == "cancelled"
    assert not list((tmp_path / "output").rglob(".media-*"))
    window.close()
    server.shutdown()
    server.server_close()
