"""Isolated worker entrypoints; file IPC also works in windowed frozen apps."""

import json
import os
import sys
from pathlib import Path


def prepare():
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
def run(command_file, session):
    events_file = command_file.with_suffix(".events")
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
            report("progress", percent=-1, detail="正在准备媒体任务")
            report("result", **session.execute(command, report))
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


def main(command_path: str) -> int:
    prepare()
    from .session import Session
    return run(Path(command_path), Session())


def engine(directory: str) -> int:
    import time
    prepare()
    from .session import Session
    # Six GUI slots together retain at most 48 entries, below the 50-link cap.
    session = Session(capacity=8)
    root = Path(directory)
    while root.is_dir():
        if not (root / "heartbeat").exists() or time.time() - (root / "heartbeat").stat().st_mtime > 30:
            break
        for request in sorted(root.glob("*.request")):
            try:
                command_file = Path(request.read_text(encoding="utf-8"))
                request.unlink()
                code = run(command_file, session)
                with command_file.with_suffix(".events").open("a", encoding="utf-8") as output:
                    output.write(json.dumps({"event": "complete", "code": code}) + "\n")
            except OSError:
                continue
        time.sleep(0.05)
    return 0
