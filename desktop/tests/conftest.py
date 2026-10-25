import functools
import http.server
import shutil
import subprocess
import threading

import pytest


@pytest.fixture(scope="session")
def media_server(tmp_path_factory):
    directory = tmp_path_factory.mktemp("media-server")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed for the media integration tests")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "1", "-c:v", "mpeg4", "-c:a", "aac", str(directory / "sample.mp4")], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(directory / "sample.mp4"), "-vn", "-c:a", "copy", str(directory / "audio.m4a")], check=True, capture_output=True)
    # Valid tiny PNG, generated using FFmpeg rather than a new test dependency.
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90", "-frames:v", "1", "-update", "1", str(directory / "cover.png")], check=True, capture_output=True)
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", directory
    server.shutdown()
    server.server_close()
