import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop.adapter import Adapter, DesktopError
from desktop.media import canonical_url, media_key, normalize_formats, public_formats
from desktop.results import ResultCatalog
from desktop.session import Session


def test_canonical_douyin_modal_short_and_source_identity():
    assert canonical_url("https://www.douyin.com/video/111/search/test?aid=2abc&modal_id=222") == "https://www.douyin.com/video/222"
    assert canonical_url("https://www.douyin.com/search/test?modal_id=222") == "https://www.douyin.com/video/222"
    assert canonical_url("https://www.douyin.com.evil.test/video/111?modal_id=222").startswith("https://www.douyin.com.evil.test/")
    assert canonical_url("https://youtu.be/example?t=30") == "https://www.youtube.com/watch?v=example"
    first = SimpleNamespace(source="PVVideoClient", title="2026-10-25-02-10-59 PVVideoClient-unknowtitle",
        identifier="2026-10-25-02-10-59 PVVideoClient-unknowtitle", _desktop_url="https://www.douyin.com/video/222", _desktop_single=True)
    second = copy.deepcopy(first)
    second.source, second.title, second.identifier = "DouyinVideoClient", "真实标题", "222"
    assert media_key(first) == media_key(second)


def test_format_resources_refresh_without_exposing_signed_urls():
    resources = [{"format_id": "high", "url": "https://cdn.test/a?signature=old", "width": 1080, "height": 1920, "ext": "mp4"},
        {"format_id": "low", "url": "https://cdn.test/b", "width": 720, "height": 1280, "ext": "mp4"}]
    formats = normalize_formats(resources)
    assert [f["label"] for f in formats] == ["1080p-MP4", "720p-MP4"]
    refreshed = normalize_formats([{**r, "url": "https://other.test/new?signature=new"} for r in reversed(resources)])
    assert [f["id"] for f in formats] == [f["id"] for f in refreshed]
    public = json.dumps(public_formats(formats))
    assert "signature" not in public and "cdn.test" not in public and '"url"' not in public


def test_intermediate_generation_jobs_are_not_download_options(tmp_path):
    adapter = Adapter(tmp_path, common=False)
    raw = {"api": {"mediaItems": [{"type": "video", "mediaQuality": "1080p", "mediaUrl": "https://jobs.test/high"},
        {"type": "video", "mediaQuality": "720p", "mediaUrl": "https://jobs.test/low"}]}}
    info = adapter.new_info(source="YouTubeVideoClient", title="真实视频标题", identifier="video-id", raw_data=raw,
        download_url="https://cdn.test/actual.mp4")
    adapter.parser.deadline = 0
    adapter.parser.enrich([info], "https://www.youtube.com/watch?v=video-id")
    formats = info._desktop_formats
    assert len(formats) == 1
    assert formats[0]["url"] == "https://cdn.test/actual.mp4"


def test_cache_expires_evicts_and_reuses_opaque_objects(tmp_path, monkeypatch):
    import desktop.adapter
    now, calls = [0], []
    opaque = object()
    class FakeAdapter:
        def __init__(self, output, report, common=True):
            pass
        def parse(self, url):
            calls.append(url)
            return [opaque]
        def summary(self, infos):
            assert infos[0] is opaque
            return {"items": []}
        def download(self, infos, *args):
            assert infos[0] is opaque
            return {"status": "done", "files": [{"kind": "video"}], "errors": []}
    monkeypatch.setattr(desktop.adapter, "Adapter", FakeAdapter)
    session = Session(capacity=2, clock=lambda: now[0])
    command = {"action": "parse", "url": "https://example.test/a", "output": str(tmp_path)}
    events = []
    report = lambda event, **values: events.append({"event": event, **values})
    assert not session.execute(command, report)["cache_hit"]
    session.execute({**command, "action": "download", "options": {"video": True}}, report)
    assert len(calls) == 1
    assert next(e for e in reversed(events) if e["event"] == "parsed")["cache_hit"]
    now[0] = 601
    session.execute(command, report)
    assert len(calls) == 2
    for name in ("b", "c"):
        session.execute({**command, "url": "https://example.test/" + name}, report)
    session.execute(command, report)
    assert calls.count(command["url"]) == 3


