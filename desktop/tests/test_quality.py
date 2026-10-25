from desktop.media import normalize_formats, public_formats
from desktop.quality import choice_label, recommended_formats


def test_compact_choices_preserve_original_variants():
    raw = [{"id": f"{pixels}-{codec}", "height": pixels, "width": pixels * 16 // 9,
            "vcodec": codec, "url": f"https://cdn.test/{pixels}/{codec}",
            "ext": "webm" if codec == "vp9" else "mp4"}
           for pixels in (1080, 720, 480, 360, 240, 144) for codec in ("avc1", "vp9", "av01")]
    formats = public_formats(normalize_formats(raw))
    compact = recommended_formats(formats)
    assert len(formats) == 18 and len(compact) == 6
    assert [choice_label(f) for f in compact] == [f"{p}p-MP4" for p in (1080, 720, 480, 360, 240, 144)]
    assert all(f["codec"] == "avc1" for f in compact)


def test_portrait_unknown_and_higher_framerate():
    formats = [{"id": "30", "width": 1080, "height": 1920, "fps": 30, "codec": "avc1", "ext": "mp4"},
               {"id": "60", "width": 1080, "height": 1920, "fps": 60, "codec": "hev1", "ext": "mp4"},
               {"id": "unknown", "ext": "mp4"}]
    compact = recommended_formats(formats)
    assert [f["id"] for f in compact] == ["60", "unknown"]
    assert choice_label(compact[0]) == "1080p-MP4 · 60帧"
    assert choice_label(compact[1]) == "来源画质-MP4"
