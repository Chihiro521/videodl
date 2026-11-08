"""Qt process lifecycle and NDJSON events for source and packaged execution."""

import json
import os
import subprocess
import shutil
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .storage import data_dir, save_json


class Worker(QObject):
    event = Signal(dict)
    finished = Signal(int)

    def __init__(self, command, parent=None):
        super().__init__(parent)
        self.command = command
        self.path = data_dir() / "work" / (uuid.uuid4().hex + ".json")
        self.event_path = self.path.with_suffix(".events")
        self.offset = 0
        self.cancelled = False
        self.ended = False
        self.killer = None
        self.scratch = set()
        self.created_folders = set()
        self.engine = None
        self.succeeded = False
        self.pending = None
        self.process = QProcess(self)
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.poll)
        self.process.finished.connect(self._finish)
        self.process.errorOccurred.connect(self._process_error)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self.parse_timeout)

    def start(self):
        save_json(self.path, self.command)
        pool = getattr(self.parent(), "engine_pool", None)
        if pool is not None and self.command["action"] in ("parse", "download"):
            pool.submit(self)
            self.deadline.start(60000)
            self.timer.start()
            return
        if getattr(sys, "frozen", False):
            args = ["--worker", str(self.path)]
            cwd = str(Path(sys.executable).parent)
        else:
            args = ["-m", "desktop", "--worker", str(self.path)]
            cwd = str(Path(__file__).resolve().parent.parent)
        self.process.setWorkingDirectory(cwd)
        self.process.start(sys.executable, args)
        self.timer.start()

    def poll(self):
        try:
            with self.event_path.open("rb") as stream:
                stream.seek(self.offset)
                while line := stream.readline():
                    if not line.endswith(b"\n"):
                        break
                    self.offset = stream.tell()
                    event = json.loads(line.decode("utf-8"))
                    if event["event"] == "phase":
                        if not self.deadline.isActive():
                            self.deadline.start(60000)
                        continue
                    if event["event"] == "parsed":
                        self.deadline.stop()
                        self.succeeded = True
                    if self.engine and event["event"] in ("result", "error"):
                        self.pending = event
                        continue
                    if event["event"] == "complete":
                        self.timer.stop()
                        # Windows cannot unlink the event file while this reader
                        # is open. Release the file before completing the task.
                        QTimer.singleShot(0, lambda code=event.get("code", 0): self._finish(code))
                        return
                    if event.get("event") == "scratch":
                        self.scratch.add(event["path"])
                    if event.get("event") == "created_folder":
                        self.created_folders.add(event["path"])
                        continue
                    self.event.emit(event)
        except (OSError, ValueError):
            pass

    def cancel(self):
        self.cancelled = True
        pid = self.process.processId()
        if pid and os.name == "nt":
            self.killer = subprocess.Popen(["taskkill", "/PID", str(pid), "/T", "/F"],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
            QTimer.singleShot(3000, self._force_stop)
        else:
            self.process.kill()

    def _force_stop(self):
        if not self.ended:
            self.process.kill()

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.event.emit({"event": "error", "message": "后台进程启动失败，请重新打开程序。"})
            self._finish(1)

    def parse_timeout(self):
        self.pending = {"event": "error", "message": "提取超时（60 秒），可稍后重试。"}
        if self.engine:
            self.engine.stop()
        else:
            self.process.kill()

    def _finish(self, code, *_):
        if self.ended:
            return
        self.ended = True
        self.timer.stop()
        self.deadline.stop()
        self.poll()
        if self.engine:
            self.engine.release(self)
        if self.pending:
            self.event.emit(self.pending)
            self.pending = None
        if self.command.get("output"):
            root = Path(self.command["output"]).resolve()
            cache = (data_dir() / "temp").resolve()
            for name in sorted(self.scratch, key=len, reverse=True):
                scratch = Path(name).resolve()
                owned = scratch.is_relative_to(root) or scratch.is_relative_to(cache) or (self.engine is not None and scratch.is_relative_to(self.engine.root.resolve()))
                publishing = scratch.parent == root.parent and scratch.name.startswith(".videodl-publish-")
                if (owned and scratch.name.startswith((".media-", ".audio-")) or publishing) and scratch.is_dir():
                    shutil.rmtree(scratch, ignore_errors=True)
            for name in self.created_folders:
                folder = Path(name).resolve()
                if folder != root and folder.is_relative_to(root):
                    try:
                        folder.rmdir()
                    except OSError:
                        pass
        self.path.unlink(missing_ok=True)
        self.event_path.unlink(missing_ok=True)
        self.finished.emit(code)
