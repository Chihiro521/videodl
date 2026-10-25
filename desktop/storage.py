"""Small, atomic local stores. Download URLs returned by parsers are never persisted."""

import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def data_dir() -> Path:
    override = os.environ.get("VIDEODL_DESKTOP_DATA")
    base = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "VideoDL Desktop"
    base.mkdir(parents=True, exist_ok=True)
    return base


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def parse_links(text: str) -> list[str]:
    """Accept multi-line links and the surrounding text of share messages."""
    links = []
    for candidate in re.findall(r"https?://[^\s<>\"“”]+", text):
        url = candidate.rstrip("。；，、！）)]}.,;!'")
        try:
            parts = urlsplit(url)
            _ = parts.port
            if parts.hostname and not parts.username and not parts.password and url not in links:
                links.append(url)
        except ValueError:
            continue
    return links


def public_host(url: str) -> str:
    return urlsplit(url).hostname or "未知来源"
