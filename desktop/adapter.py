"""The only desktop module importing upstream implementation details.

Keep upstream files untouched. Contract tests pin this boundary rather than a
particular list of platforms. Opaque stream objects remain inside the worker.
"""

import base64
import hashlib
import copy
import json
import re
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import requests
from pathvalidate import sanitize_filename

from videodl import __version__ as core_version
from videodl.modules import BuildCommonVideoClient, BuildVideoClient, CommonVideoClientBuilder, VideoClientBuilder, VideoInfo
from videodl.videodl import VideoClient


class DesktopError(Exception):
    pass


def media_key(info, index=0):
    identity = str(info.identifier) if info.identifier else f"{index}:{info.title}"
    return hashlib.sha256(f"{info.source}\0{identity}".encode("utf-8")).hexdigest()


class QuietLogger:
    def __deepcopy__(self, memo):
        return self

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def find_tool(name: str) -> str | None:
    import sys
    roots = [Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)), Path(sys.executable).parent]
    for root in roots:
        path = root / "tools" / (name + (".exe" if sys.platform == "win32" else ""))
        if path.is_file():
            return str(path)
    return shutil.which(name)


def tool_environment():
    import os
    dirs = {str(Path(p).parent) for n in ("ffmpeg", "ffprobe", "node") if (p := find_tool(n))}
    os.environ["PATH"] = os.pathsep.join(sorted(dirs) + [os.environ.get("PATH", "")])


def check_contract() -> dict:
    import inspect
    expected = {"source", "title", "cover_url", "download_url", "save_path", "audio_download_url", "audio_save_path"}
    if not expected.issubset(VideoInfo.knownfields()):
        raise DesktopError("上游数据结构发生变化，需要更新桌面适配层。")
    if "url" not in inspect.signature(VideoClient.parsefromurl).parameters:
        raise DesktopError("上游解析接口发生变化，需要更新桌面适配层。")
    return {"core_version": core_version, "platforms": len(VideoClientBuilder.REGISTERED_MODULES), "common": len(CommonVideoClientBuilder.REGISTERED_MODULES)}


def filename(title: str, fallback="未命名") -> str:
    return (sanitize_filename(str(title), platform="Windows").strip(" .") or fallback)[:100].rstrip(" .") or fallback


def extension(value, default="mp4") -> str:
    ext = str(value or default).lower().lstrip(".")
    return ext if re.fullmatch(r"[a-z0-9]{1,8}", ext) else default


def unique_path(path: Path) -> Path:
    candidate = path
    count = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({count}){path.suffix}")
        count += 1
    return candidate


def cover_url(value) -> str:
    if isinstance(value, str):
        return ("https:" + value) if value.startswith("//") else value
    if isinstance(value, (list, tuple)):
        return next((s for v in value if (s := cover_url(v))), "")
    if isinstance(value, dict):
        return cover_url(value.get("url") or value.get("src") or value.get("url_list"))
    return ""


def download_error(exc: Exception) -> str:
    if isinstance(exc, DesktopError):
        return str(exc)
    if isinstance(exc, requests.HTTPError):
        return f"服务器拒绝了请求（HTTP {exc.response.status_code}），请重新解析或稍后重试。"
    if isinstance(exc, (requests.Timeout, subprocess.TimeoutExpired)):
        return "连接超时，请检查网络后重试。"
    if isinstance(exc, requests.RequestException):
        return "网络请求失败，请检查网络或稍后重试。"
    if isinstance(exc, PermissionError):
        return "无法写入保存目录，请选择可写入的文件夹。"
    if isinstance(exc, OSError):
        return "文件操作失败，请检查保存路径和可用空间。"
    return f"任务未完成（{type(exc).__name__}），请重新解析后重试。"


@contextmanager
def upstream_progress(report):
    """Bridge Rich progress in this isolated worker, without editing upstream."""
    from videodl.modules.sources import base
    original = base.Progress
    class Progress(original):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = True
            self.last_event = 0.0
            super().__init__(*args, **kwargs)

        def update(self, task_id, *args, **kwargs):
            result = super().update(task_id, *args, **kwargs)
            now = time.monotonic()
            if now - self.last_event >= 0.15:
                task = next((t for t in self.tasks if t.id == task_id), None)
                if task and task.fields.get("kind") != "overall":
                    self.last_event = now
                    known = task.total and task.total > 0
                    report("progress", percent=min(99, int(task.percentage)) if known else -1,
                           detail="正在下载媒体", completed=int(task.completed), total=int(task.total or 0))
            return result
    base.Progress = Progress
    try:
        yield
    finally:
        base.Progress = original


