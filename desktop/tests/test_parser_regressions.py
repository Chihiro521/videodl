import json

import pytest
import requests

from videodl.modules.common import pv, qingting, snapwc, xiazaitool
from videodl.modules.sources import cctv, iqiyi, pipigaoxiao, rednote, xinpianchang, youtube


def json_response(payload):
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode("utf-8")
    response.encoding = "utf-8"
    return response


@pytest.mark.parametrize("parser_name", ["_parsefromurlwithytdown", "_parsefromurlwithdownr"])
@pytest.mark.parametrize("verify", [None, "custom-ca.pem"])
@pytest.mark.parametrize("trusted_certificate", [True, False])
def test_youtube_resource_probes_validate_certificates(tmp_path, monkeypatch, parser_name, verify, trusted_certificate):
    client = youtube.YouTubeVideoClient(work_dir=str(tmp_path), disable_print=True)
    source_url = "https://www.youtube.com/watch?v=example"
    video_url, audio_url = "https://cdn.test/video.mp4", "https://cdn.test/audio.m4a"
    probes = []

    def post(url, **kwargs):
        if url == "https://app.ytdown.to/proxy.php":
            target = kwargs["data"]["url"]
            if target != source_url:
                return json_response({"api": {"fileUrl": target}})
            return json_response({"api": {"title": "Sample", "mediaItems": [
                {"type": "video", "mediaUrl": video_url, "mediaExtension": "mp4", "mediaFileSize": "10 MB"},
                {"type": "audio", "mediaUrl": audio_url, "mediaExtension": "m4a", "mediaFileSize": "1 MB"},
            ]}})
        assert url == "https://downr.org/.netlify/functions/nyt"
        return json_response({"title": "Sample", "medias": [
            {"type": "video", "url": video_url, "ext": "mp4", "width": 1280, "height": 720, "bitrate": 1000},
            {"type": "audio", "url": audio_url, "ext": "m4a", "bitrate": 128, "audioSampleRate": 44100},
        ]})

    def get(url, **kwargs):
        if url == "https://downr.org/.netlify/functions/analytics":
            return json_response({})
        assert url in (video_url, audio_url)
        probes.append((url, kwargs))
        if not trusted_certificate and kwargs.get("verify", True):
            raise requests.exceptions.SSLError("test certificate rejected")
        return json_response({})

    monkeypatch.setattr(youtube.requests, "post", post)
    monkeypatch.setattr(youtube.requests, "get", get)
    overrides = {} if verify is None else {"verify": verify}
    infos = getattr(client, parser_name)(source_url, request_overrides=overrides)

    assert [url for url, _ in probes] == [video_url, audio_url]
    assert all(kwargs.get("verify", True) == (True if verify is None else verify) for _, kwargs in probes)
    if trusted_certificate:
        assert len(infos) == 1
        assert infos[0].download_url == video_url
        assert infos[0].audio_download_url == audio_url
    else:
        assert infos == []


@pytest.mark.parametrize(("domain", "platform"), [
    ("bilibili.com", "bilibili"), ("b23.tv", "bilibili"), ("bili2233.cn", "bilibili"),
    ("douyin.com", "douyin"), ("kuaishou.com", "kuaishou"), ("pipix.com", "pipix"),
    ("xiaohongshu.com", "xhs"), ("xhslink.com", "xhs"), ("tiktok.com", "tiktok"),
    ("ixigua.com", "xigua"), ("weishi.qq.com", "weishi"), ("weibo.com", "weibo"),
    ("jd.com", "jingdong"), ("3.cn", "jingdong"), ("youtube.com", "youtube"),
    ("youtu.be", "youtube"), ("hao123.com", "haokan"), ("haokan.baidu.com", "haokan"),
    ("facebook.com", "facebook"), ("fb.watch", "facebook"), ("twitter.com", "twitter"),
    ("x.com", "twitter"), ("instagram.com", "instagram"), ("toutiao.com", "toutiao"),
])
@pytest.mark.parametrize(("url_template", "matches"), [
    ("https://{domain}/watch", True),
    ("https://PLAYER.{domain}.:443/watch", True),
    ("https://{domain}.example.test/watch", False),
])
def test_xiazaitool_platform_detection_matches_host_boundaries(monkeypatch, domain, platform, url_template, matches):
    monkeypatch.setattr(xiazaitool, "platformfromurl", lambda url: "fallback")
    url = url_template.format(domain=domain)
    result = xiazaitool.XiazaitoolVideoClient._detectplatform(None, url)
    assert result == (platform if matches else "fallback")


