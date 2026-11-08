"""Build-time GUI checks, enabled only by the explicit diagnostic environment."""

import os
import time
from pathlib import Path

from PySide6.QtCore import QTimer

from .storage import load_json, save_json
from .quality import recommended_formats


def schedule_capture(window, report_path):
    path = Path(report_path)
    command_path = os.environ.get("VIDEODL_GUI_SMOKE_INPUT")
    command = load_json(Path(command_path), {}) if command_path else None
    started = time.monotonic()
    stage = "extract" if command else "capture"
    timer = QTimer(window)
    timer.setInterval(100)

    def capture(error=""):
        timer.stop()
        save_json(path, {"visible": window.isVisible(), "width": window.width(), "height": window.height(),
            "error": error, "failures": list(window.extraction_failures.values()),
            "results": [{key: row.get(key) for key in ("id", "url", "source_order", "kind", "status", "title", "formats", "format_id")} for row in window.catalog.rows],
            "groups": [{"url": url, "source_order": window.catalog.sources[url],
                        "row": window.source_row_map.get(url), "state": window.source_states.get(url, "done"),
                        "span": window.results_table.columnSpan(window.source_row_map[url], 0)}
                       for url in window.source_row_map],
            "jobs": [{key: job.get(key) for key in ("status", "options", "files", "cache_hit", "parse_seconds")} for job in window.jobs]})
        window.grab().save(str(path.with_suffix(".png")))
        window.close()

    def advance():
        nonlocal stage
        if time.monotonic() - started > 110:
            capture("GUI operation timed out")
        elif stage == "capture":
            if time.monotonic() - started > 0.5:
                capture()
        elif stage == "extract" and not window.extraction_active and not window.extraction_waiting:
            if window.extraction_failures or not window.catalog.rows:
                capture("No usable extraction results")
                return
            kind = command.get("kind", "audio")
            rows = [row for row in window.catalog.rows if kind == "all" or row["kind"] == kind]
            for row in rows:
                if row["kind"] == "video" and row.get("formats"):
                    formats = recommended_formats(row["formats"])
                    row["format_id"] = formats[min(command.get("quality_index", 0), len(formats)-1)]["id"]
            window.render_results()
            window.type_filter.setCurrentIndex(max(0, window.type_filter.findData("" if kind == "all" else kind)))
            window.download_all_button.click()
            stage = "download"
        elif stage == "download" and not window.running and not any(job["status"] == "waiting" for job in window.jobs):
            capture()

    timer.timeout.connect(advance)
    if command:
        window.destination.setText(command["output"])
        window.common.setChecked(command.get("common", False))
        window.auto_download.setChecked(False)
        window.concurrency.setValue(command.get("concurrency", 1))
        window.save_mode.setCurrentIndex(max(0, window.save_mode.findData(command.get("save_mode", "flat"))))
        window.links.setPlainText(command.get("text", command.get("url", "")))
        window.start_preview()
    timer.start()
