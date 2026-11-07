"""Load every score through the drawing step, each in its own process, and list the ones that crash it.

    python tools/verovio_load_check.py [--reader-output] [--jobs N] [--out results.json] PATH [PATH ...]

A PATH is a score file or a folder searched for .musicxml, .xml and .mxl files. With --reader-output the inputs are
raw reader output (.mxl as the PDF reader writes it): each is cleaned and checked for problem bars, as `read_pdf` does
with each setting's result. Otherwise each is loaded with `load_toolkit`, as a sent score is.

A crash in the drawing library kills its process, so each file runs alone. For each file the result is "ok",
"crash (signal N)", "timeout", an error name, or "beam without notes" when the tidied score still holds a beam
with no note or chord in it, which crashes the drawing library when a cross-staff rest is left inside.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SUFFIXES = {".musicxml", ".xml", ".mxl"}
SECONDS = 300


def worker(path: Path, reader_output: bool) -> str:
    sys.path.insert(0, str(HERE))
    from engine.read_pdf import clean, _problem_spots
    from engine.render import ScoreError, load_toolkit
    from engine.render import noteless_beams

    data = path.read_bytes()
    try:
        if reader_output:
            data = clean(data)
            _problem_spots(data, timing=False)
        mei = load_toolkit(data).getMEI()
    except ScoreError:
        return "unreadable"
    return "beam without notes" if noteless_beams(mei) else "ok"


def check(path: Path, reader_output: bool) -> str:
    command = [sys.executable, "-I", str(Path(__file__).resolve()), "--worker", str(path)]
    try:
        run = subprocess.run(command + (["--reader-output"] if reader_output else []), capture_output=True, text=True,
                             timeout=SECONDS, cwd=HERE)
    except subprocess.TimeoutExpired:
        return "timeout"
    if run.returncode < 0:
        return f"crash (signal {-run.returncode})"
    if run.returncode:
        lines = run.stderr.strip().splitlines()
        return f"error: {lines[-1] if lines else run.returncode}"
    return run.stdout.strip().splitlines()[-1]


def inputs(paths: list[Path]) -> list[Path]:
    found = []
    for path in paths:
        found += sorted(p for p in path.rglob("*") if p.suffix in SUFFIXES) if path.is_dir() else [path]
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--reader-output", action="store_true")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        print(worker(args.paths[0], args.reader_output))
        return 0
    files = inputs(args.paths)
    with ThreadPoolExecutor(args.jobs) as pool:
        results = dict(zip(map(str, files), pool.map(lambda path: check(path, args.reader_output), files)))
    if args.out:
        args.out.write_text(json.dumps(results, indent=1))
    for name, result in results.items():
        if result != "ok":
            print(f"{result}: {name}")
    print(dict(Counter(re.sub(r": .*", "", result) for result in results.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