@pytest.mark.parametrize("url", [
    "https://notdouyin.com/watch",
    "https://example.test/douyin.com/watch",
    "https://example.test/?next=douyin.com",
    "https://douyin.com@example.test/watch",
    "https://example.test/#douyin.com",
    "https://[invalid",
    "",
])
def test_xiazaitool_other_urls_keep_platform_fallback(monkeypatch, url):
    monkeypatch.setattr(xiazaitool, "platformfromurl", lambda url: "fallback")
    assert xiazaitool.XiazaitoolVideoClient._detectplatform(None, url) == "fallback"


@pytest.mark.parametrize(("domain", "endpoint"), [
    ("douyin.com", "douyin"), ("bilibili.com", "bilibili"), ("b23.tv", "bilibili"),
    ("xiaohongshu.com", "redbook"), ("xhslink.com", "redbook"), ("kuaishou.com", "kuaishou"),
])
@pytest.mark.parametrize(("url_template", "matches"), [
    ("https://{domain}/watch", True),
    ("https://PLAYER.{domain}.:443/watch", True),
    ("https://{domain}.example.test/watch", False),
    ("https://example.test/?next={domain}", False),
])
def test_qingting_routes_by_hostname(tmp_path, monkeypatch, domain, endpoint, url_template, matches):
    client = qingting.QingtingVideoClient(work_dir=str(tmp_path), disable_print=True)
    requested = []

    def get(url, **kwargs):
        requested.append(url)
        return json_response({"code": 1})

    monkeypatch.setattr(qingting, "platformfromurl", lambda url: "other")
    monkeypatch.setattr(client, "_make33toolheaders", lambda: {})
    monkeypatch.setattr(client, "get", get)
    client.parsefromurl(url_template.format(domain=domain))
    assert requested == ([f"https://api.33tool.com/api/parse/{endpoint}"] if matches else [])


@pytest.mark.parametrize("url", [
    "https://share.ippzone.com/pp/post/123",
    "http://share.ippzone.com/pp/post/123?mid=456&pid=123",
    "https://share.ippzone.com/pp/post/123?mid=456&pid=123&next=a%2Fb%3Fc%3Dd#detail",
])
@pytest.mark.parametrize("suffix", ["", "<unexpected>", "\\unexpected", "^unexpected", "`unexpected"])
def test_pipigaoxiao_extracts_complete_url_without_extra_delimiters(tmp_path, monkeypatch, url, suffix):
    client = pipigaoxiao.PipigaoxiaoVideoClient(work_dir=str(tmp_path), disable_print=True)
    requested = []

    def post(endpoint, **kwargs):
        assert endpoint == "https://h5.ippzone.com/ppapi/share/fetch_content"
        requested.append(kwargs)
        return json_response({"data": {"post": {"content": "Sample", "imgs": [{"id": 1}],
            "videos": {"1": {"url": "https://cdn.test/sample.mp4"}}}}})

    monkeypatch.setattr(client, "post", post)
    monkeypatch.setattr(pipigaoxiao.FileTypeSniffer, "getfileextensionfromurl", lambda **kwargs: {"ext": "mp4"})
    infos = client.parsefromurl(url + suffix)

    assert len(requested) == 1
    assert requested[0]["headers"]["Referer"] == url
    assert json.loads(requested[0]["data"])["pid"] == 123
    assert infos[0].download_url == "https://cdn.test/sample.mp4"


@pytest.mark.parametrize(("url", "resolve_short_link", "identifier"), [
    ("http://xhslink.com/short", True, "note-id"),
    ("http://xhslink.com:80/short", True, "note-id"),
    ("HTTP://XHSLINK.COM/short", True, "note-id"),
    ("http://xhslink.com./short", True, "note-id"),
    ("https://xhslink.com/short", False, "short"),
    ("https://www.xiaohongshu.com/explore/note-id?next=http://xhslink.com", False, "note-id"),
    ("http://www.xiaohongshu.com/explore/note-id", False, "note-id"),
    ("http://xhslink.com.example.xhslink.com/short", False, "short"),
])
def test_rednote_short_link_resolution_uses_scheme_and_hostname(tmp_path, monkeypatch, url, resolve_short_link, identifier):
    client = rednote.RednoteVideoClient(work_dir=str(tmp_path), disable_print=True)
    resolved_url = "https://www.xiaohongshu.com/explore/note-id"
    requested = []
    raw = {"masterUrl": "https://cdn.test/sample.mp4", "title": "Sample",
        "imageList": [{"urlDefault": "https://cdn.test/cover.png"}]}

    def get(address, **kwargs):
        requested.append((address, kwargs))
        response = json_response({})
        response.url = resolved_url
        response._content = ("<script>window.__INITIAL_STATE__ = " + json.dumps(raw)
            + "</script></body></html>").encode("utf-8")
        return response

    monkeypatch.setattr(client, "get", get)
    monkeypatch.setattr(rednote.FileTypeSniffer, "getfileextensionfromurl", lambda **kwargs: {"ext": "mp4"})
    infos = client.parsefromurl(url)

    assert len(requested) == (2 if resolve_short_link else 1)
    assert requested[0][0] == url
    assert requested[0][1].get("allow_redirects", False) == resolve_short_link
    assert infos[0].identifier == identifier
    assert infos[0].download_url == "https://cdn.test/sample.mp4"


