"""Extracted media catalogue: display metadata only, never temporary media URLs."""

import hashlib
from collections import OrderedDict

KINDS = {"video": "视频", "audio": "音频", "cover": "封面"}


class ResultCatalog:
    def __init__(self, rows=None):
        self.rows = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or row.get("kind") not in KINDS:
                continue
            if not all(key in row for key in ("id", "url", "index", "title")):
                continue
            if not isinstance(row["index"], int) or row["index"] < 0:
                continue
            self.rows.append({**row, "checked": False})

    def replace_summary(self, url, items):
        old = {row["id"]: row for row in self.rows if row["url"] == url}
        fresh = []
        for item in items:
            index = item["index"]
            key = item.get("item_key") or str(index)
            kinds = ["audio"] if item.get("media_kind") == "audio" else ["video", "audio"]
            if item.get("has_cover"):
                kinds.append("cover")
            for kind in kinds:
                row_id = hashlib.sha256(f"{url}\0{key}\0{kind}".encode("utf-8")).hexdigest()
                previous = old.get(row_id, {})
                fresh.append({"id": row_id, "url": url, "index": index, "item_key": item.get("item_key", ""),
                    "title": item.get("title") or "未命名媒体", "source": item.get("source", ""),
                    "kind": kind, "ext": item.get("ext", ""), "audio_ext": item.get("audio_ext", ""),
                    "separate_audio": bool(item.get("separate_audio")), "checked": previous.get("checked", False),
                    "job_id": previous.get("job_id", ""), "file": previous.get("file", ""),
                    "status": previous.get("status", "idle"), "detail": previous.get("detail", "")})
        # Re-extracting refreshes a source in place instead of duplicating rows.
        positions = [i for i, row in enumerate(self.rows) if row["url"] == url]
        insertion = positions[0] if positions else len(self.rows)
        self.rows = [row for row in self.rows if row["url"] != url]
        self.rows[insertion:insertion] = fresh
        return fresh

    def visible(self, kind="", query=""):
        query = query.strip().casefold()
        return [row for row in self.rows if (not kind or row["kind"] == kind)
                and (not query or query in row["title"].casefold())]

    def plan(self, rows):
        groups = OrderedDict()
        for row in rows:
            key = (row["url"], row.get("item_key") or row["index"])
            if key not in groups:
                groups[key] = {"url": row["url"], "title": row["title"], "indices": [row["index"]],
                    "item_keys": [row["item_key"]] if row.get("item_key") else None,
                    "options": {kind: False for kind in KINDS}, "result_ids": []}
            groups[key]["options"][row["kind"]] = True
            if row["id"] not in groups[key]["result_ids"]:
                groups[key]["result_ids"].append(row["id"])
        return list(groups.values())

    def link_job(self, job):
        for row in self.rows:
            if row["id"] in job.get("result_ids", []):
                row.update(job_id=job["id"], file="", status=job["status"], detail=job.get("detail", ""))

    def sync_job(self, job):
        for row in self.rows:
            if row.get("job_id") != job["id"]:
                continue
            files = [f for f in job.get("files", []) if f["kind"] == row["kind"]
                     and (not f.get("item_key") or f["item_key"] == row.get("item_key"))]
            if files:
                row.update(file=files[-1]["path"], status="done", detail="下载完成")
            else:
                status = job["status"]
                row.update(status="failed" if status in ("partial", "done") else status,
                           detail=job.get("detail", ""))
