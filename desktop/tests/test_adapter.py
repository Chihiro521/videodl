import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from desktop.adapter import Adapter, DesktopError, check_contract, filename


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_upstream_contract():
    result = check_contract()
    assert result["platforms"] > 0
    assert result["common"] > 0


def parse_fixture(adapter, server):
    infos = adapter.parse(server + "/sample.mp4")
    assert infos
    infos[0].title = "中文测试 feat.歌手 (字幕)"
    infos[0].cover_url = server + "/cover.png"
    return infos


def test_three_outputs_and_collision_are_real_files(tmp_path, media_server):
    server, source = media_server
    adapter = Adapter(tmp_path, common=False)
    infos = parse_fixture(adapter, server)
    result = adapter.download(infos, {"cover": True, "audio": True, "video": True})
    assert result["status"] == "done", result["errors"]
    files = {f["kind"]: Path(f["path"]) for f in result["files"]}
    assert set(files) == {"cover", "audio", "video"}
    assert digest(files["video"]) == digest(source / "sample.mp4")
    assert digest(files["cover"]) == digest(source / "cover.png")
    streams = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(files["audio"])]))["streams"]
    assert [s["codec_type"] for s in streams] == ["audio"]
    assert streams[0]["codec_name"] == "aac"
    assert files["audio"].stem == infos[0].title
    # Stream packet hashes must match: extraction must not re-encode audio.
    def packet_hashes(path):
        return subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_packets", "-show_data_hash", "sha256", "-show_entries", "packet=data_hash", "-of", "csv=p=0", str(path)])
    assert packet_hashes(files["audio"]) == packet_hashes(source / "sample.mp4")
    again = adapter.download(infos, {"video": True})
    assert again["status"] == "done"
    assert Path(again["files"][0]["path"]) != files["video"]
    assert files["video"].is_file()


def test_audio_only_leaves_no_video_or_temporary_files(tmp_path, media_server):
    server, _ = media_server
    adapter = Adapter(tmp_path, common=False)
    result = adapter.download(parse_fixture(adapter, server), {"audio": True})
    assert result["status"] == "done", result["errors"]
    assert [f["kind"] for f in result["files"]] == ["audio"]
    assert not list(tmp_path.rglob("*.mp4"))
    assert not [p for p in tmp_path.rglob("*") if p.name.startswith((".media-", ".audio-"))]


def test_separate_audio_is_downloaded_directly(tmp_path, media_server):
    server, source = media_server
    adapter = Adapter(tmp_path, common=False)
    infos = parse_fixture(adapter, server)
    infos[0].audio_download_url = server + "/audio.m4a"
    infos[0].audio_ext = "m4a"
    result = adapter.download(infos, {"audio": True})
    assert result["status"] == "done", result["errors"]
    assert digest(result["files"][0]["path"]) == digest(source / "audio.m4a")
    assert not list(tmp_path.rglob("*.mp4"))


def test_missing_cover_reports_partial_not_success(tmp_path, media_server):
    server, _ = media_server
    adapter = Adapter(tmp_path, common=False)
    infos = parse_fixture(adapter, server)
    infos[0].cover_url = None
    result = adapter.download(infos, {"cover": True, "video": True})
    assert result["status"] == "partial"
    assert len(result["errors"]) == 1
    assert len(result["files"]) == 1


def test_rejects_no_selection_and_invalid_links(tmp_path):
    adapter = Adapter(tmp_path, common=False)
    with pytest.raises(DesktopError):
        adapter.parse("file:///C:/test.mp4")
    with pytest.raises(DesktopError):
        adapter.download([], {"cover": True})
    assert ".." not in filename("../中文<测试>..")