@pytest.mark.parametrize("url", [
    "http://xhslink.com.example.test/short",
    "http://xhslink.com@example.test/short",
])
def test_rednote_rejects_other_hosts_before_requesting(tmp_path, monkeypatch, url):
    client = rednote.RednoteVideoClient(work_dir=str(tmp_path), disable_print=True)

    def get(*args, **kwargs):
        pytest.fail("an unsupported host reached the request layer")

    monkeypatch.setattr(client, "get", get)
    assert client.parsefromurl(url) == []


@pytest.mark.parametrize(("url", "expected_parser"), [
    ("https://stock.xinpianchang.com/a123", "stock"),
    ("https://cdn.stock.xinpianchang.com/a123", "stock"),
    ("https://STOCK.XINPIANCHANG.COM.:443/a123", "stock"),
    ("https://www.xinpianchang.com/a123", "www"),
    ("https://notstock.xinpianchang.com/a123", "www"),
    ("https://stock.xinpianchang.com.example.test/a123", "www"),
    ("https://www.xinpianchang.com/a123?next=stock.xinpianchang.com", "www"),
    ("https://stock.xinpianchang.com@www.xinpianchang.com/a123", "www"),
    ("https://[invalid", "www"),
    ("", "www"),
])
def test_xinpianchang_stock_routing_matches_host_boundaries(tmp_path, monkeypatch, url, expected_parser):
    client = xinpianchang.XinpianchangVideoClient(work_dir=str(tmp_path), disable_print=True)
    calls = []
    overrides = {"timeout": 1}

    def parse_stock(address, request_overrides):
        calls.append(("stock", address, request_overrides))
        return ["stock"]

    def parse_www(address, request_overrides):
        calls.append(("www", address, request_overrides))
        return ["www"]

    monkeypatch.setattr(client, "_parsefromurlwithstock", parse_stock)
    monkeypatch.setattr(client, "_parsefromurlwithwww", parse_www)

    assert client.parsefromurl(url, request_overrides=overrides) == [expected_parser]
    assert calls == [(expected_parser, url, overrides)]


def test_snapwc_generates_matching_2048_bit_client_keys(tmp_path):
    client = snapwc.SnapWCVideoClient(work_dir=str(tmp_path), disable_print=True)
    private_pem, public_pem = client._genclientkeypair()
    private_key = snapwc.serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    public_key = snapwc.serialization.load_pem_public_key(public_pem.encode("utf-8"))

    assert private_key.key_size == 2048
    assert public_key.key_size == 2048
    assert private_key.public_key().public_numbers() == public_key.public_numbers()