def test_format_selection_is_part_of_the_download_record():
    catalog = ResultCatalog()
    formats = public_formats(normalize_formats([{"id": "high", "url": "https://cdn.test/high", "height": 1080},
        {"id": "low", "url": "https://cdn.test/low", "height": 720}]))
    rows = catalog.replace_summary("https://example.test/a", [{"index": 0, "item_key": "asset", "title": "视频标题", "formats": formats}])
    row = rows[0]
    row["format_id"] = formats[1]["id"]
    plan = catalog.plan([row])[0]
    assert plan["format_ids"] == {"asset": formats[1]["id"]}
    catalog.replace_summary(row["url"], [{"index": 0, "item_key": "asset", "title": "新标题", "formats": formats}])
    assert catalog.rows[0]["format_id"] == formats[1]["id"]
    job = {"id": "job", "status": "done", "result_ids": [catalog.rows[0]["id"]],
        "files": [{"kind": "video", "item_key": "asset", "format_id": formats[0]["id"], "path": "high.mp4"}]}
    catalog.link_job(job)
    catalog.sync_job(job)
    assert catalog.rows[0]["status"] != "done"


def test_expired_cached_video_refresh_keeps_already_saved_cover(tmp_path, monkeypatch):
    import desktop.adapter
    calls, requested = [], []
    class FakeAdapter:
        def __init__(self, *args, **kwargs):
            pass
        def parse(self, url):
            calls.append(url)
            return [len(calls)]
        def summary(self, infos):
            return {"items": []}
        def download(self, infos, options, *args):
            requested.append(options.copy())
            if len(calls) == 1:
                return {"status": "partial", "files": [{"kind": "cover", "path": "cover.jpg"}], "errors": ["视频：地址失效"]}
            return {"status": "done", "files": [{"kind": "video", "path": "video.mp4"}], "errors": []}
    monkeypatch.setattr(desktop.adapter, "Adapter", FakeAdapter)
    session = Session()
    command = {"action": "parse", "url": "https://example.test/a", "output": str(tmp_path)}
    report = lambda *args, **kwargs: None
    session.execute(command, report)
    result = session.execute({**command, "action": "download", "options": {"video": True, "cover": True}}, report)
    assert len(calls) == 2
    assert result["status"] == "done"
    assert [f["kind"] for f in result["files"]] == ["cover", "video"]
    assert requested[-1] == {"video": True, "cover": False}


def test_video_and_separate_audio_are_fetched_once(tmp_path, media_server, monkeypatch):
    server, _ = media_server
    adapter = Adapter(tmp_path, common=False)
    infos = adapter.parse(server + "/sample.mp4")
    infos[0].audio_download_url = server + "/audio.m4a"
    infos[0].audio_ext = "m4a"
    original, calls = adapter.fetch_media, []
    def fetch(info, target, audio_only=False):
        if audio_only:
            calls.append(info.audio_download_url)
        return original(info, target, audio_only)
    monkeypatch.setattr(adapter, "fetch_media", fetch)
    result = adapter.download(infos, {"video": True, "audio": True})
    assert result["status"] == "done", result["errors"]
    assert len(calls) == 1
    assert {f["kind"] for f in result["files"]} == {"video", "audio"}


@pytest.fixture(scope="module")
def variant_server(media_server):
    server, directory = media_server
    for name, size in (("low", "320:180"), ("high", "640:360")):
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(directory / "sample.mp4"),
            "-vf", "scale=" + size, "-r", "25", "-c:v", "mpeg2video", "-c:a", "aac", "-f", "hls", "-hls_time", "1",
            str(directory / (name + ".m3u8"))], check=True, capture_output=True)
    (directory / "master.m3u8").write_text("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\nhigh.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=320x180\nlow.m3u8\n")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(directory / "sample.mp4"),
        "-map", "0:v", "-map", "0:v", "-map", "0:a", "-s:v:0", "320x180", "-s:v:1", "640x360", "-c:v", "mpeg4",
        "-b:v:0", "300k", "-b:v:1", "800k", "-c:a", "aac", "-f", "dash", (directory / "manifest.mpd").as_posix()], check=True, capture_output=True)
    return server, directory


@pytest.mark.parametrize("path", ["master.m3u8", "manifest.mpd"])
def test_real_selected_hls_and_dash_resolution(tmp_path, variant_server, path):
    server, _ = variant_server
    adapter = Adapter(tmp_path, common=False)
    infos = adapter.parse(server + "/" + path)
    item = adapter.summary(infos)["items"][0]
    assert [f["resolution"] for f in item["formats"]] == [360, 180]
    selected = item["formats"][1]["id"]
    result = adapter.download(infos, {"video": True}, item_keys=[item["item_key"]], format_ids={item["item_key"]: selected})
    assert result["status"] == "done", result["errors"]
    output = Path(result["files"][0]["path"])
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)]))
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (320, 180)
    assert any(s["codec_type"] == "audio" for s in probe["streams"])
    assert result["files"][0]["format_id"] == selected
    with pytest.raises(DesktopError, match="画质"):
        adapter.download(infos, {"video": True}, format_ids={item["item_key"]: "expired-format"})
