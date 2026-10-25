"""Release discovery; the desktop never modifies its running source tree."""

import json
import re
from xml.etree import ElementTree
from pathlib import Path

import requests

from . import REPOSITORY, UPSTREAM, __version__


def build_info():
    path = Path(__file__).with_name("build-info.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return json.loads(Path(__file__).with_name("upstream.json").read_text(encoding="utf-8"))


def check_updates():
    session = requests.Session()
    session.headers["User-Agent"] = f"VideoDL-Desktop/{__version__}"
    try:
        response = session.get(f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=50", timeout=15)
        response.raise_for_status()
        releases = [r for r in response.json() if re.fullmatch(r"desktop-v\d+\.\d+\.\d+", r.get("tag_name", "")) and not r.get("draft") and not r.get("prerelease")]
    except (requests.RequestException, ValueError):
        # Public Atom feeds also work when GitHub's anonymous API limit is used.
        response = session.get(f"https://github.com/{REPOSITORY}/releases.atom", timeout=15)
        response.raise_for_status()
        feed = ElementTree.fromstring(response.content)
        releases = []
        for link in feed.findall(".//{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}link"):
            url = link.get("href", "")
            if match := re.search(r"/releases/tag/(desktop-v\d+\.\d+\.\d+)$", url):
                releases.append({"tag_name": match[1], "html_url": url})
    def version(tag):
        return tuple(int(s) for s in tag.removeprefix("desktop-v").split(".") if s.isdigit())
    latest = max(releases, key=lambda r: version(r["tag_name"]), default=None)
    result = {"current": __version__, "latest": latest["tag_name"] if latest else "暂无桌面发行版",
              "available": bool(latest and version(latest["tag_name"]) > version(__version__)),
              "release_url": latest["html_url"] if latest else f"https://github.com/{REPOSITORY}/releases",
              "build": build_info()}
    try:
        upstream = session.get(f"https://api.github.com/repos/{UPSTREAM}/commits/master", timeout=20)
        upstream.raise_for_status()
        result["upstream_revision"] = upstream.json()["sha"]
    except (requests.RequestException, ValueError, KeyError):
        try:
            feed = session.get(f"https://github.com/{UPSTREAM}/commits/master.atom", timeout=15)
            feed.raise_for_status()
            first_id = ElementTree.fromstring(feed.content).findtext("{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}id", "")
            result["upstream_revision"] = first_id.rsplit("/", 1)[-1] or "未获取到"
        except (requests.RequestException, ValueError, ElementTree.ParseError):
            result["upstream_revision"] = "未获取到"
    return result
