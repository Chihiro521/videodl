import ast
import hashlib
import io
import json
import zipfile

import pytest
import requests

from desktop.build import PublicDefaults
from desktop import build
import os


def test_public_build_removes_defaults_without_changing_api_structure():
    original = '''
API_TOKEN = "example-private-service-token"
headers = {"Cookie": "account=example-value", "User-Agent": "Example public user agent"}
def f(url, cookies=None):
    return url, cookies
'''
    transform = PublicDefaults()
    tree = transform.visit(ast.parse(original))
    result = ast.unparse(ast.fix_missing_locations(tree))
    assert "example-private-service-token" not in result
    assert "account=example-value" not in result
    assert "Example public user agent" in result
    assert "def f(url, cookies=None)" in result
    assert len(transform.removed) == 2


def test_staged_sources_clear_reused_values_and_preserve_originals(tmp_path, monkeypatch):
    upstream = tmp_path / "videodl"
    upstream.mkdir()
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    original = 'API_TOKEN = "example-service-default"\nreused = ["example-service-default"]\n'
    (upstream / "example.py").write_text(original, encoding="utf-8")
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "WORK", tmp_path / "work")
    stage = build.stage_sources()
    assert "example-service-default" not in (stage / "videodl/example.py").read_text(encoding="utf-8")
    assert (upstream / "example.py").read_text(encoding="utf-8") == original


def test_build_dll_search_does_not_inherit_other_apps(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "C:/other-application/poppler/bin")
    monkeypatch.setenv("QT_PLUGIN_PATH", "C:/other-application/qt/plugins")
    environment = build.isolated_environment(tmp_path / "stage", tmp_path / "tools")
    assert "other-application" not in environment["PATH"]
    assert "QT_PLUGIN_PATH" not in environment
    assert environment["PYTHONPATH"] == str(tmp_path / "stage")


@pytest.mark.parametrize("bad_asset", [None, "ffmpeg", "yt-dlp"])
def test_media_tools_verifies_and_stages_both_binaries(tmp_path, monkeypatch, bad_asset):
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("ffmpeg-test/bin/ffmpeg.exe", b"test-ffmpeg")
    archive_bytes = archive_buffer.getvalue()
    downloader_bytes = b"test-downloader"
    ffmpeg_url = "https://tools.test/ffmpeg.zip"
    downloader_url = "https://tools.test/yt-dlp.exe"
    config = {
        "url": ffmpeg_url, "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "yt_dlp": {"version": "test", "url": downloader_url, "sha256": hashlib.sha256(downloader_bytes).hexdigest()},
    }
    if bad_asset == "ffmpeg":
        config["sha256"] = "0" * 64
    elif bad_asset == "yt-dlp":
        config["yt_dlp"]["sha256"] = "0" * 64
    (tmp_path / "desktop").mkdir()
    (tmp_path / "desktop/media-tools.json").write_text(json.dumps(config), encoding="utf-8")
    downloaded = []

    def get(url, **kwargs):
        downloaded.append(url)
        assert kwargs == {"stream": True, "timeout": (30, 120)}
        response = requests.Response()
        response.status_code = 200
        response._content = {ffmpeg_url: archive_bytes, downloader_url: downloader_bytes}[url]
        response._content_consumed = True
        return response

    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "WORK", tmp_path / "build/desktop-package")
    monkeypatch.setattr(build.requests, "get", get)
    if bad_asset:
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            build.media_tools()
        failed_cache_name = "ffmpeg.zip" if bad_asset == "ffmpeg" else "yt-dlp-test.exe"
        assert not (tmp_path / "build/media-cache" / failed_cache_name).exists()
        return

    tools, actual_config = build.media_tools()
    assert actual_config == config
    assert (tools / "ffmpeg.exe").read_bytes() == b"test-ffmpeg"
    assert (tools / "yt-dlp.exe").read_bytes() == downloader_bytes
    assert downloaded == [ffmpeg_url, downloader_url]
    build.media_tools()
    assert downloaded == [ffmpeg_url, downloader_url]
