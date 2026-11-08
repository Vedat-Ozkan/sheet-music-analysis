from __future__ import annotations

import os
import subprocess
import sys
import threading
from multiprocessing.connection import Connection

BACKEND = os.environ.get("VEROVIO_BACKEND", "inprocess")
POOL_SIZE = int(os.environ.get("VEROVIO_POOL", "2"))
SECONDS = float(os.environ.get("VEROVIO_SECONDS", "300"))


class VerovioFailed(RuntimeError):
    pass


class _Process:
    def __init__(self):
        parent_read, child_write = os.pipe()
        child_read, parent_write = os.pipe()
        self.process = subprocess.Popen([sys.executable, "-m", "engine.verovio_host", str(child_read), str(child_write)],
                                        pass_fds=(child_read, child_write), cwd=os.path.dirname(os.path.dirname(__file__)))
        os.close(child_read)
        os.close(child_write)
        self.receive, self.send = Connection(parent_read, writable=False), Connection(parent_write, readable=False)
        self.lock = threading.Lock()
        self.toolkits = 0

    def call(self, handle: int | None, method: str, args: tuple = ()):
        with self.lock:
            if self.process.poll() is not None:
                raise VerovioFailed(f"drawing process had stopped (exit {self.process.returncode})")
            try:
                self.send.send((handle, method, args))
                if not self.receive.poll(SECONDS):
                    self.process.kill()
                    raise VerovioFailed(f"drawing took over {SECONDS:.0f} s and was stopped")
                status, value = self.receive.recv()
            except (EOFError, BrokenPipeError, ConnectionResetError):
                self.process.wait()
                raise VerovioFailed(f"drawing library crashed (exit {self.process.returncode})") from None
        if status == "error":
            raise VerovioFailed(value)
        return value

    def alive(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> None:
        self.process.kill()
        self.process.wait()
        self.receive.close()
        self.send.close()


class _Pool:
    def __init__(self, size: int):
        self.lock = threading.Lock()
        self.workers = [_Process() for _ in range(size)]

    def take(self) -> _Process:
        with self.lock:
            for index, worker in enumerate(self.workers):
                if not worker.alive():
                    worker.stop()
                    self.workers[index] = _Process()
            worker = min(self.workers, key=lambda w: w.toolkits)
            worker.toolkits += 1
            return worker


_pool: _Pool | None = None
_pool_lock = threading.Lock()


def _shared_worker() -> _Process:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = _Pool(POOL_SIZE)
    return _pool.take()


class RemoteToolkit:
    def __init__(self, own_process: bool):
        self._own = own_process
        self._worker = _Process() if own_process else _shared_worker()
        self._handle = self._worker.call(None, "new")

    def __getattr__(self, method: str):
        return lambda *args: self._worker.call(self._handle, method, args)

    def __del__(self):
        worker = self.__dict__.get("_worker")
        if worker is None:
            return
        if self._own:
            worker.stop()
            return
        worker.toolkits -= 1
        try:
            worker.call(self._handle, "drop")
        except Exception:
            pass


def new_toolkit():
    if BACKEND == "process":
        return RemoteToolkit(own_process=True)
    if BACKEND == "worker":
        return RemoteToolkit(own_process=False)
    if BACKEND == "wasm":
        from engine.verovio_wasm import Toolkit
        return Toolkit(False)
    import verovio
    return verovio.toolkit(False)


def _serve(read_fd: int, write_fd: int) -> None:
    import verovio
    receive, send = Connection(read_fd, writable=False), Connection(write_fd, readable=False)
    toolkits: dict[int, verovio.toolkit] = {}
    next_handle = 0
    while True:
        try:
            handle, method, args = receive.recv()
        except EOFError:
            return
        try:
            if method == "new":
                next_handle += 1
                toolkits[next_handle] = verovio.toolkit(False)
                send.send(("ok", next_handle))
            elif method == "drop":
                toolkits.pop(handle, None)
                send.send(("ok", None))
            else:
                send.send(("ok", getattr(toolkits[handle], method)(*args)))
        except Exception as error:
            send.send(("error", f"{type(error).__name__}: {error}"))


if __name__ == "__main__":
    _serve(int(sys.argv[1]), int(sys.argv[2]))
