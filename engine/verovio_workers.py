from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from contextvars import ContextVar
from importlib.util import find_spec
from multiprocessing.connection import Connection
from pathlib import Path

from engine import render
from engine.render import UNREADABLE, ScoreError

WORKERS = 2
CALL_SECONDS = 120
RUNNER = Path(__file__).with_name("verovio_runner.py")
log = logging.getLogger(__name__)


class VerovioFailed(ScoreError):
    def __init__(self, reason: str):
        super().__init__(UNREADABLE)
        self.reason = reason


class _Worker:
    def __init__(self):
        parent_read, child_write = os.pipe()
        child_read, parent_write = os.pipe()
        self.process = subprocess.Popen([sys.executable, str(RUNNER), str(child_read), str(child_write)],
                                        pass_fds=(child_read, child_write))
        os.close(child_read)
        os.close(child_write)
        self.replies = Connection(parent_read, writable=False)
        self.requests = Connection(parent_write, readable=False)
        self.lock = threading.Lock()
        self.bound = 0

    def call(self, handle: int | None, method: str, args: tuple = ()):
        with self.lock:
            if self.process.poll() is not None:
                raise VerovioFailed(f"worker had stopped (exit {self.process.returncode})")
            try:
                self.requests.send((handle, method, args))
                if not self.replies.poll(CALL_SECONDS):
                    self.process.kill()
                    self.process.wait()
                    log.warning("Verovio worker %s stopped: %s took over %s s", self.process.pid, method, CALL_SECONDS)
                    raise VerovioFailed(f"{method} took over {CALL_SECONDS} s")
                status, value = self.replies.recv()
            except (EOFError, OSError):
                self.process.wait()
                log.warning("Verovio worker %s crashed (exit %s) in %s", self.process.pid, self.process.returncode, method)
                raise VerovioFailed(f"crashed (exit {self.process.returncode}) in {method}") from None
        if status == "error":
            raise RuntimeError(f"Verovio {method}: {value}")
        return value

    def close(self) -> None:
        with self.lock:
            self.process.kill()
            self.process.wait()
            self.replies.close()
            self.requests.close()


class Request:
    def __init__(self):
        self.pool: Pool | None = None
        self.worker: _Worker | None = None
        self.handles: list[int] = []
        self.binding = threading.Lock()

    def release(self) -> None:
        if self.worker is None:
            return
        try:
            self.worker.call(None, "drop", tuple(self.handles))
        except VerovioFailed:
            pass
        finally:
            self.pool.unbind(self.worker)
            self.worker = None


current: ContextVar[Request | None] = ContextVar("verovio_request", default=None)


class Toolkit:
    def __init__(self, worker: _Worker, handle: int):
        self._worker = worker
        self._handle = handle

    def __getattr__(self, method: str):
        return lambda *args: self._worker.call(self._handle, method, args)


class Pool:
    def __init__(self, size: int = WORKERS):
        self.lock = threading.Lock()
        self.workers = [_Worker() for _ in range(size)]

    def bind(self) -> _Worker:
        with self.lock:
            for index, worker in enumerate(self.workers):
                if worker.process.poll() is not None:
                    worker.close()
                    self.workers[index] = _Worker()
            worker = min(self.workers, key=lambda candidate: candidate.bound)
            worker.bound += 1
            return worker

    def unbind(self, worker: _Worker) -> None:
        with self.lock:
            worker.bound -= 1

    def toolkit(self) -> Toolkit:
        request = current.get()
        if request is None:
            raise RuntimeError("A Verovio toolkit was asked for outside a request")
        with request.binding:
            if request.worker is None:
                request.pool, request.worker = self, self.bind()
        handle = request.worker.call(None, "new")
        request.handles.append(handle)
        return Toolkit(request.worker, handle)

    def stop(self) -> None:
        for worker in self.workers:
            worker.close()


def start() -> Pool:
    pool = Pool()
    render.new_toolkit = pool.toolkit
    return pool


def library_files() -> list[str]:
    return [str(path) for path in Path(find_spec("verovio").origin).parent.iterdir() if path.is_file()]
