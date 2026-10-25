import json
import os
import subprocess
import sys
import pytest

from desktop.storage import save_json


def test_worker_process_protocol_and_all_outputs(tmp_path, media_server):
    server, _ = media_server
    path = tmp_path / "command.json"
    save_json(path, {"action": "download", "url": server + "/sample.mp4", "common": False,
                     "output": str(tmp_path / "output"), "options": {"audio": True, "video": True}})
    frozen = os.environ.get("VIDEODL_TEST_EXE")
    executable = [frozen] if frozen else [sys.executable, "-m", "desktop"]
    environment = os.environ.copy()
    if frozen and os.name == "nt":
        environment["PATH"] = str(__import__("pathlib").Path(os.environ["SystemRoot"]) / "System32")
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
    result = subprocess.run([*executable, "--worker", str(path)], capture_output=True, timeout=120, env=environment)
    assert result.returncode == 0, result.stderr.decode(errors="replace")[-2000:]
    events = [json.loads(line) for line in path.with_suffix(".events").read_text(encoding="utf-8").splitlines()]
    assert events[0]["event"] == "progress"
    assert any(e["event"] == "parsed" for e in events)
    assert {e["kind"] for e in events if e["event"] == "file"} == {"audio", "video"}
    assert events[-1]["event"] == "result"
    assert events[-1]["status"] == "done"


@pytest.mark.skipif(not os.environ.get("VIDEODL_TEST_EXE"), reason="requires packaged executable")
def test_frozen_gui_starts_without_a_system_python(tmp_path):
    environment = os.environ.copy()
    environment["PATH"] = str(__import__("pathlib").Path(os.environ["SystemRoot"]) / "System32")
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["VIDEODL_DESKTOP_DATA"] = str(tmp_path / "appdata")
    environment["VIDEODL_GUI_SMOKE_REPORT"] = str(tmp_path / "gui.json")
    result = subprocess.run([os.environ["VIDEODL_TEST_EXE"]], capture_output=True, env=environment, timeout=40)
    assert result.returncode == 0
    report = json.loads((tmp_path / "gui.json").read_text(encoding="utf-8"))
    assert report["visible"]
    assert report["width"] >= 940
    assert (tmp_path / "gui.png").stat().st_size > 20000
