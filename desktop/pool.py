"""Reusable isolated engines with URL affinity and file-based task IPC."""

import os
import shutil
import subprocess
import sys
import uuid
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer

from .media import canonical_url
from .jobobject import ProcessTree
from .storage import data_dir


class Engine(QObject):
    def __init__(self, pool):
        super().__init__(pool)
        self.pool, self.active, self.keys = pool, None, OrderedDict()
        self.tree = None
        self.ended = False
        self.root = data_dir() / "engine" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        (self.root / "heartbeat").touch()
        self.process = QProcess(self)
        self.process.finished.connect(self.stopped)
        self.process.errorOccurred.connect(self.failed)
        self.process.started.connect(lambda: QTimer.singleShot(100, self.bind_tree))
        self.heartbeat = QTimer(self)
        self.heartbeat.setInterval(5000)
        self.heartbeat.timeout.connect(self.touch)
        self.heartbeat.start()
        if getattr(sys, "frozen", False):
            args = ["--engine", str(self.root)]
            cwd = str(Path(sys.executable).parent)
        else:
            args = ["-m", "desktop", "--engine", str(self.root)]
            cwd = str(Path(__file__).resolve().parent.parent)
        self.process.setWorkingDirectory(cwd)
        self.process.start(sys.executable, args)

    def bind_tree(self):
        if not self.ended and self.process.processId():
            self.tree = ProcessTree(self.process.processId())

    def touch(self):
        if self.root.is_dir():
            (self.root / "heartbeat").touch()

    def submit(self, worker):
        self.active = worker
        worker.engine, worker.process = self, self.process
        request = self.root / (worker.path.stem + ".request")
        temporary = request.with_suffix(".tmp")
        temporary.write_text(str(worker.path), encoding="utf-8")
        os.replace(temporary, request)

    def release(self, worker):
        if self.active is worker:
            if worker.succeeded:
                key = (canonical_url(worker.command["url"]), worker.command.get("common", True))
                self.keys[key] = True
                self.keys.move_to_end(key)
                while len(self.keys) > 8:
                    self.keys.popitem(last=False)
            self.active = None

    def failed(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            if self.active:
                self.active.event.emit({"event": "error", "message": "后台进程启动失败，请重新打开程序。"})
            self.stopped(1)

    def stopped(self, code, *_):
        if self.ended:
            return
        self.ended = True
        self.heartbeat.stop()
        if self.tree:
            self.tree.close()
        worker, self.active = self.active, None
        self.keys.clear()
        if self in self.pool.engines:
            self.pool.engines.remove(self)
        if worker and not worker.ended:
            worker._finish(code)
        if self.root.is_dir():
            shutil.rmtree(self.root, ignore_errors=True)
        self.deleteLater()

    def stop(self):
        pid = self.process.processId()
        if pid and os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
        self.process.kill()
        self.process.waitForFinished(1500)
        self.stopped(1)


class EnginePool(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.engines = []

    def submit(self, worker):
        key = (canonical_url(worker.command["url"]), worker.command.get("common", True))
        idle = [engine for engine in self.engines if not engine.ended and engine.active is None]
        engine = next((e for e in idle if key in e.keys), None)
        if engine is None:
            engine = idle[0] if idle else Engine(self)
            if engine not in self.engines:
                self.engines.append(engine)
        engine.submit(worker)

    def close(self):
        for engine in list(self.engines):
            engine.stop()
