import json
import os
import subprocess
import sys
import pytest

from desktop.storage import save_json
from desktop.tests.test_media import variant_server


@pytest.mark.skipif(not os.environ.get("VIDEODL_TEST_EXE"), reason="requires packaged executable")
def test_frozen_package_includes_verified_downloader():
    import hashlib
    from pathlib import Path

    config_path = Path(__file__).resolve().parents[1] / "media-tools.json"
    expected = json.loads(config_path.read_text(encoding="utf-8"))["yt_dlp"]
    downloader = Path(os.environ["VIDEODL_TEST_EXE"]).parent / "_internal/tools/yt-dlp.exe"
    assert downloader.is_file()
    with downloader.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == expected["sha256"]
    environment = os.environ.copy()
    environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    result = subprocess.run([str(downloader), "--version"], capture_output=True, text=True, env=environment, timeout=30, check=True)
    assert result.stdout.strip() == expected["version"]


@pytest.mark.skipif(not os.environ.get("VIDEODL_TEST_EXE"), reason="requires packaged executable")
def test_frozen_package_uses_patched_node():
    import hashlib
    from pathlib import Path

    root = Path(os.environ["VIDEODL_TEST_EXE"]).parent
    tool_config = json.loads((Path(__file__).resolve().parents[1] / "media-tools.json").read_text(encoding="utf-8"))
    config = tool_config["nodejs"]
    nodes = list(root.rglob("node.exe"))
    assert nodes == [root / "_internal/tools/node.exe"]
    with nodes[0].open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == config["sha256"]
    result = subprocess.run([str(nodes[0]), "-p", "JSON.stringify({node:process.versions.node,brotli:process.versions.brotli})"],
        capture_output=True, text=True, timeout=30, check=True)
    versions = json.loads(result.stdout)
    assert versions["node"] == config["version"]
    assert tuple(int(part) for part in versions["brotli"].split(".")) >= (1, 2, 1)
    tools = root / "_internal/tools"
    probe = subprocess.run([str(tools / "ffprobe.exe"), "-version"], capture_output=True, text=True, timeout=30, check=True)
    assert tool_config["source_url"].rsplit("/", 1)[1] in probe.stdout.splitlines()[0]
    for library in tools.glob("av*.dll"):
        other_copy = root / "_internal" / library.name
        if other_copy.exists():
            assert hashlib.sha256(library.read_bytes()).digest() == hashlib.sha256(other_copy.read_bytes()).digest()


def test_worker_diagnostics_includes_login_components(tmp_path):
    path = tmp_path / "diagnostics.json"
    save_json(path, {"action": "diagnostics"})
    frozen = os.environ.get("VIDEODL_TEST_EXE")
    executable = [frozen] if frozen else [sys.executable, "-m", "desktop"]
    environment = os.environ.copy()
    if frozen and os.name == "nt":
        environment["PATH"] = str(__import__("pathlib").Path(os.environ["SystemRoot"]) / "System32")
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
    result = subprocess.run([*executable, "--worker", str(path)], capture_output=True, timeout=45, env=environment)
    assert result.returncode == 0
    event = json.loads(path.with_suffix(".events").read_text(encoding="utf-8").splitlines()[-1])
    assert event["event"] == "result" and event["qr_login"] and event["encrypted_storage"]
    if frozen:
        from pathlib import Path
        assert Path(event["node_path"]) == Path(frozen).parent / "_internal/tools/node.exe"
    import re
    curl_version = re.search(r"libcurl/(\d+)\.(\d+)\.(\d+)", event["curl_version"])
    brotli_version = re.search(r"brotli/(\d+)\.(\d+)\.(\d+)", event["curl_version"])
    assert curl_version and tuple(map(int, curl_version.groups())) >= (8, 23, 0)
    assert brotli_version and tuple(map(int, brotli_version.groups())) >= (1, 2, 1)


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


@pytest.mark.skipif(not os.environ.get("VIDEODL_TEST_EXE"), reason="requires packaged executable")
def test_frozen_gui_extracts_selects_and_downloads(tmp_path, media_server):
    server, _ = media_server
    command = tmp_path / "flow-input.json"
    save_json(command, {"url": server + "/sample.mp4", "output": str(tmp_path / "下载"), "kind": "audio"})
    environment = os.environ.copy()
    environment["PATH"] = str(__import__("pathlib").Path(os.environ["SystemRoot"]) / "System32")
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.update(QT_QPA_PLATFORM="offscreen", VIDEODL_DESKTOP_DATA=str(tmp_path / "appdata"),
        VIDEODL_GUI_SMOKE_REPORT=str(tmp_path / "flow-report.json"), VIDEODL_GUI_SMOKE_INPUT=str(command))
    result = subprocess.run([os.environ["VIDEODL_TEST_EXE"]], capture_output=True, env=environment, timeout=130)
    assert result.returncode == 0
    report = json.loads((tmp_path / "flow-report.json").read_text(encoding="utf-8"))
    assert not report["error"], report
    assert not report["failures"]
    assert len(report["results"]) == 2
    assert len(report["jobs"]) == 1
    assert report["jobs"][0]["status"] == "done"
    assert report["jobs"][0]["options"] == {"video": False, "audio": True, "cover": False}
    assert __import__("pathlib").Path(report["jobs"][0]["files"][0]["path"]).is_file()
    assert report["jobs"][0]["cache_hit"]


