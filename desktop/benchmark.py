"""Compare two portable GUI releases on the same local extract/download flow."""

import argparse
import functools
import http.server
import json
import os
import statistics
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from .storage import save_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("old", "new", "media", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()
    counts = Counter()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_HEAD(self):
            counts["HEAD"] += 1
            super().do_HEAD()
        def do_GET(self):
            counts["GET"] += 1
            super().do_GET()

    handler = functools.partial(Handler, directory=str(args.media.resolve().parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    trials = []
    try:
        for trial in range(args.trials):
            for version, executable in (("old", args.old), ("new", args.new)):
                root = args.output.resolve() / f"{version}-{trial + 1}"
                root.mkdir(parents=True, exist_ok=False)
                command, report = root / "input.json", root / "report.json"
                save_json(command, {"url": f"http://127.0.0.1:{server.server_port}/" + quote(args.media.name),
                    "output": str(root / "downloads"), "kind": "video"})
                env = os.environ.copy()
                env.update(QT_QPA_PLATFORM="offscreen", VIDEODL_DESKTOP_DATA=str(root / "appdata"),
                    VIDEODL_GUI_SMOKE_INPUT=str(command), VIDEODL_GUI_SMOKE_REPORT=str(report))
                env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
                env.pop("PYTHONHOME", None)
                env.pop("PYTHONPATH", None)
                before = counts.copy()
                started = time.perf_counter()
                result = subprocess.run([str(executable.resolve())], env=env, capture_output=True, timeout=130)
                seconds = round(time.perf_counter() - started, 3)
                data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
                if result.returncode or data.get("error") or not data.get("jobs") or data["jobs"][0]["status"] != "done":
                    raise RuntimeError(f"{version} trial {trial + 1} did not complete")
                item = {"version": version, "trial": trial + 1, "seconds": seconds,
                    "requests": dict(counts - before), "cache_hit": data["jobs"][0].get("cache_hit")}
                trials.append(item)
                print(json.dumps(item), flush=True)
        medians = {version: statistics.median(t["seconds"] for t in trials if t["version"] == version) for version in ("old", "new")}
        output = {"media_bytes": args.media.stat().st_size, "trials": trials, "median_seconds": medians,
            "reduction_percent": round(100 * (1 - medians["new"] / medians["old"]), 1)}
        save_json(args.output / "benchmark.json", output)
        print(json.dumps({key: value for key, value in output.items() if key != "trials"}), flush=True)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
