import json
import os
import time
from types import SimpleNamespace

import pytest

from desktop import bilibili_auth as auth
from desktop.adapter import Adapter
from desktop.session import Session


@pytest.mark.skipif(os.name != "nt", reason="Windows current-user vault")
def test_encrypted_session_roundtrip_and_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path))
    assert auth.load_cookies() == {}
    auth.save_cookies({"SESSDATA": "test-session-value", "unrelated": "ignored"})
    assert b"test-session-value" not in auth.vault_path().read_bytes()
    assert auth.load_cookies() == {"SESSDATA": "test-session-value"}
    assert auth.revision()
    auth.vault_path().write_bytes(b"corrupt")
    assert auth.load_cookies() == {}


def test_login_poll_validates_session_and_keeps_only_bili_cookie(monkeypatch):
    login = auth.QRLogin()
    login.key = "fixture-key"
    login.session.cookies.set("SESSDATA", "fixture-session", domain=".bilibili.com")
    login.session.cookies.set("irrelevant", "ignored", domain=".bilibili.com")
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/poll"):
            return {"code": 0, "url": "https://unfollowed.test/?SESSDATA=never-used"}
        return {"isLogin": True}
    monkeypatch.setattr(login, "get", get)
    assert login.poll() == (0, {"SESSDATA": "fixture-session"})
    assert [url for url, _ in calls] == ["https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                                        "https://api.bilibili.com/x/web-interface/nav"]
    monkeypatch.setattr(login, "get", lambda *args, **kwargs: {"code": 0, "isLogin": False})
    with pytest.raises(ValueError, match="登录未完成"):
        login.poll()


def test_bili_authenticated_formats_stay_private(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "load_cookies", lambda: {"SESSDATA": "fixture-session"})
    adapter = Adapter(tmp_path, common=False)
    adapter.parser.deadline = time.monotonic() + 58
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        assert url.startswith("https://api.bilibili.com/")
        assert kwargs["cookies"] == {"SESSDATA": "fixture-session"}
        assert kwargs["allow_redirects"] is False
        if url.endswith("/view"):
            data = {"bvid": "BVfixture", "title": "真实中文标题", "pages": [{"page": 1, "cid": 123}]}
        else:
            data = {"dash": {"video": [{"id": 80, "width": 1920, "height": 1080, "codecs": "avc1",
                                       "baseUrl": "https://cdn.test/video?signature=private"}],
                              "audio": [{"bandwidth": 128000, "baseUrl": "https://cdn.test/audio"}]}}
        return SimpleNamespace(json=lambda: {"code": 0, "data": data})
    monkeypatch.setattr(adapter.parser, "get", get)
    infos = adapter.parser.bilibili("https://www.bilibili.com/video/BVfixture/")
    assert len(calls) == 2
    summary = adapter.summary(infos)
    assert summary["items"][0]["formats"][0]["resolution"] == 1080
    assert infos[0]._desktop_formats[0]["has_audio"] is False
    public = json.dumps(summary)
    assert "fixture-session" not in public and "signature=private" not in public
    assert "SESSDATA" not in json.dumps(infos[0].default_download_headers)


def test_login_change_invalidates_bili_cache_only(tmp_path, monkeypatch):
    revision, calls = [0], []
    class FakeAdapter:
        def __init__(self, *args, **kwargs):
            pass
        def parse(self, url):
            calls.append(url)
            return []
        def summary(self, infos):
            return {"items": []}
    monkeypatch.setattr("desktop.adapter.Adapter", FakeAdapter)
    monkeypatch.setattr(auth, "revision", lambda: revision[0])
    session = Session()
    command = {"action": "parse", "url": "https://www.bilibili.com/video/BVfixture/", "output": str(tmp_path)}
    other = {**command, "url": "https://other.test/video"}
    report = lambda *args, **kwargs: None
    assert not session.execute(command, report)["cache_hit"]
    session.execute(other, report)
    assert session.execute(command, report)["cache_hit"]
    revision[0] = 1
    assert not session.execute(command, report)["cache_hit"]
    assert session.execute(other, report)["cache_hit"]
    revision[0] = 0
    # A logout must not revive pre-login signed URLs.
    assert not session.execute(command, report)["cache_hit"]


def test_muxed_selection_does_not_fetch_redundant_audio(tmp_path, monkeypatch, media_server):
    server, _ = media_server
    adapter = Adapter(tmp_path, common=False)
    infos = adapter.parse(server + "/sample.mp4")
    infos[0].audio_download_url = server + "/unused-audio.m4a"
    selected = adapter.select_format(infos[0])
    assert selected.audio_download_url == ""
    result = adapter.download(infos, {"video": True, "audio": True})
    assert result["status"] == "done", result["errors"]
    assert {f["kind"] for f in result["files"]} == {"video", "audio"}


def test_bili_h5_dimensions_are_probed_not_guessed(tmp_path, monkeypatch, media_server):
    server, _ = media_server
    monkeypatch.setattr(auth, "load_cookies", lambda: {})
    adapter = Adapter(tmp_path, common=False)
    adapter.parser.deadline = time.monotonic() + 58
    def get(url, **kwargs):
        if url.endswith("/view"):
            data = {"bvid": "BVfixture", "title": "匿名资源", "pages": [{"page": 1, "cid": 123}]}
        elif kwargs["params"]["fnval"]:
            data = {"dash": {"video": [{"id": 32, "width": 852, "height": 480,
                                       "baseUrl": "https://cdn.test/video"}]}}
        else:
            # Advertised qn 80 must not become a fabricated 1080p label.
            data = {"quality": 80, "durl": [{"url": server + "/sample.mp4"}]}
        return SimpleNamespace(json=lambda: {"code": 0, "data": data})
    monkeypatch.setattr(adapter.parser, "get", get)
    infos = adapter.parser.bilibili("https://www.bilibili.com/video/BVfixture/")
    formats = infos[0]._desktop_formats
    assert sorted(f["resolution"] for f in formats) == [90, 480]
    assert next(f for f in formats if f["resolution"] == 90)["has_audio"] is True