@pytest.mark.parametrize("source_url", [
    "https://www.bilibili.com/video/BVsample?label=中文&next=a%2Bb",
    "https://www.facebook.com/example/videos/123",
    "https://www.ted.com/talks/example",
])
@pytest.mark.parametrize("with_audio", [True, False])
@pytest.mark.parametrize("title", ["Sample video", None])
def test_pv_uses_the_public_form_and_json_protocol(tmp_path, monkeypatch, source_url, with_audio, title):
    from types import SimpleNamespace
    from urllib.parse import parse_qs, urlsplit

    client = pv.PVVideoClient(work_dir=str(tmp_path), disable_print=True)
    source_host = urlsplit(source_url).hostname
    video_url = "https://cdn.test/video.mp4"
    audio_url = "https://cdn.test/audio.m4s"
    requested = []
    overrides = {"timeout": 1}

    def get(address, **kwargs):
        assert address == "https://www.parsevideo.com/"
        assert kwargs == overrides
        requested.append("GET")
        response = json_response({})
        response.cookies.set("session", "anonymous-test-session")
        return response

    def post(address, **kwargs):
        target = urlsplit(address)
        assert target.scheme == "https"
        assert target.netloc == "www.parsevideo.com"
        assert target.path == "/parsevideo/api.html"
        assert set(parse_qs(target.query)) == {"hash", "timestamp"}
        assert parse_qs(target.query)["timestamp"] == ["1234000"]
        assert parse_qs(kwargs.pop("data")) == {"url": [source_url], "proxyip": ["on"]}
        assert kwargs == overrides
        assert client.default_cookies["session"] == "anonymous-test-session"
        requested.append("POST")
        formats = [
            {"url": "https://cdn.test/low.mp4", "vcodec": "avc1", "acodec": "none", "height": 360},
            {"url": video_url, "vcodec": "avc1", "acodec": "none", "height": 1080},
        ]
        if with_audio:
            formats.append({"url": audio_url, "vcodec": "none", "acodec": "mp4a", "abr": 128})
        return json_response({"title": title, "formats": formats})

    monkeypatch.setattr(pv, "time", SimpleNamespace(time=lambda: 1234))
    monkeypatch.setattr(client, "get", get)
    monkeypatch.setattr(client, "post", post)
    monkeypatch.setattr(pv.FileTypeSniffer, "getfileextensionfromurl", lambda **kwargs: {"ext": "m4s" if kwargs["url"] == audio_url else "mp4"})
    infos = client.parsefromurl(source_url, request_overrides=overrides)

    assert requested == ["GET", "POST"]
    assert len(infos) == 1
    info = infos[0]
    assert not info.err_msg
    assert info.download_url == video_url
    assert bool(info.title)
    if title:
        assert info.title == title
    assert info.ext == ("mkv" if source_host == "www.facebook.com" else "mp4")
    assert info.audio_download_url == (audio_url if with_audio else "")
    if with_audio:
        assert info.audio_ext == "m4a"
    if source_host == "www.bilibili.com":
        assert info.default_download_headers == client.BILIBILI_REFERENCE_HEADERS
    if source_host == "www.ted.com":
        assert info.download_with_ffmpeg


@pytest.mark.parametrize("payload", [
    {"code": 0, "msg": "No result"},
    {"title": "Sample", "formats": []},
])
def test_pv_public_json_errors_return_an_invalid_result(tmp_path, monkeypatch, payload):
    client = pv.PVVideoClient(work_dir=str(tmp_path), disable_print=True)
    monkeypatch.setattr(client, "get", lambda *args, **kwargs: json_response({}))
    monkeypatch.setattr(client, "post", lambda *args, **kwargs: json_response(payload))

    infos = client.parsefromurl("https://www.bilibili.com/video/BVsample")
    assert len(infos) == 1
    assert infos[0].err_msg
    assert not infos[0].with_valid_download_url


@pytest.mark.parametrize(("channel", "subtitle", "album_cover"), [
    (2, "Episode title", "http://cdn.test/album.jpg"),
    ("1", "", ""),
])
@pytest.mark.parametrize("string_video_id", [True, False])
def test_iqiyi_parses_public_metadata_and_manifest(tmp_path, monkeypatch, channel, subtitle, album_cover, string_video_id):
    client = iqiyi.IQiyiVideoClient(work_dir=str(tmp_path), disable_print=True)
    video_url = "https://www.iqiyi.com/v_sample.html"
    tvid = "12345"
    title = subtitle or "Video title"
    manifest = "#EXTM3U\n#EXTINF:5,\nhttps://cdn.test/segment.ts\n#EXT-X-ENDLIST\n"
    requested = []
    overrides = {"timeout": 1}

    def get(address, **kwargs):
        requested.append(address)
        assert kwargs["timeout"] == 1
        if address == client.PLAYER_INIT_URL:
            assert kwargs["headers"] == {"referer": video_url}
            return json_response({"tvid": int(tvid)})
        if address == f"https://pcw-api.iqiyi.com/video/video/baseinfo/{tvid}":
            assert "params" not in kwargs
            return json_response({"code": "A00000", "data": {
                "tvId": tvid if string_video_id else int(tvid), "albumId": 67890,
                "name": "Video title", "subtitle": subtitle, "albumName": "Album title",
                "albumImageUrl": album_cover, "imageUrl": "http://cdn.test/video.jpg",
                "channelId": channel, "period": "2025-12-01", "order": 3, "videoCount": 12,
            }})
        assert address.startswith(client.VIDEO_CONFIG_URL + "?")
        return json_response({"data": {"program": {"video": [
            {"bid": 300, "ff": "mp4", "m3u8": manifest},
        ]}}})

    monkeypatch.setattr(client, "get", get)
    infos = client.parsefromurl(video_url, request_overrides=overrides)

    assert len(requested) == 3
    assert len(infos) == 1
    info = infos[0]
    assert not info.err_msg
    assert info.title == title
    assert info.cover_url == (album_cover or "http://cdn.test/video.jpg").replace("http://", "https://", 1)
    assert info.with_valid_download_url
    assert (tmp_path / "IQiyiVideoClient" / f"{tvid}.m3u8").read_text() == manifest
    assert info.raw_data["title"] == "Album title"
    assert info.raw_data["year"] == "2025"
    assert info.raw_data["cover_id"] == 67890
    assert info.raw_data["episode_all"] == 12
    assert info.raw_data["type"] == ("MOV" if str(channel) == "1" else "TV")
    assert str(info.raw_data["normal_ids"][0]["V"]) == tvid
    assert info.raw_data["normal_ids"][0]["E"] == 3


