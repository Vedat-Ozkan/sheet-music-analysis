"""Which scores change their time unit (divisions) in mid-part, and how many bars hold a voice that runs past the bar's length.

    python tools/time_unit_corpus_check.py [--workers N] [--only SUBSTRING] [--timeout SECONDS] [--out FILE.jsonl]

Scores are the ones tools/correct_corpus_check.py uses. Per file: the distinct divisions values of each part, and for the whole
score as the index reads it, the number of bars in which some voice's notes or rests end after the meter's bar length.
Set CORRECT_ENGINE_ROOT to a folder holding another copy of engine/ to check that copy.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import correct_corpus_check as shared  # noqa: E402

sys.path.insert(0, os.environ.get("CORRECT_ENGINE_ROOT", str(shared.HERE)))


def musicxml_root(data: bytes) -> ET.Element:
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            data = archive.read(next(e.get("full-path") for e in container.iter() if e.tag.endswith("rootfile")))
    return ET.fromstring(data)


def check_file(path: Path) -> dict:
    from engine.render import load_toolkit
    from engine.score import TOLERANCE, ScoreIndex

    data = path.read_bytes()
    root = musicxml_root(data)
    changing = {}
    for part in root.findall("part"):
        values = []
        for element in part.iter("divisions"):
            if not values or values[-1] != element.text:
                values.append(element.text)
        if len(set(values)) > 1:
            changing[part.get("id")] = values
    index = ScoreIndex(load_toolkit(data).getMEI())
    over = []
    for measure in index.measures:
        if measure.full_length is None:
            continue
        ends: dict[tuple[int, int], object] = {}
        for event in measure.events:
            key = (event.staff, event.layer)
            ends[key] = max(ends.get(key, 0), event.onset + event.duration)
        if any(end > measure.full_length + TOLERANCE for end in ends.values()):
            over.append(measure.number)
    return {"changes_unit": changing, "bars": len(index.measures), "bars_over": len(over), "first_over": over[:5]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--only", default="")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--out", default="time_unit_corpus_check.jsonl")
    parser.add_argument("--one")
    args = parser.parse_args()
    if args.one:
        print("RESULT " + json.dumps(check_file(Path(args.one))))
        return
    queue = [path for path in shared.scores() if args.only in str(path)]
    out = Path(args.out)
    out.write_text("")
    results: dict[str, dict] = {}
    running: list[tuple[subprocess.Popen, Path, float]] = []
    while queue or running:
        while queue and len(running) < args.workers:
            path = queue.pop(0)
            running.append((subprocess.Popen([sys.executable, __file__, "--one", str(path)], stdout=subprocess.PIPE,
                                             stderr=subprocess.DEVNULL, text=True), path, time.time()))
        time.sleep(0.3)
        for entry in list(running):
            process, path, started = entry
            if process.poll() is None and time.time() - started < args.timeout:
                continue
            running.remove(entry)
            if process.poll() is None:
                process.kill()
                process.communicate()
                record = {"failed": f"no result after {args.timeout}s"}
            else:
                lines = [line for line in process.communicate()[0].splitlines() if line.startswith("RESULT ")]
                record = json.loads(lines[-1][7:]) if lines else {"failed": f"exit code {process.returncode}"}
            results[str(path)] = record
            with out.open("a") as handle:
                handle.write(json.dumps({"file": str(path), "record": record}) + "\n")
    changing = {name: r for name, r in results.items() if r.get("changes_unit")}
    over = {name: r for name, r in results.items() if r.get("bars_over")}
    failed = {name: r["failed"] for name, r in results.items() if "failed" in r}
    print(f"files {len(results)}, checked {len(results) - len(failed)}, failed {len(failed)}")
    print(f"files that change their time unit inside a part: {len(changing)}")
    print(f"bars with a voice past the bar's length: {sum(r['bars_over'] for r in over.values())} in {len(over)} files")
    print(f"  of which in files that change their time unit: {sum(r['bars_over'] for r in changing.values())} bars in {sum(1 for r in changing.values() if r['bars_over'])} files")
    print(f"  in files that do not: {sum(r['bars_over'] for n, r in over.items() if n not in changing)} bars in {sum(1 for n in over if n not in changing)} files")
    print("\nfiles that change their time unit (bars past the length / bars):")
    for name, r in sorted(changing.items()):
        print(f"  {Path(name).name}: {r['bars_over']} / {r['bars']}  parts {r['changes_unit']}")
    print("\nfailed:")
    for name, reason in failed.items():
        print(f"  {Path(name).name}: {reason}")


if __name__ == "__main__":
    main()