class Adapter:
    def __init__(self, output: Path, report=lambda *a, **k: None, common=True):
        check_contract()
        tool_environment()
        self.output = Path(output)
        self.report = report
        names = list(VideoClientBuilder.REGISTERED_MODULES)
        if common:
            names += list(CommonVideoClientBuilder.REGISTERED_MODULES)
        config = {name: {"work_dir": str(output), "disable_print": True, "max_retries": 2, "logger_handle": QuietLogger()} for name in names + ["WebMediaGrabber"]}
        self.client = VideoClient(allowed_video_sources=names, init_video_clients_cfg=config,
                                  requests_overrides={name: {"timeout": 18} for name in names + ["WebMediaGrabber"]})
        self.client.logger_handle = QuietLogger()

    def parse(self, url: str):
        from .storage import parse_links
        if parse_links(url) != [url]:
            raise DesktopError("请输入完整的 http 或 https 视频链接。")
        self.report("progress", percent=-1, detail="正在解析链接；通用解析可能需要一些时间")
        infos = self.client.parsefromurl(url=url)
        valid = [info for info in (infos or []) if info.with_valid_download_url]
        if not valid:
            raise DesktopError("没有解析到可下载内容。请检查链接，或稍后重试。")
        return valid

    def source_client(self, info):
        if info.source == self.client.web_media_grabber.source:
            return self.client.web_media_grabber
        for mapping, build in ((self.client.video_clients, BuildVideoClient), (self.client.common_video_clients, BuildCommonVideoClient)):
            if info.source in mapping:
                if isinstance(mapping[info.source], dict):
                    mapping[info.source] = build(module_cfg=mapping[info.source]["cfg"])
                return mapping[info.source]
        raise DesktopError("上游返回了未注册的解析器，需要更新适配层。")

    def summary(self, infos, with_thumbnail=True):
        result = []
        for index, info in enumerate(infos):
            url_ext = Path(urlsplit(info.download_url).path).suffix.lower().lstrip(".") if isinstance(info.download_url, str) else ""
            audio_formats = {"mp3", "m4a", "aac", "flac", "ogg", "opus", "wav", "aiff", "wma", "mka"}
            media_kind = "audio" if url_ext in audio_formats or str(info.ext).lower() in audio_formats else "video"
            result.append({"index": index, "title": info.title or "未命名媒体", "source": info.source,
                           "ext": info.ext, "has_cover": bool(cover_url(info.cover_url)),
                           "separate_audio": bool(info.audio_download_url), "audio_ext": info.audio_ext,
                           "media_kind": media_kind, "item_key": media_key(info, index)})
        thumbnail = ""
        if with_thumbnail and infos and cover_url(infos[0].cover_url):
            try:
                data, _ = self.cover_bytes(infos[0], limit=3 * 1024 * 1024)
                thumbnail = base64.b64encode(data).decode("ascii")
            except Exception:
                pass
        return {"items": result, "thumbnail": thumbnail, "core_version": core_version}

    def cover_bytes(self, info, limit=24 * 1024 * 1024):
        url = cover_url(info.cover_url)
        if not url.startswith(("https://", "http://")):
            raise DesktopError("这个条目没有可用的封面。")
        headers = dict(info.default_download_headers or getattr(self.source_client(info), "default_download_headers", {}) or {})
        headers = {k: v for k, v in headers.items() if k.lower() not in {"cookie", "authorization"}}
        with requests.get(url, headers=headers, timeout=18, stream=True) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > limit:
                    raise DesktopError("封面文件较大，已跳过预览或保存。")
                chunks.append(chunk)
            data = b"".join(chunks)
            import filetype
            kind = filetype.guess(data)
            if not data or not kind or not kind.mime.startswith("image/"):
                raise DesktopError("服务器返回的封面不是有效图片。")
            return data, kind.extension

    def fetch_media(self, info, target: Path, audio_only=False):
        item = copy.deepcopy(info)
        item.title = target.stem
        if audio_only:
            item.download_url = item.audio_download_url
            item.default_download_headers = item.default_audio_download_headers or item.default_download_headers
            item.default_download_cookies = item.default_audio_download_cookies or item.default_download_cookies
            item.ext = extension(item.audio_ext, "m4a")
            item.guess_video_ext_result = item.guess_audio_ext_result
            item.download_with_ffmpeg = False
        if audio_only:
            item.audio_download_url = ""
        client = self.source_client(item)
        # Keep upstream's regenerated HLS paths and partial files inside this
        # owned temporary directory, including on failure and audio-only jobs.
        with tempfile.TemporaryDirectory(prefix=".media-", dir=target.parent) as scratch:
            self.report("scratch", path=scratch)
            client.work_dir = scratch
            item.save_path = str(Path(scratch) / str(item.source) / (item.title + "." + extension(item.ext)))
            item.audio_save_path = str(Path(scratch) / str(item.source) / (item.title + ".audio." + extension(item.audio_ext, "m4a")))
            with upstream_progress(self.report):
                downloaded = client.download(video_infos=[item], num_threadings=1, request_overrides={"timeout": 25})
            paths = [Path(v.save_path) for v in (downloaded or []) if Path(v.save_path).is_file() and Path(v.save_path).stat().st_size]
            if not paths:
                raise DesktopError("媒体下载未完成，请重新解析后重试。")
            actual = paths[0]
            target = unique_path(target.with_suffix(actual.suffix))
            shutil.move(str(actual), target)
        return target

    def extract_audio(self, media: Path, destination: Path) -> Path:
        ffmpeg, ffprobe = find_tool("ffmpeg"), find_tool("ffprobe")
        if not ffmpeg or not ffprobe:
            raise DesktopError("音频提取需要 FFmpeg 和 ffprobe，请使用包含媒体工具的完整发行包。")
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if __import__("os").name == "nt" else {}
        probe = subprocess.run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "json", str(media)], capture_output=True, text=True, timeout=45, **flags)
        try:
            codec = json.loads(probe.stdout)["streams"][0]["codec_name"]
        except (ValueError, KeyError, IndexError):
            raise DesktopError("这个媒体中没有可提取的音轨。")
        ext = {"aac": "m4a", "alac": "m4a", "mp3": "mp3", "opus": "opus", "vorbis": "ogg", "flac": "flac"}.get(codec, "wav" if codec.startswith("pcm_") else "mka")
        output = unique_path(destination.parent / (destination.name + "." + ext))
        self.report("progress", percent=-1, detail="正在提取原始音轨")
        result = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-n", "-i", str(media), "-map", "0:a:0", "-vn", "-c:a", "copy", str(output)], capture_output=True, timeout=7200, **flags)
        if result.returncode or not output.is_file() or not output.stat().st_size:
            output.unlink(missing_ok=True)
            raise DesktopError("音轨提取失败，请重试或保留视频文件。")
        return output

    def download(self, infos, options, indices=None, item_keys=None):
        indexed = list(enumerate(infos))
        if item_keys is not None:
            requested = set(item_keys)
            selected = [(index, info) for index, info in indexed if media_key(info, index) in requested]
            if {media_key(info, index) for index, info in selected} != requested:
                raise DesktopError("所选条目已经变化，请重新提取后再选择下载。")
        else:
            selected = indexed if indices is None else [(i, infos[i]) for i in indices if 0 <= i < len(infos)]
        if not selected or not any(options.get(k) for k in ("cover", "audio", "video")):
            raise DesktopError("请选择至少一个条目及一种下载内容。")
        if options.get("audio") and any(not i.audio_download_url for _, i in selected) and not find_tool("ffmpeg"):
            raise DesktopError("音频提取需要 FFmpeg，请使用完整发行包。")
        files, errors = [], []
        self.output.mkdir(parents=True, exist_ok=True)
        for number, (source_index, original) in enumerate(selected, 1):
            info = copy.deepcopy(original)
            title = filename(info.title)
            folder = self.output / title
            folder.mkdir(parents=True, exist_ok=True)
            self.report("progress", percent=-1, detail=f"正在处理 {number}/{len(selected)}：{info.title}")
            def record(path, kind):
                entry = {"path": str(path), "kind": kind, "item_key": media_key(original, source_index)}
                files.append(entry)
                self.report("file", **entry)
            if options.get("cover"):
                try:
                    data, ext = self.cover_bytes(info)
                    path = unique_path(folder / f"{title}_封面.{ext}")
                    path.write_bytes(data)
                    record(path, "cover")
                except Exception as exc:
                    errors.append("封面：" + download_error(exc))
            media = None
            if options.get("video"):
                try:
                    media = self.fetch_media(info, unique_path(folder / f"{title}.{extension(info.ext)}"))
                    record(media, "video")
                except Exception as exc:
                    errors.append("视频：" + download_error(exc))
            if options.get("audio"):
                try:
                    if info.audio_download_url:
                        audio = self.fetch_media(info, unique_path(folder / f"{title}.{extension(info.audio_ext, 'm4a')}"), audio_only=True)
                    elif media:
                        audio = self.extract_audio(media, folder / title)
                    else:
                        # Upstream temporary downloads stay on the chosen disk and
                        # are removed even when extraction fails.
                        with tempfile.TemporaryDirectory(prefix=".audio-", dir=folder) as temp:
                            self.report("scratch", path=temp)
                            temp_media = self.fetch_media(info, Path(temp) / f"{title}.{extension(info.ext)}")
                            audio = self.extract_audio(temp_media, folder / title)
                    record(audio, "audio")
                except Exception as exc:
                    errors.append("音频：" + download_error(exc))
        return {"files": files, "errors": errors, "status": "partial" if files and errors else "failed" if errors else "done"}
