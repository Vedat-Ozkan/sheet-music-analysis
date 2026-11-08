from __future__ import annotations

import calendar
import json
import os
import secrets
import struct
import threading
import time
from pathlib import PurePosixPath

import wasmtime

from engine.verovio_host import VerovioFailed

ENOENT, EBADF, EINVAL, ENOTTY = 44, 8, 28, 59
O_DIRECTORY = 0o200000
DIRENT_SIZE = 280
SECONDS = float(os.environ.get("VEROVIO_SECONDS", "300"))

_engine_config = wasmtime.Config()
_engine_config.epoch_interruption = True
_engine_config.wasm_exceptions = True
_engine = wasmtime.Engine(_engine_config)
_module: wasmtime.Module | None = None
_module_lock = threading.Lock()


def _compiled() -> wasmtime.Module:
    global _module
    with _module_lock:
        if _module is None:
            path = os.environ["VEROVIO_WASM"]
            load = wasmtime.Module.deserialize_file if path.endswith(".cwasm") else wasmtime.Module.from_file
            _module = load(_engine, path)
        return _module


def _ticker() -> None:
    while True:
        time.sleep(1)
        _engine.increment_epoch()


threading.Thread(target=_ticker, daemon=True).start()


class _Exit(Exception):
    pass


class _Runtime:
    def __init__(self):
        module = _compiled()
        self.store = wasmtime.Store(_engine)
        self.store.set_epoch_deadline(int(SECONDS))
        self.files: dict[str, bytes] = {}
        self.dirs: dict[str, set[str]] = {"/": set()}
        self.streams: dict[int, list] = {}
        self.next_fd = 3
        handlers = {
            "a": lambda code, sig, args: 0,
            "b": self.fd_close,
            "c": self.fail,
            "d": lambda fd, cmd, varargs: 0,
            "e": self.openat,
            "f": self.fd_write,
            "g": self.fd_seek,
            "h": lambda fd, op, varargs: -ENOTTY,
            "i": self.fail,
            "j": lambda: time.time() * 1000.0,
            "k": self.random_get,
            "l": self.fail,
            "m": self.getdents,
            "n": self.localtime,
            "o": self.mktime,
            "p": lambda environ, buf: 0,
            "q": self.environ_sizes,
            "r": self.tzset,
            "s": self.fd_read,
            "t": self.resize_heap,
            "u": self.load_embedded_files,
        }
        imports = [wasmtime.Func(self.store, item.type, handlers[item.name]) for item in module.imports]
        self.instance = wasmtime.Instance(self.store, module, imports)
        self.exports = self.instance.exports(self.store)
        self.memory: wasmtime.Memory = self.exports["v"]
        self.call("w")

    def call(self, name: str, *args):
        try:
            return self.exports[name](self.store, *args)
        except (wasmtime.Trap, wasmtime.WasmtimeError, _Exit) as error:
            raise VerovioFailed(f"drawing library stopped: {str(error).splitlines()[0]}") from None

    def read(self, address: int, size: int) -> bytes:
        return self.memory.read(self.store, address, address + size)

    def write(self, address: int, data: bytes) -> None:
        self.memory.write(self.store, data, address)

    def u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def c_string(self, address: int) -> str:
        if not address:
            return ""
        data = self.memory.get_buffer_ptr(self.store)
        end = address
        while data[end]:
            end += 1
        return bytes(data[address:end]).decode("utf-8", "replace")

    def put_string(self, text: str) -> int:
        data = text.encode("utf-8") + b"\0"
        address = self.call("ma", len(data))
        self.write(address, data)
        return address

    def fail(self, *args):
        raise _Exit("abort")

    def load_embedded_files(self, pointer: int) -> None:
        while True:
            name, size, content = struct.unpack("<III", self.read(pointer, 12))
            path = self.c_string(name)
            self.files[path] = self.read(content, size)
            parts = PurePosixPath(path).parts
            for depth in range(1, len(parts)):
                parent = str(PurePosixPath(*parts[:depth]))
                self.dirs.setdefault(parent, set()).add(parts[depth])
            pointer += 12
            if not self.u32(pointer):
                return

    def openat(self, dirfd: int, path: int, flags: int, varargs: int) -> int:
        name = str(PurePosixPath("/") / self.c_string(path))
        name = os.path.normpath(name)
        if name in self.dirs:
            entry = [name, sorted(self.dirs[name]), 0, True]
        elif name in self.files and not flags & O_DIRECTORY:
            entry = [name, self.files[name], 0, False]
        else:
            return -ENOENT
        fd = self.next_fd
        self.next_fd += 1
        self.streams[fd] = entry
        return fd

    def fd_close(self, fd: int) -> int:
        return 0 if self.streams.pop(fd, None) is not None else EBADF

    def fd_read(self, fd: int, iov: int, count: int, done: int) -> int:
        stream = self.streams.get(fd)
        if stream is None or stream[3]:
            return EBADF
        total = 0
        for index in range(count):
            address, size = struct.unpack("<II", self.read(iov + 8 * index, 8))
            chunk = stream[1][stream[2]:stream[2] + size]
            self.write(address, chunk)
            stream[2] += len(chunk)
            total += len(chunk)
            if len(chunk) < size:
                break
        self.write(done, struct.pack("<I", total))
        return 0

    def fd_write(self, fd: int, iov: int, count: int, done: int) -> int:
        total = sum(struct.unpack("<II", self.read(iov + 8 * index, 8))[1] for index in range(count))
        self.write(done, struct.pack("<I", total))
        return 0

    def fd_seek(self, fd: int, offset: int, whence: int, result: int) -> int:
        stream = self.streams.get(fd)
        if stream is None:
            return EBADF
        base = {0: 0, 1: stream[2], 2: len(stream[1])}.get(whence)
        if base is None or base + offset < 0:
            return EINVAL
        stream[2] = base + offset
        self.write(result, struct.pack("<q", stream[2]))
        return 0

    def getdents(self, fd: int, buffer: int, count: int) -> int:
        stream = self.streams.get(fd)
        if stream is None or not stream[3]:
            return -EBADF
        names = [".", ".."] + stream[1]
        start = stream[2] // DIRENT_SIZE
        written = 0
        for index in range(start, min(len(names), start + count // DIRENT_SIZE)):
            name = names[index]
            child = str(PurePosixPath(stream[0]) / name)
            kind = 4 if name in (".", "..") or child in self.dirs else 8
            record = struct.pack("<QqHB", index + 1, (index + 1) * DIRENT_SIZE, DIRENT_SIZE, kind)
            record += name.encode()[:255].ljust(DIRENT_SIZE - len(record), b"\0")
            self.write(buffer + written, record)
            written += DIRENT_SIZE
        stream[2] += written
        return written

    def random_get(self, buffer: int, size: int) -> int:
        self.write(buffer, secrets.token_bytes(size))
        return 0

    def environ_sizes(self, count: int, size: int) -> int:
        self.write(count, struct.pack("<I", 0))
        self.write(size, struct.pack("<I", 0))
        return 0

    def tzset(self, timezone: int, daylight: int, std_name: int, dst_name: int) -> None:
        self.write(timezone, struct.pack("<I", 0))
        self.write(daylight, struct.pack("<i", 0))
        self.write(std_name, b"UTC\0")
        self.write(dst_name, b"UTC\0")

    def localtime(self, seconds: int, tm: int) -> int:
        moment = time.gmtime(seconds)
        fields = (moment.tm_sec, moment.tm_min, moment.tm_hour, moment.tm_mday, moment.tm_mon - 1, moment.tm_year - 1900,
                  (moment.tm_wday + 1) % 7, moment.tm_yday - 1, 0, 0)
        self.write(tm, struct.pack("<9ii", *fields))
        return 0

    def mktime(self, tm: int) -> int:
        sec, minute, hour, day, month, year = struct.unpack("<6i", self.read(tm, 24))
        return calendar.timegm((year + 1900, month + 1, day, hour, minute, sec))

    def resize_heap(self, requested: int) -> int:
        current = self.memory.data_len(self.store)
        if requested > 2 ** 31:
            return 0
        pages = (max(requested, int(current * 1.2)) - current + 65535) // 65536
        try:
            self.memory.grow(self.store, pages)
        except wasmtime.WasmtimeError:
            return 0
        return 1


class Toolkit:
    def __init__(self, init_font: bool = False):
        self.runtime = _Runtime()
        self.handle = self.runtime.call("z")

    def _string(self, name: str, *args) -> str:
        return self.runtime.c_string(self.runtime.call(name, self.handle, *args))

    def _with_text(self, name: str, text: str, decode: bool = False):
        address = self.runtime.put_string(text)
        try:
            result = self.runtime.call(name, self.handle, address)
        finally:
            if self.runtime is not None:
                self.runtime.call("na", address)
        return self.runtime.c_string(result) if decode else result

    def setResourcePath(self, path: str) -> bool:
        return True

    def setOptions(self, options: dict) -> bool:
        return bool(self._with_text("ka", json.dumps(options)))

    def getOptions(self) -> dict:
        return json.loads(self._string("S"))

    def loadData(self, data: str) -> bool:
        return bool(self._with_text("Y", data))

    def getMEI(self, options: dict | None = None) -> str:
        return self._with_text("P", json.dumps(options or {}), decode=True)

    def getPageCount(self) -> int:
        return self.runtime.call("T", self.handle)

    def redoLayout(self, options: dict | None = None) -> None:
        self._with_text("$", json.dumps(options or {}))

    def select(self, selection: dict) -> bool:
        return bool(self._with_text("ja", json.dumps(selection)))

    def renderToSVG(self, page: int = 1, xml_declaration: bool = False) -> str:
        return self._string("fa", page, int(xml_declaration))

    def getLog(self) -> str:
        return self._string("O")