@pytest.mark.parametrize("save_mode", ["flat", "by_work", "by_type"])
def test_gui_groups_multiple_links_and_saves_chosen_way(tmp_path, media_server, save_mode):
    from pathlib import Path
    server, _ = media_server
    urls = [server + "/sample.mp4?source=first", server + "/sample.mp4?source=second"]
    command = tmp_path / "batch-input.json"
    output = tmp_path / "多链接下载"
    save_json(command, {"text": f"第一条 {urls[0]}\n第二条 {urls[1]}\n重复 {urls[0]}", "output": str(output), "kind": "all", "save_mode": save_mode, "concurrency": 2})
    environment = os.environ.copy()
    frozen = os.environ.get("VIDEODL_TEST_EXE")
    executable = [frozen] if frozen else [sys.executable, "-m", "desktop"]
    if frozen:
        environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
    environment.update(QT_QPA_PLATFORM="offscreen", VIDEODL_DESKTOP_DATA=str(tmp_path / "appdata"),
        VIDEODL_GUI_SMOKE_REPORT=str(tmp_path / "batch-report.json"), VIDEODL_GUI_SMOKE_INPUT=str(command))
    result = subprocess.run(executable, capture_output=True, env=environment, timeout=130)
    assert result.returncode == 0
    report = json.loads((tmp_path / "batch-report.json").read_text(encoding="utf-8"))
    assert not report["error"] and not report["failures"], report
    assert [group["url"] for group in report["groups"]] == urls
    assert [group["row"] for group in report["groups"]] == [0, 3]
    assert all(group["span"] == 5 for group in report["groups"])
    assert [row["source_order"] for row in report["results"]] == [0, 0, 1, 1]
    assert len(report["jobs"]) == 2 and all(job["status"] == "done" for job in report["jobs"])
    files = [Path(f["path"]) for job in report["jobs"] for f in job["files"]]
    assert len(files) == len(set(files)) == 4
    assert all(path.is_file() for path in files)
    if save_mode == "flat":
        assert all(path.parent == output for path in files)
        assert not any(path.is_dir() for path in output.iterdir())
    elif save_mode == "by_work":
        parents = [{Path(f["path"]).parent for f in job["files"]} for job in report["jobs"]]
        assert all(len(paths) == 1 for paths in parents) and parents[0] != parents[1]
        assert len(list(output.iterdir())) == 2
    else:
        assert {path.name for path in output.iterdir()} == {"视频", "音频"}
        assert all(Path(f["path"]).parent.name == {"video": "视频", "audio": "音频"}[f["kind"]] for job in report["jobs"] for f in job["files"])


@pytest.mark.skipif(not os.environ.get("VIDEODL_TEST_EXE"), reason="requires packaged executable")
@pytest.mark.parametrize("manifest", ["master.m3u8", "manifest.mpd"])
def test_frozen_gui_downloads_chosen_quality(tmp_path, variant_server, manifest):
    from pathlib import Path
    server, _ = variant_server
    command = tmp_path / "quality-input.json"
    save_json(command, {"url": server + "/" + manifest, "output": str(tmp_path / "下载"), "kind": "video", "quality_index": 1})
    environment = os.environ.copy()
    environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.update(QT_QPA_PLATFORM="offscreen", VIDEODL_DESKTOP_DATA=str(tmp_path / "appdata"),
        VIDEODL_GUI_SMOKE_REPORT=str(tmp_path / "quality-report.json"), VIDEODL_GUI_SMOKE_INPUT=str(command))
    result = subprocess.run([os.environ["VIDEODL_TEST_EXE"]], capture_output=True, env=environment, timeout=130)
    assert result.returncode == 0
    report = json.loads((tmp_path / "quality-report.json").read_text(encoding="utf-8"))
    assert not report["error"], report
    assert report["jobs"][0]["status"] == "done", report
    assert report["jobs"][0]["cache_hit"]
    row = next(row for row in report["results"] if row["kind"] == "video")
    assert [f["resolution"] for f in row["formats"]] == [360, 180]
    assert row["format_id"] == row["formats"][1]["id"]
    video = report["jobs"][0]["files"][0]
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", video["path"]]))
    assert (probe["streams"][0]["width"], probe["streams"][0]["height"]) == (320, 180)
