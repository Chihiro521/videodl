"""Compact quality choices; original formats remain available in the menu."""

import re

from .media import number


def resolution(item):
    value = int(number(item.get("resolution")))
    width, height = int(number(item.get("width"))), int(number(item.get("height")))
    if not value and width and height:
        value = min(width, height)
    if not value:
        match = re.search(r"(\d{3,4})p", item.get("label", ""), re.I)
        value = int(match[1]) if match else 0
    return value


def codec_name(item):
    codec = str(item.get("codec") or "").lower()
    for prefixes, name in ((("avc", "h264", "h.264", "7"), "H.264"),
        (("hev", "hvc", "hevc", "h265", "h.265", "12"), "H.265"),
        (("vp09", "vp9"), "VP9"), (("av01", "av1", "13"), "AV1")):
        if any(codec.startswith(prefix) for prefix in prefixes):
            return name
    return "来源编码" if not codec else codec


def transport_name(item):
    protocol = str(item.get("protocol") or "").lower()
    if "m3u8" in protocol or protocol == "hls":
        return "HLS 分片"
    if "dash" in protocol:
        return "DASH 分流"
    if protocol in ("http", "https") or "http-" in item.get("label", ""):
        return "直链"
    return ""


def preference(item):
    codec = codec_name(item)
    mp4 = str(item.get("ext") or "mp4").lower() == "mp4"
    compatible = 3 if mp4 and codec in ("H.264", "来源编码") else 2 if mp4 else 1
    audio = item.get("has_audio")
    direct = 2 if audio is True else 1 if audio is not False and transport_name(item) == "直链" else 0
    fps = number(item.get("fps"))
    return (fps >= 50, compatible, round(fps), number(item.get("bitrate")), direct, codec == "H.264")


def recommended_formats(formats):
    groups = {}
    for item in formats:
        key = resolution(item)
        if key not in groups or preference(item) > preference(groups[key]):
            groups[key] = item
    return [groups[key] for key in sorted(groups, reverse=True)]


def choice_label(item):
    pixels = resolution(item)
    label = f"{str(pixels) + 'p' if pixels else '来源画质'}-{str(item.get('ext') or 'mp4').upper()}"
    fps = number(item.get("fps"))
    if fps >= 50:
        label += f" · {round(fps)}帧"
    dynamic_range = item.get("dynamic_range")
    if dynamic_range and dynamic_range != "SDR":
        label += f" · {dynamic_range}"
    return label


def detail_label(item):
    parts = [str(item.get("ext") or "mp4").upper(), codec_name(item)]
    fps = number(item.get("fps"))
    if fps:
        parts.append(f"{fps:g}帧")
    if item.get("dynamic_range") and item["dynamic_range"] != "SDR":
        parts.append(item["dynamic_range"])
    mode = transport_name(item)
    if mode:
        parts.append(mode)
    return " · ".join(parts)
