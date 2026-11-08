"""Desktop-side normalization for YouTube Music track links.

The upstream SDK exposes one YouTube client. This small adapter keeps Music
URLs recognizable at the desktop boundary, then hands a normalized track URL
to that client without changing upstream files.
"""

import re
from urllib.parse import parse_qs, urlencode, urlsplit


class YouTubeMusicAdapter:
    HOST = "music.youtube.com"
    VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

    @classmethod
    def is_url(cls, url):
        return (urlsplit(url).hostname or "").lower() == cls.HOST

    @classmethod
    def track_id(cls, url):
        # Chat and Markdown copies sometimes escape ampersands as ``\&``.
        # Treat that presentation escape as a normal query separator.
        url = url.replace("\\&", "&")
        parts = urlsplit(url)
        value = parse_qs(parts.query, keep_blank_values=True).get("v", [""])[0]
        return value if cls.VIDEO_ID.fullmatch(value) else ""

    @classmethod
    def normalize(cls, url):
        """Return the ordinary YouTube track URL used by the upstream client."""
        url = url.replace("\\&", "&")
        if not cls.is_url(url):
            return url
        video_id = cls.track_id(url)
        if not video_id:
            return ""
        return "https://www.youtube.com/watch?" + urlencode({"v": video_id})

    @classmethod
    def mark_track(cls, info):
        """Tell the desktop catalog that this result is an audio-first track."""
        info._desktop_music = True
        info._desktop_single = True
        return info