@pytest.mark.parametrize("payload", [
    {"code": "A00004", "data": {}},
    {"code": "A00000"},
    {"code": "A00000", "data": None},
    {"code": "A00000", "data": []},
    {"code": "A00000", "data": {"tvId": 54321, "name": "Other video"}},
    {"code": "A00000", "data": {"tvId": 12345}},
])
def test_iqiyi_rejects_unusable_public_metadata(tmp_path, monkeypatch, payload):
    client = iqiyi.IQiyiVideoClient(work_dir=str(tmp_path), disable_print=True)

    def get(address, **kwargs):
        if address == client.PLAYER_INIT_URL:
            return json_response({"tvid": 12345})
        assert address == "https://pcw-api.iqiyi.com/video/video/baseinfo/12345"
        return json_response(payload)

    monkeypatch.setattr(client, "get", get)
    assert client.parsefromurl("https://www.iqiyi.com/v_sample.html") == []


def test_iqiyi_public_metadata_defaults_optional_fields(tmp_path, monkeypatch):
    client = iqiyi.IQiyiVideoClient(work_dir=str(tmp_path), disable_print=True)
    video_url = "https://www.iqiyi.com/v_sample.html"

    def get(address, **kwargs):
        if address == client.PLAYER_INIT_URL:
            return json_response({"tvid": 12345})
        assert address == "https://pcw-api.iqiyi.com/video/video/baseinfo/12345"
        return json_response({"code": "A00000", "data": {"tvId": 12345, "name": "Video title"}})

    monkeypatch.setattr(client, "get", get)
    metadata = client._getvideocoverinfo(video_url, device_id="temporary-device")
    assert metadata["title"] == "Video title"
    assert metadata["image_url"] is None
    assert metadata["year"] == ""
    assert metadata["cover_id"] == 12345
    assert metadata["episode_all"] == 1
    assert metadata["normal_ids"] == [{"V": 12345, "E": 1, "defns": {}, "title": "Video title", "url": video_url, "referrer": video_url}]


@pytest.mark.parametrize("page_template", [
    'var guid = "{pid}"',
    'videoCenterId: "{pid}"',
    'changePlayer("{pid}")',
    'loadVideo("{pid}")',
    'var initMyAray = "{pid}"',
    'var ids = ["{pid}"]',
])
@pytest.mark.parametrize("nested_manifest", [True, False])
def test_cctv_metadata_request_uses_the_public_video_id(tmp_path, monkeypatch, page_template, nested_manifest):
    client = cctv.CCTVVideoClient(work_dir=str(tmp_path), disable_print=True)
    page_url = "https://tv.cctv.com/2026/11/07/sample.shtml"
    pid = "00112233445566778899aabbccddeeff"
    manifest_url = "https://cdn.test/master.m3u8"
    media_url = "https://cdn.test/1080.m3u8"
    metadata_params = []

    def get(address, **kwargs):
        if address == page_url:
            response = json_response({})
            response._content = page_template.format(pid=pid).encode("utf-8")
            return response
        if address == "https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do":
            metadata_params.append(kwargs["params"])
            metadata = {"title": "Sample"}
            if nested_manifest:
                metadata["manifest"] = {"hls_url": manifest_url}
            else:
                metadata["hls_url"] = manifest_url
            return json_response(metadata)
        assert address == manifest_url
        response = json_response({})
        response._content = ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1920x1080\n"
            + media_url + "\n").encode("utf-8")
        return response

    monkeypatch.setattr(client, "get", get)
    monkeypatch.setattr(cctv.FileTypeSniffer, "getfileextensionfromurl", lambda **kwargs: {"ext": "mp4"})
    infos = client.parsefromurl(page_url)

    assert len(metadata_params) == 1
    assert set(metadata_params[0]) == {"pid"}
    assert metadata_params[0]["pid"] == pid
    assert infos[0].identifier == pid
    assert infos[0].title == "Sample"
    assert infos[0].download_url == media_url
