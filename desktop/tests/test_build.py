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


@pytest.mark.parametrize("bad_asset", [None, "ffmpeg", "yt-dlp", "node"])
def test_media_tools_verifies_and_stages_all_binaries(tmp_path, monkeypatch, bad_asset):
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("ffmpeg-test/bin/ffmpeg.exe", b"test-ffmpeg")
    archive_bytes = archive_buffer.getvalue()
    downloader_bytes = b"test-downloader"
    node_bytes = b"test-node"
    ffmpeg_url = "https://tools.test/ffmpeg.zip"
    downloader_url = "https://tools.test/yt-dlp.exe"
    node_url = "https://tools.test/node.exe"
    config = {
        "url": ffmpeg_url, "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "yt_dlp": {"version": "test", "url": downloader_url, "sha256": hashlib.sha256(downloader_bytes).hexdigest()},
        "nodejs": {"version": "test", "url": node_url, "sha256": hashlib.sha256(node_bytes).hexdigest()},
    }
    if bad_asset == "ffmpeg":
        config["sha256"] = "0" * 64
    elif bad_asset == "yt-dlp":
        config["yt_dlp"]["sha256"] = "0" * 64
    elif bad_asset == "node":
        config["nodejs"]["sha256"] = "0" * 64
    (tmp_path / "desktop").mkdir()
    (tmp_path / "desktop/media-tools.json").write_text(json.dumps(config), encoding="utf-8")
    downloaded = []

    def get(url, **kwargs):
        downloaded.append(url)
        assert kwargs == {"stream": True, "timeout": (30, 120)}
        response = requests.Response()
        response.status_code = 200
        response._content = {ffmpeg_url: archive_bytes, downloader_url: downloader_bytes, node_url: node_bytes}[url]
        response._content_consumed = True
        return response

    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "WORK", tmp_path / "build/desktop-package")
    monkeypatch.setattr(build.requests, "get", get)
    if bad_asset:
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            build.media_tools()
        failed_cache_name = {"ffmpeg": "ffmpeg.zip", "yt-dlp": "yt-dlp-test.exe", "node": "node-test/node.exe"}[bad_asset]
        assert not (tmp_path / "build/media-cache" / failed_cache_name).exists()
        return

    tools, actual_config = build.media_tools()
    assert actual_config == config
    assert (tools / "ffmpeg.exe").read_bytes() == b"test-ffmpeg"
    assert (tools / "yt-dlp.exe").read_bytes() == downloader_bytes
    assert (tools / "node.exe").read_bytes() == node_bytes
    assert downloaded == [ffmpeg_url, downloader_url, node_url]
    stale = tmp_path / "build/desktop-package/media-tools/ffmpeg-old/bin"
    stale.mkdir(parents=True)
    (stale / "ffmpeg.exe").write_bytes(b"old-ffmpeg")
    build.media_tools()
    assert downloaded == [ffmpeg_url, downloader_url, node_url]
    assert tools.name == "bin" and tools.parent.name == "ffmpeg-test"


def test_youtube_node_helpers_use_the_desktop_runtime(monkeypatch, tmp_path):
    from videodl.modules.utils import youtubeutils

    node = tmp_path / "node.exe"
    calls = []
    monkeypatch.setenv("VIDEODL_NODE_EXECUTABLE", str(node))

    def check_output(command, **kwargs):
        calls.append(command)
        return b"public-test-result\n"

    monkeypatch.setattr(youtubeutils.subprocess, "check_output", check_output)
    assert youtubeutils.NodeRunner._nodepath() == str(node)
    assert youtubeutils.generatepotoken("public-test-video") == "public-test-result"
    assert calls[0][0] == str(node)


def test_youtube_node_path_preserves_the_sdk_default(monkeypatch):
    from pathlib import Path
    import nodejs_wheel.executable
    from videodl.modules.utils.youtubeutils import NodeRunner

    monkeypatch.delenv("VIDEODL_NODE_EXECUTABLE", raising=False)
    root = Path(nodejs_wheel.executable.ROOT_DIR)
    expected = root / "node.exe" if os.name == "nt" else root / "bin/node"
    assert Path(NodeRunner._nodepath()) == expected


def test_native_http_transport_contains_fixed_libraries():
    import re
    from curl_cffi import Curl

    curl = Curl()
    try:
        version = curl.version().decode("ascii")
    finally:
        curl.close()
    curl_version = re.search(r"libcurl/(\d+)\.(\d+)\.(\d+)", version)
    brotli_version = re.search(r"brotli/(\d+)\.(\d+)\.(\d+)", version)
    assert curl_version and tuple(map(int, curl_version.groups())) >= (8, 23, 0)
    assert brotli_version and tuple(map(int, brotli_version.groups())) >= (1, 2, 1)
