"""Platform-neutral media identities and public format descriptors.

Resource URLs and opaque upstream objects stay in the worker. Only descriptors
returned by public_formats may enter the GUI's persistent stores.
"""

import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


def canonical_url(url):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    query = parse_qs(parts.query)
    if host in ("douyin.com", "iesdouyin.com") or host.endswith(".douyin.com") or host.endswith(".iesdouyin.com"):
        video_id = next((v for v in query.get("modal_id", []) if v.isdigit()), "")
        match = re.search(r"/(?:share/)?video/(\d+)", parts.path)
        if video_id or match:
            return "https://www.douyin.com/video/" + (video_id or match[1])
    if host in ("youtu.be", "www.youtu.be"):
        return "https://www.youtube.com/watch?" + urlencode({"v": parts.path.strip("/")})
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        match = re.search(r"/(?:shorts|embed|live)/([^/]+)", parts.path)
        video_id = query.get("v", [""])[0] or (match[1] if match else "")
        if video_id:
            return "https://www.youtube.com/watch?" + urlencode({"v": video_id})
    # Keep unknown query strings: they can identify a resource or sign a URL.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def fallback_title(value):
    return not value or bool(re.search(r"unknow(?:n)?title|未命名|^\d{4}-\d\d-\d\d.*VideoClient", str(value), re.I))


def media_key(info, index=0):
    origin = getattr(info, "_desktop_url", "")
    identifier = str(info.identifier or "")
    if fallback_title(identifier) or identifier == str(info.title):
        identifier = ""
    if origin and "/www.douyin.com/video/" in origin:
        identifier = ""  # The canonical video number survives parser switches.
    identity = origin or str(info.source)
    identity += "\0" + (identifier or ("single" if getattr(info, "_desktop_single", False) else str(index)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def legacy_media_key(info, index=0):
    identity = str(info.identifier) if info.identifier else f"{index}:{info.title}"
    return hashlib.sha256(f"{info.source}\0{identity}".encode("utf-8")).hexdigest()


def number(value):
    try:
        parts = str(value).split("/")
        return float(parts[0]) / (float(parts[1]) if len(parts) > 1 else 1)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


def format_descriptor(resource, index=0, default_ext="mp4"):
    """Normalize an actual format, retaining its resource only inside the worker."""
    if not isinstance(resource, dict):
        return None
    address = resource.get("play_addr") or {}
    urls = address.get("url_list") or resource.get("url_list") or []
    url = resource.get("url") or resource.get("baseUrl") or resource.get("base_url") or resource.get("mediaUrl") or resource.get("vid_url") or (urls[0] if urls else None)
    if not url or (isinstance(url, str) and not url.startswith(("http://", "https://"))):
        return None
    label = str(resource.get("format_note") or resource.get("format") or resource.get("quality") or resource.get("qualityLabel") or resource.get("definition") or resource.get("mediaQuality") or "")
    if resource.get("vcodec") == "none" or str(resource.get("type", "")).lower() == "audio":
        return None
    width = int(number(resource.get("width") or address.get("width")))
    height = int(number(resource.get("height") or address.get("height")))
    match = re.search(r"(\d{3,4})[pP]", label)
    resolution = min(width, height) if width and height else (int(match[1]) if match else height)
    ext = str(resource.get("ext") or resource.get("mediaExtension") or default_ext).lower().lstrip(".")
    if ext in ("m4s", "m3u8", "m3u", "mpd"):
        ext = "mp4"
    if not re.fullmatch(r"[a-z0-9]{1,8}", ext):
        ext = "mp4"
    codec = str(resource.get("vcodec") or resource.get("codecs") or resource.get("codecid") or resource.get("codec_type") or "")
    fps = number(resource.get("fps") or resource.get("frameRate"))
    bitrate = number(resource.get("tbr") or resource.get("bandwidth") or resource.get("bit_rate") or resource.get("bitrate"))
    native_id = str(resource.get("format_id") or resource.get("itag") or resource.get("id") or resource.get("gear_name") or "")
    identity = [native_id, resolution, width, height, fps, codec, ext, str(resource.get("_map", ""))]
    # Unknown single resources must survive changing signed URLs and providers.
    if not any((native_id, resolution, codec, width, height)):
        identity = ["source", ext, index]
    key = hashlib.sha256(repr(identity).encode()).hexdigest()[:24]
    return {"id": key, "label": f"{str(resolution) + 'p' if resolution else '来源画质'}-{ext.upper()}",
            "width": width, "height": height, "resolution": resolution, "fps": fps,
            "codec": codec, "ext": ext, "bitrate": bitrate, "url": url,
            "audio_url": resource.get("audio_url", ""), "map": resource.get("_map"),
            "headers": resource.get("http_headers") or {}, "native_id": native_id}


def normalize_formats(resources, default_ext="mp4"):
    normalized = {}
    for index, resource in enumerate(resources):
        item = format_descriptor(resource, index, default_ext)
        if item:
            previous = normalized.get(item["id"])
            if not previous or item["bitrate"] > previous["bitrate"]:
                normalized[item["id"]] = item
    result = sorted(normalized.values(), key=lambda f: (f["resolution"], f["width"] * f["height"], f["fps"], f["bitrate"]), reverse=True)
    labels = [f["label"] for f in result]
    for item in result:
        if labels.count(item["label"]) > 1:
            extra = item["codec"] or item["native_id"] or str(round(item["bitrate"]))
            extra = next((name for prefix, name in (("avc", "H.264"), ("hvc", "H.265"), ("hev", "H.265"),
                ("av01", "AV1"), ("vp09", "VP9")) if extra.lower().startswith(prefix)), extra)
            item["label"] += f" · {extra}"
    return result


def public_formats(formats):
    return [{key: item[key] for key in ("id", "label", "width", "height", "resolution", "fps", "codec", "ext")} for item in formats]


def raw_formats(raw):
    """Known format containers shared by upstream's platform/common parsers."""
    paths = (("formats",), ("medias",), ("video",), ("api", "mediaItems"), ("streamingData", "formats"),
             ("streamingData", "adaptiveFormats"), ("data", "dash", "video"),
             ("result", "video_info", "dash", "video"), ("video", "bit_rate"), ("bit_rate",))
    result = []
    for path in paths:
        value = raw
        for key in path:
            value = value.get(key, {}) if isinstance(value, dict) else {}
        if isinstance(value, list):
            if path == ("video",) and len(value) != 1:
                continue  # An unlabeled list may describe separate posts.
            result.extend(item for item in value if isinstance(item, dict))
    return result
