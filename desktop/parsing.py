"""Automatic platform adaptations over the untouched upstream SDK."""

import html
import json
import re
import time
from urllib.parse import urlsplit, urljoin
from xml.etree import ElementTree as ET

import requests

from .media import canonical_url, fallback_title, normalize_formats, raw_formats


class Parsing:
    def __init__(self, adapter):
        self.adapter = adapter
        self.preferred = {}
        self.deadline = 0
        self.session = requests.Session()

    def get(self, url, **kwargs):
        remaining = max(0.1, self.deadline - time.monotonic())
        kwargs.setdefault("timeout", (min(5, remaining), min(8, remaining)))
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response

    def parse(self, url):
        self.deadline = time.monotonic() + 58
        adapter = self.adapter
        url = canonical_url(url)
        host = urlsplit(url).hostname or ""
        if host in ("v.douyin.com", "b23.tv"):
            url = canonical_url(self.get(url).url)
            host = urlsplit(url).hostname or ""
        infos, errors = [], []
        self.page_html = ""
        # Explicit media resources bypass domain routing and page probing.
        media_suffixes = (".mp4", ".webm", ".mkv", ".mov", ".m4a", ".mp3", ".aac", ".flac", ".ogg", ".opus", ".wav", ".m3u8", ".mpd")
        if urlsplit(url).path.lower().endswith(media_suffixes):
            from urllib.parse import unquote
            ext = urlsplit(url).path.rsplit(".", 1)[-1].lower()
            infos = [adapter.new_info(source="WebMediaGrabber", download_url=url,
                title=unquote(urlsplit(url).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]), ext="mp4" if ext in ("m3u8", "mpd") else ext)]
        if not infos and host == "www.douyin.com":
            try:
                infos = self.douyin(url)
            except Exception as exc:
                errors.append(adapter.error_text(exc))
        if not infos and host in ("www.bilibili.com", "bilibili.com", "m.bilibili.com") and "/video/" in url:
            try:
                infos = self.bilibili(url)
            except Exception as exc:
                errors.append(adapter.error_text(exc))
        if not infos:
            for name, entry in adapter.client.video_clients.items():
                cls = entry["cls"] if isinstance(entry, dict) else entry
                if not cls.belongto(url):
                    continue
                # Douyin's old share-page parser uses the same missing SSR field.
                if name == "DouyinVideoClient":
                    continue
                infos = self.attempt(name, url, errors)
                if infos:
                    break
        if not infos:
            names = sorted(adapter.client.common_video_clients)
            preferred = self.preferred.get(host)
            metadata_source = "WzjunVideoClient" if host == "www.douyin.com" else "PVVideoClient"
            names = sorted(names, key=lambda n: (n != preferred, n != metadata_source, n != "PVVideoClient", n))
            for name in names:
                if time.monotonic() >= self.deadline:
                    break
                infos = self.attempt(name, url, errors)
                if infos:
                    self.preferred[host] = name
                    break
        if not infos and time.monotonic() < self.deadline:
            # Existing headless automatic grabber; no interactive browser path.
            infos = self.attempt("WebMediaGrabber", url, errors)
        if not infos:
            reason = errors[-1] if errors else "来源未返回可用媒体。"
            raise adapter.failure("没有解析到可下载内容：" + reason)
        self.enrich(infos, url)
        return infos

    def attempt(self, name, url, errors):
        adapter = self.adapter
        adapter.report("progress", percent=-1, detail=f"正在提取 · {name.removesuffix('VideoClient')}")
        try:
            client = adapter.source_client(adapter.new_info(source=name))
            remaining = max(0.1, self.deadline - time.monotonic())
            infos = client.parsefromurl(url, request_overrides={"timeout": (min(5, remaining), min(10, remaining))})
            valid = [info for info in infos or [] if info.with_valid_download_url]
            if valid:
                return valid
            errors.append("来源未返回可用媒体。")
        except Exception as exc:
            errors.append(adapter.error_text(exc))
        return []

    def douyin(self, url):
        adapter = self.adapter
        video_id = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
        if not video_id.isdigit():
            return []
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        response = self.get("https://www.iesdouyin.com/share/video/" + video_id, headers={"User-Agent": ua})
        self.page_html = response.text
        match = re.search(r"window\._ROUTER_DATA\s*=\s*(.*?)</script>", response.text, re.S)
        detail = {}
        if match:
            import json_repair
            data = json_repair.loads(match[1].strip().rstrip(";"))
            res = data.get("loaderData", {}).get("video_(id)/page", {}).get("videoInfoRes", {})
            items = res.get("item_list") or []
            detail = items[0] if items else {}
        if not detail:
            try:
                detail = self.get("https://www.douyin.com/aweme/v1/web/aweme/detail/", params={"aweme_id": video_id},
                    headers={"User-Agent": ua, "Referer": "https://www.douyin.com/"}).json().get("aweme_detail", {})
            except (requests.RequestException, ValueError):
                pass
        if not detail:
            return []
        video = detail.get("video") or {}
        resources = video.get("bit_rate") or []
        address = video.get("play_addr") or {}
        if address.get("url_list"):
            resources = [*resources, {"play_addr": address, "width": video.get("width"), "height": video.get("height")}]
        formats = normalize_formats(resources)
        if not formats:
            return []
        info = adapter.new_info(source="DouyinVideoClient", identifier=video_id, title=detail.get("desc", ""),
            raw_data=detail, download_url=formats[0]["url"], cover_url=(video.get("origin_cover") or video.get("cover") or {}).get("url_list", []),
            default_download_headers={"User-Agent": ua, "Referer": "https://www.douyin.com/"})
        info._desktop_formats = formats
        return [info]

    def bilibili(self, url):
        from urllib.parse import parse_qs
        match = re.search(r"/video/(BV[a-zA-Z0-9]+|av\d+)", url, re.I)
        if not match:
            return []
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
        identifier = match[1]
        query = {"bvid": identifier} if identifier.lower().startswith("bv") else {"aid": identifier[2:]}
        payload = self.get("https://api.bilibili.com/x/web-interface/view", params=query, headers=headers).json()
        data = payload.get("data") or {}
        if payload.get("code") != 0 or not data:
            return []
        page_number = parse_qs(urlsplit(url).query).get("p", [None])[0]
        infos = []
        for page in data.get("pages", []):
            if page_number and str(page.get("page")) != page_number:
                continue
            payload = self.get("https://api.bilibili.com/x/player/playurl", params={"bvid": data["bvid"], "cid": page["cid"],
                "fnval": 4048, "fnver": 0, "fourk": 1, "qn": 127}, headers=headers).json()
            play = payload.get("data") or {}
            dash = play.get("dash") or {}
            resources = dash.get("video") or []
            audio = sorted(dash.get("audio") or [], key=lambda a: a.get("bandwidth", 0), reverse=True)
            audio_url = (audio[0].get("baseUrl") or audio[0].get("base_url")) if audio else ""
            resources = [{**resource, "audio_url": audio_url} for resource in resources]
            formats = normalize_formats(resources)
            if not formats:
                urls = play.get("durl") or []
                if len(urls) == 1:
                    formats = normalize_formats([{"url": urls[0].get("url")}])
            if not formats:
                continue
            title = data.get("title", "")
            if len(data.get("pages", [])) > 1:
                title += f" - P{page.get('page', len(infos)+1)} {page.get('part', '')}"
            info = self.adapter.new_info(source="BilibiliVideoClient", identifier=f"{data['bvid']}-{page['cid']}", title=title,
                raw_data={"data": play, "x/web-interface/view": {"data": data}}, download_url=formats[0]["url"],
                audio_download_url=audio_url, audio_ext="m4a", cover_url=page.get("first_frame") or data.get("pic", ""),
                default_download_headers=headers, default_audio_download_headers=headers)
            info._desktop_formats = formats
            infos.append(info)
        return infos

    def enrich(self, infos, url):
        for index, info in enumerate(infos):
            info._desktop_url = url
            info._desktop_single = len(infos) == 1
            if not getattr(info, "_desktop_formats", None):
                resources = raw_formats(info.raw_data if isinstance(info.raw_data, dict) else {})
                if info.source == "YouTubeVideoClient" and isinstance(info.raw_data, dict) and info.raw_data.get("api"):
                    # mediaItems from this provider are generation jobs. Expose
                    # the SDK's already resolved resource, never a job address.
                    resources = []
                # Existing selected streams are usable even when no variants exist.
                if not resources:
                    stream = info.download_url
                    resources = [{"url": stream, "ext": info.ext, "height": getattr(stream, "height", 0),
                        "quality": getattr(stream, "resolution", ""), "itag": getattr(stream, "itag", "")}]
                info._desktop_formats = normalize_formats(resources, info.ext)
            stream = info.download_url
            youtube = getattr(getattr(stream, "_monostate", None), "youtube", None)
            if youtube:
                streams = list(youtube.streams)
                audio = sorted((s for s in streams if s.type == "audio"), key=lambda s: s.bitrate or 0, reverse=True)
                resources = [{"url": s, "itag": s.itag, "quality": s.resolution, "ext": s.subtype,
                    "fps": getattr(s, "fps", 0), "vcodec": s.video_codec, "bitrate": s.bitrate,
                    "audio_url": audio[0] if audio and not s.audio_codec else ""} for s in streams if s.type == "video"]
                info._desktop_formats = normalize_formats(resources, info.ext)
            if isinstance(info.download_url, str):
                suffix = urlsplit(info.download_url).path.lower()
                try:
                    if suffix.endswith(".m3u8"):
                        self.hls(info)
                    elif suffix.endswith(".mpd"):
                        self.dash(info)
                except (requests.RequestException, ValueError, ET.ParseError):
                    pass
            if len(info._desktop_formats) == 1 and not info._desktop_formats[0]["resolution"] and str(info.ext).lower() not in ("mp3", "m4a", "aac", "wav", "flac", "opus", "ogg"):
                self.probe_format(info)
            if fallback_title(info.title):
                title = self.raw_title(info.raw_data)
                if not title and time.monotonic() < self.deadline - 2:
                    try:
                        title = self.html_title(getattr(self, "page_html", "") if "douyin.com" in url else self.get(url).text)
                    except requests.RequestException:
                        pass
                info.title = title or f"{urlsplit(url).hostname or '视频'}_{urlsplit(url).path.rstrip('/').rsplit('/',1)[-1] or index + 1}"
            # An identifier synthesized from a changing title is never an asset ID.
            if fallback_title(info.identifier) or info.identifier == info.title:
                info.identifier = ""
            if not info.cover_url and isinstance(info.raw_data, dict):
                info.cover_url = info.raw_data.get("thumbnail") or info.raw_data.get("cover") or ""

    def probe_format(self, info):
        """Read stream headers only when a source has no resolution metadata."""
        import subprocess
        from .adapter import find_tool
        probe = find_tool("ffprobe")
        if not probe or not isinstance(info.download_url, str) or time.monotonic() >= self.deadline - 6:
            return
        try:
            headers = info.default_download_headers or getattr(self.adapter.source_client(info), "default_download_headers", {}) or {}
            args = [probe, "-v", "error", "-rw_timeout", "4000000", "-analyzeduration", "0", "-probesize", "65536"]
            if headers:
                args += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in headers.items())]
            args += ["-select_streams", "v:0", "-show_entries", "stream=width,height,codec_name,r_frame_rate", "-of", "json", info.download_url]
            response = subprocess.run(args, capture_output=True, timeout=6)
            stream = json.loads(response.stdout).get("streams", [])[0]
            if stream.get("width") and stream.get("height"):
                resource = {"url": info.download_url, "width": stream["width"], "height": stream["height"],
                    "vcodec": stream.get("codec_name", ""), "fps": stream.get("r_frame_rate"), "ext": info.ext}
                info._desktop_formats = normalize_formats([resource], info.ext)
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            pass

    @staticmethod
    def raw_title(raw):
        if not isinstance(raw, dict):
            return ""
        for path in (("title",), ("desc",), ("api", "title"), ("videoDetails", "title"), ("x/web-interface/view", "data", "title")):
            value = raw
            for key in path:
                value = value.get(key) if isinstance(value, dict) else None
            if isinstance(value, str) and not fallback_title(value):
                return value.strip()
        return ""

    @staticmethod
    def html_title(text):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "html.parser")
        for selector in ('meta[property="og:title"]', 'meta[name="twitter:title"]'):
            item = soup.select_one(selector)
            if item and item.get("content"):
                return html.unescape(item["content"]).strip()
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
                for item in data if isinstance(data, list) else [data]:
                    if isinstance(item, dict) and item.get("@type") in ("VideoObject", "AudioObject"):
                        return item.get("name", "")
            except ValueError:
                pass
        return ""

    def hls(self, info):
        import m3u8
        response = self.get(info.download_url, headers=info.default_download_headers or {})
        master = m3u8.loads(response.text, uri=response.url)
        if not master.is_variant:
            return
        resources = []
        for playlist in master.playlists:
            stream = playlist.stream_info
            width, height = stream.resolution or (0, 0)
            audio = next((m.absolute_uri for m in master.media if m.type == "AUDIO" and m.group_id == stream.audio and m.uri), "")
            resources.append({"url": playlist.absolute_uri, "width": width, "height": height,
                "bandwidth": stream.bandwidth, "fps": stream.frame_rate, "codecs": stream.codecs, "audio_url": audio})
        info._desktop_formats = normalize_formats(resources)

    def dash(self, info):
        response = self.get(info.download_url, headers=info.default_download_headers or {})
        root = ET.fromstring(response.content)
        resources, video_index = [], 0
        for adaptation in root.findall(".//{*}AdaptationSet"):
            for representation in adaptation.findall("{*}Representation"):
                mime = representation.get("mimeType") or adaptation.get("mimeType", "")
                if not mime.startswith("video") and adaptation.get("contentType") != "video":
                    continue
                resources.append({"url": response.url, "id": representation.get("id"),
                    "width": representation.get("width") or adaptation.get("width"),
                    "height": representation.get("height") or adaptation.get("height"),
                    "bandwidth": representation.get("bandwidth"), "codecs": representation.get("codecs"),
                    "frameRate": representation.get("frameRate") or adaptation.get("frameRate"), "_map": f"0:v:{video_index}"})
                video_index += 1
        if resources:
            info._desktop_formats = normalize_formats(resources)
