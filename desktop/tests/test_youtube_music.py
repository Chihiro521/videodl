import pytest
from types import SimpleNamespace

from desktop.adapter import Adapter
from desktop.media import canonical_url
from desktop.parsing import Parsing
from desktop.youtube_music import YouTubeMusicAdapter


def test_youtube_music_track_normalization_and_playlist_rejection():
    source = "https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=PLdemo"
    assert YouTubeMusicAdapter.is_url(source)
    assert YouTubeMusicAdapter.track_id(source) == "dQw4w9WgXcQ"
    assert YouTubeMusicAdapter.normalize(source) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert canonical_url(source) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    # Playlist-only pages have no track id and are rejected by the parser.
    assert YouTubeMusicAdapter.normalize("https://music.youtube.com/playlist?list=PLdemo") == ""


def test_youtube_music_result_is_audio_first(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    adapter = Adapter(tmp_path, common=False)
    info = adapter.new_info(source="YouTubeVideoClient", title="歌曲", ext="mp4",
        download_url="https://cdn.test/video", audio_download_url="https://cdn.test/audio", audio_ext="m4a")
    YouTubeMusicAdapter.mark_track(info)
    summary = adapter.summary([info])
    assert summary["items"][0]["media_kind"] == "audio"
    assert summary["items"][0]["audio_ext"] == "m4a"
    adapter.close()


def test_youtube_music_preserves_opus_audio_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEODL_DESKTOP_DATA", str(tmp_path / "appdata"))
    adapter = Adapter(tmp_path / "output", common=False)
    audio = SimpleNamespace(subtype="webm", mime_type="audio/webm")
    info = adapter.new_info(source="YouTubeVideoClient", title="歌曲", ext="mp4",
        download_url="https://cdn.test/video")
    info._desktop_formats = [{"id": "music", "url": "https://cdn.test/video", "ext": "mp4",
        "resolution": 1080, "has_audio": False, "audio_url": audio}]
    selected = adapter.select_format(info, "music")
    assert selected.audio_ext == "webm"
    adapter.close()


def test_parser_routes_music_track_to_upstream_youtube_client(monkeypatch):
    class Client:
        video_clients = {"YouTubeVideoClient": SimpleNamespace(belongto=lambda url: True)}
        common_video_clients = {}

    class FakeAdapter:
        failure = ValueError
        client = Client()

        @staticmethod
        def report(*args, **kwargs):
            pass

        @staticmethod
        def error_text(exc):
            return str(exc)

    parser = Parsing(FakeAdapter())
    seen = []
    info = SimpleNamespace()
    monkeypatch.setattr(parser, "attempt", lambda name, url, errors: (seen.append((name, url)) or [info]))
    monkeypatch.setattr(parser, "enrich", lambda infos, url: None)
    result = parser.parse("https://music.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result == [info]
    assert seen == [("YouTubeVideoClient", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")]
    assert info._desktop_music and info._desktop_single
