from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

opened: list[str] = []
report: dict = {}


def read_file(path: str) -> int:
    try:
        with open(path, "rb", buffering=0) as file:
            size = 0
            while chunk := file.read(1 << 20):
                size += len(chunk)
            return size
    except OSError:
        return 0


def read_all(paths: list[str]) -> None:
    begun = time.monotonic()
    with ThreadPoolExecutor(16) as pool:
        size = sum(pool.map(read_file, paths))
    report.update(files=len(paths), bytes=size, seconds=round(time.monotonic() - begun, 1))


def start(file_list: Path) -> None:
    if file_list.is_file():
        threading.Thread(target=read_all, args=(file_list.read_text().splitlines(),), daemon=True).start()


def record() -> None:
    sys.addaudithook(lambda event, args: opened.append(args[0]) if event == "open" and isinstance(args[0], str) else None)


def save(file_list: Path, extra: list[str] = ()) -> None:
    libraries = [line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines() if ".so" in line.split()[-1]]
    paths = [path for path in dict.fromkeys(os.path.realpath(path) for path in [*libraries, *opened, *extra])
             if os.path.isfile(path) and not path.startswith(tempfile.gettempdir())]
    file_list.write_text("\n".join(paths) + "\n")
