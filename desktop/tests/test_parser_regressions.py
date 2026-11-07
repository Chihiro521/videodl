import json

import pytest
import requests

from videodl.modules.common import qingting, xiazaitool
from videodl.modules.sources import pipigaoxiao, youtube


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
