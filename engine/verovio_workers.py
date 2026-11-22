from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from collections import deque
from contextvars import ContextVar
from importlib.util import find_spec
from multiprocessing.connection import Connection
from pathlib import Path

from engine import render

WORKERS = 2
CALL_SECONDS = 120
RUNNER = Path(__file__).with_name("verovio_runner.py")
log = logging.getLogger(__name__)


class VerovioFailed(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class WorkersBusy(Exception):
    pass


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
            raise VerovioFailed(f"{method}: {value}")
        return value

    def close(self) -> None:
        with self.lock:
            self.process.kill()
            self.process.wait()
            self.replies.close()
            self.requests.close()


class Request:
    def __init__(self, wait: float):
        self.wait = wait
        self.worker: _Worker | None = None
        self.handles: list[int] = []
        self.claiming = threading.Lock()

    def claim(self) -> _Worker:
        with self.claiming:
            if self.worker is None:
                self.worker = pool.take(self.wait)
            return self.worker

    def release(self) -> None:
        if self.worker is None:
            return
        try:
            self.worker.call(None, "drop", tuple(self.handles))
        except VerovioFailed:
            pass
        finally:
            pool.give_back(self.worker)
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
        self.turns = threading.Condition()
        self.workers = [_Worker() for _ in range(size)]
        self.free = list(self.workers)
        self.queue: deque[object] = deque()

    def take(self, wait: float) -> _Worker:
        ticket = object()
        with self.turns:
            self.queue.append(ticket)
            try:
                if not self.turns.wait_for(lambda: self.queue[0] is ticket and self.free, wait):
                    raise WorkersBusy(f"no drawing worker came free within {wait} s")
                worker = self.free.pop()
            finally:
                self.queue.remove(ticket)
                self.turns.notify_all()
            if worker.process.poll() is not None:
                worker.close()
                self.workers[self.workers.index(worker)] = worker = _Worker()
            return worker

    def give_back(self, worker: _Worker) -> None:
        with self.turns:
            self.free.append(worker)
            self.turns.notify_all()

    def stop(self) -> None:
        for worker in self.workers:
            worker.close()


pool: Pool | None = None


def toolkit() -> Toolkit:
    request = current.get()
    if request is None:
        raise RuntimeError("A Verovio toolkit was asked for outside a request")
    worker = request.claim()
    handle = worker.call(None, "new")
    request.handles.append(handle)
    return Toolkit(worker, handle)


def claim() -> None:
    if pool is not None and (request := current.get()) is not None:
        request.claim()


def start() -> Pool:
    global pool
    pool = Pool()
    render.new_toolkit = toolkit
    return pool


def library_files() -> list[str]:
    return [str(path) for path in Path(find_spec("verovio").origin).parent.iterdir() if path.is_file()]
