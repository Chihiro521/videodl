"""Worker-owned, expiring cache of opaque parser results."""

import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlsplit

from .media import canonical_url, legacy_media_key, media_key


class Session:
    def __init__(self, capacity=50, ttl=600, clock=time.monotonic):
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self.cache = OrderedDict()
        self.adapters = {}

    def execute(self, command, report):
        from .adapter import Adapter
        common = command.get("common", True)
        if common not in self.adapters:
            self.adapters[common] = Adapter(Path(command["output"]), report, common=common)
        adapter = self.adapters[common]
        adapter.output, adapter.report = Path(command["output"]), report
        url = canonical_url(command["url"])
        from .bilibili_auth import revision
        auth_revision = revision() if (urlsplit(url).hostname or "") in ("www.bilibili.com", "m.bilibili.com", "bilibili.com", "b23.tv") else 0
        key = (url, common, auth_revision)
        for old_key, (created, _) in list(self.cache.items()):
            if self.clock() - created >= self.ttl or (old_key[0] == url and old_key[2] != auth_revision):
                self.cache.pop(old_key)

        def parse(force=False):
            started = self.clock()
            report("phase", stage="parse")
            if force:
                self.cache.pop(key, None)
            cached = self.cache.pop(key, None) if not force else None
            if cached:
                self.cache[key] = cached
                report("progress", percent=-1, detail="正在复用已提取的媒体信息")
                infos = cached[1]
            else:
                # A stuck upstream call must not exceed the public parse budget.
                def timeout():
                    report("error", message="提取超时（60 秒），可稍后重试。")
                    os._exit(124)
                watchdog = threading.Timer(60, timeout)
                watchdog.daemon = True
                watchdog.start()
                try:
                    infos = adapter.parse(command["url"])
                finally:
                    watchdog.cancel()
                self.cache[key] = (self.clock(), infos)
                while len(self.cache) > self.capacity:
                    self.cache.popitem(last=False)
            summary = adapter.summary(infos)
            requested = command.get("item_keys")
            if requested and command.get("identity_version") != 2:
                mapped = {legacy_media_key(info, i): media_key(info, i) for i, info in enumerate(infos)}
                if all(key in mapped for key in requested):
                    requested = [mapped[key] for key in requested]
                elif len(infos) == 1 and len(requested) == 1:
                    requested = [media_key(infos[0])]
                else:
                    raise adapter.failure("历史记录中的分P已无法准确匹配，请重新提取后选择下载。")
            summary["selected_item_keys"] = requested
            summary.update(cache_hit=bool(cached), parse_seconds=round(self.clock() - started, 4))
            report("parsed", **summary)
            return infos, summary

        infos, summary = parse(command.get("refresh", False))
        if command["action"] != "download":
            return summary
        item_keys = summary.get("selected_item_keys")
        result = adapter.download(infos, command["options"], command.get("indices"), item_keys, command.get("format_ids"))
        # A cached signed resource may expire earlier than the cache's TTL.
        completed = {f["kind"] for f in result["files"]}
        pending = {kind: bool(enabled and kind not in completed) for kind, enabled in command["options"].items()}
        if summary["cache_hit"] and any(pending.get(k) for k in ("video", "audio")):
            report("progress", percent=-1, detail="媒体地址可能已失效，正在自动刷新一次")
            infos, refreshed = parse(force=True)
            item_keys = refreshed.get("selected_item_keys")
            retried = adapter.download(infos, pending, command.get("indices"), item_keys, command.get("format_ids"))
            result = {**retried, "files": result["files"] + retried["files"]}
            result["status"] = "partial" if result["files"] and result["errors"] else "failed" if result["errors"] else "done"
        return result
