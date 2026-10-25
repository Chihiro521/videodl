"""One isolated process per job; file events also work in windowed frozen apps."""

import json
import os
import sys
from pathlib import Path


def main(command_path: str) -> int:
    command_file = Path(command_path)
    events_file = command_file.with_suffix(".events")
    # A windowed executable has no console streams. Upstream Rich needs them.
    sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    sys.stdin = open(os.devnull, "r", encoding="utf-8")
    if os.name == "nt":
        import subprocess
        original_popen = subprocess.Popen
        class HiddenPopen(original_popen):
            def __init__(self, *args, **kwargs):
                kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
                super().__init__(*args, **kwargs)
        subprocess.Popen = HiddenPopen
    with events_file.open("a", encoding="utf-8", buffering=1) as output:
        def report(event, **values):
            output.write(json.dumps({"event": event, **values}, ensure_ascii=False) + "\n")
            output.flush()
        try:
            command = json.loads(command_file.read_text(encoding="utf-8"))
            if command["action"] == "updates":
                from .updates import check_updates
                report("result", **check_updates())
                return 0
            from .adapter import Adapter, check_contract
            if command["action"] == "diagnostics":
                report("result", **check_contract())
                return 0
            adapter = Adapter(Path(command["output"]), report, common=command.get("common", True))
            infos = adapter.parse(command["url"])
            summary = adapter.summary(infos, with_thumbnail=command["action"] == "parse")
            report("parsed", **summary)
            if command["action"] == "download":
                report("result", **adapter.download(infos, command["options"], command.get("indices"), command.get("item_keys")))
            else:
                report("result", **summary)
            return 0
        except Exception as exc:
            try:
                from .adapter import download_error
                message = download_error(exc)
            except Exception:
                message = f"运行依赖未能加载（{type(exc).__name__}），请使用完整发行包。"
            if locals().get("command", {}).get("action") == "updates":
                message = "检查更新未完成，请稍后重试，或直接打开下载页面查看发行版。"
            report("error", message=message)
            return 1
