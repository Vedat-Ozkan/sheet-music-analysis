"""Hand every bar of every part of every score out through correct_bars and send it back, unchanged and with one pitch changed.

    python tools/correct_corpus_check.py [--workers N] [--only SUBSTRING] [--out FILE.jsonl] [--timeout SECONDS] [--clean]

Set CORRECT_ENGINE_ROOT to a folder holding another copy of engine/ to check that copy instead.
Scores: tests/data (this tree and the main checkout, for git-ignored ones) and the cached final PDF readings in the main
checkout's spike/omr. For every bar, two tries through engine.correct.replace_bars:
  unchanged  the bar exactly as handed out
  changed    the first plain note of the first voice that has one is moved up one letter name
Refusals are counted by message with the numbers blanked out. With --verify-untouched, every accepted "changed" result is read
back and the voices that were not changed must still hold the same notes.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get("CORRECT_ENGINE_ROOT", str(HERE)))
NEXT_LETTER = dict(zip("CDEFGAB", "DEFGABC"))
PLAIN = re.compile(r"[A-G](?:#+|b+)?[0-9]~?")


def main_checkout() -> Path:
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=HERE,
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


def scores() -> list[Path]:
    found: dict[str, Path] = {}
    for root in (HERE, main_checkout()):
        for path in sorted((root / "tests/data").rglob("*")):
            if path.suffix in (".musicxml", ".mxl", ".xml") and path.is_file():
                found.setdefault(str(path.relative_to(root)), path)
        for path in sorted((root / "spike/omr").glob("*/cache/runs/results-final--*.musicxml")):
            found.setdefault(f"{path.parents[2].name}/{path.name}", path)
    return list(found.values())


def read_score(path: Path, cleaned: bool) -> bytes:
    data = path.read_bytes()
    if not cleaned:
        return data
    from engine.read_pdf import clean

    if data[:2] != b"PK":
        sink = io.BytesIO()
        with zipfile.ZipFile(sink, "w") as archive:
            archive.writestr("score.xml", data)
        data = sink.getvalue()
    return clean(data)


def part_ids(score: bytes) -> list[str]:
    if score[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(score)) as archive:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            score = archive.read(next(e.get("full-path") for e in container.iter() if e.tag.endswith("rootfile")))
    root = ET.fromstring(score)
    if root.tag != "score-partwise":
        return []
    return [part.get("id") for part in root.findall("part")]


def blank(message: str) -> str:
    return re.sub(r"\d+(?:\.\d+)?(?:/\d+)?", "N", message)


def change_one_pitch(text: str) -> tuple[str, str] | None:
    lines = text.splitlines()
    for number, line in enumerate(lines):
        if line.startswith(("m", "x:", "N")) or ":" not in line:
            continue
        label, body = line.split(":", 1)
        tokens = body.split()
        for position, token in enumerate(tokens):
            if PLAIN.fullmatch(token.split("+")[0]):
                first, *rest = token.split("+")
                tokens[position] = "+".join([NEXT_LETTER[first[0]] + first[1:], *rest])
                lines[number] = f"{label}: {' '.join(tokens)}"
                return "\n".join(lines), label.strip()
    return None


def voices_of(bar, with_ties: bool = False) -> dict[tuple[int, int], list]:
    voices: dict[tuple[int, int], list] = {}
    for event in (event for event in bar.events if event.pitch):
        found = (event.onset, event.duration, event.pitch, event.grace) + ((event.tied,) if with_ties else ())
        voices.setdefault((event.staff, event.layer), []).append(found)
    return voices


def check_part(path: Path, part: str, verify: bool, cleaned: bool = False) -> dict:
    from engine import correct, notes
    from engine.errors import UserError

    mei_cache: dict[bytes, str] = {}
    real_load = correct.load_toolkit

    class Cached:
        def __init__(self, mei: str):
            self.mei = mei

        def getMEI(self):
            return self.mei

    def cached_load(data, *args, **kwargs):
        if kwargs or args:
            return real_load(data, *args, **kwargs)
        if data not in mei_cache:
            mei_cache[data] = real_load(data).getMEI()
        return Cached(mei_cache[data])

    correct.load_toolkit = cached_load
    try:
        score = read_score(path, cleaned)
        _, selected, index = correct._read(score, part)
    except Exception as error:
        return {"unopenable": f"{type(error).__name__}: {blank(str(error))[:160]}"}
    record = {"bars": 0, "unchanged": Counter(), "changed": Counter(), "voice_longer": 0, "zero_length": 0, "untouched_lost": 0, "untouched_ties_changed": 0}
    for measure in index.measures:
        record["bars"] += 1
        try:
            text = correct._bars_from_index(selected, index, measure.number)
            handed = notes.decode(text).bar(measure.name)
        except Exception as error:
            record["unchanged"][f"HANDOUT {type(error).__name__}: {blank(str(error))[:120]}"] += 1
            continue
        if handed.length == 0:
            record["zero_length"] += 1
        if any(max(onset + duration for onset, duration, *_ in events) > handed.length for events in voices_of(handed).values()):
            record["voice_longer"] += 1
        try:
            correct.replace_bars(score, text, part=part)
            record["unchanged"]["ok"] += 1
        except UserError as error:
            record["unchanged"][blank(str(error))[:160]] += 1
        except Exception as error:
            record["unchanged"][f"CRASH {type(error).__name__}: {blank(str(error))[:120]}"] += 1
        altered = change_one_pitch(text)
        if altered is None:
            record["changed"]["no pitched note to change"] += 1
            continue
        try:
            output = correct.replace_bars(score, altered[0], part=part)
            record["changed"]["ok"] += 1
            if verify:
                _, _, after = correct._read(output, part)
                before_voices, after_voices = voices_of(index.measure(measure.number)), voices_of(after.measure(measure.number))
                staff, voice = (int(n) for n in altered[1].split("."))
                others = [key for key in before_voices if key != (staff, voice)]
                if any(before_voices[key] != after_voices.get(key) for key in others):
                    record["untouched_lost"] += 1
                else:
                    tied_before, tied_after = voices_of(index.measure(measure.number), True), voices_of(after.measure(measure.number), True)
                    record["untouched_ties_changed"] += any(tied_before[key] != tied_after.get(key) for key in others)
        except UserError as error:
            record["changed"][blank(str(error))[:160]] += 1
        except Exception as error:
            record["changed"][f"CRASH {type(error).__name__}: {blank(str(error))[:120]}"] += 1
    return record


def summarise(results: dict[str, dict[str, dict]]) -> None:
    totals = {"unchanged": Counter(), "changed": Counter()}
    bars = zero = longer = lost = tied = parts = 0
    files = {"voice_longer": set(), "zero_length": set()}
    problems = []
    for name, found in results.items():
        for part, record in found.items():
            parts += 1
            if "unopenable" in record or "timeout" in record:
                problems.append((name, part, record.get("unopenable") or record["timeout"]))
                continue
            bars += record["bars"]
            for kind in totals:
                totals[kind].update(record[kind])
            for kind in files:
                if record[kind]:
                    files[kind].add(name)
            zero += record["zero_length"]
            longer += record["voice_longer"]
            lost += record["untouched_lost"]
            tied += record["untouched_ties_changed"]
    print(f"files {len(results)}, parts {parts}, bars {bars}")
    print(f"bars handed out with a voice longer than the bar: {longer} in {len(files['voice_longer'])} files")
    print(f"bars handed out with length 0: {zero} in {len(files['zero_length'])} files")
    print(f"changed bars accepted whose untouched voices lost or moved notes: {lost}")
    print(f"changed bars accepted whose untouched voices kept their notes but not their tie marks: {tied}")
    for kind, counts in totals.items():
        print(f"\n{kind}:")
        for message, count in counts.most_common():
            print(f"  {count:6d}  {message}")
    print("\nparts that could not be checked:")
    for name, part, message in problems:
        print(f"  {name} [{part}] {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--only", default="")
    parser.add_argument("--out", default="correct_corpus_check.jsonl")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--verify-untouched", action="store_true")
    parser.add_argument("--one", nargs=2, metavar=("FILE", "PART"))
    parser.add_argument("--clean", action="store_true", help="pass each score through engine.read_pdf.clean first, as production does")
    args = parser.parse_args()
    if args.one:
        record = check_part(Path(args.one[0]), args.one[1], args.verify_untouched, args.clean)
        print("RESULT " + json.dumps(record, default=dict))
        return
    queue = []
    results: dict[str, dict[str, dict]] = {}
    for path in scores():
        if args.only not in str(path):
            continue
        try:
            queue += [(path, part) for part in part_ids(read_score(path, args.clean))]
        except Exception as error:
            results[str(path)] = {"-": {"unopenable": f"{type(error).__name__}: {error}"}}
    out = Path(args.out)
    out.write_text("")
    running: list[tuple[subprocess.Popen, Path, str, float]] = []
    while queue or running:
        while queue and len(running) < args.workers:
            path, part = queue.pop(0)
            command = [sys.executable, __file__, "--one", str(path), part] + (["--verify-untouched"] if args.verify_untouched else []) + (["--clean"] if args.clean else [])
            running.append((subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True), path, part, time.time()))
        time.sleep(0.5)
        for entry in list(running):
            process, path, part, started = entry
            if process.poll() is None and time.time() - started < args.timeout:
                continue
            running.remove(entry)
            if process.poll() is None:
                process.kill()
                process.communicate()
                record = {"timeout": f"no result after {args.timeout}s"}
            else:
                lines = [line for line in process.communicate()[0].splitlines() if line.startswith("RESULT ")]
                record = json.loads(lines[-1][7:]) if lines else {"unopenable": f"exit code {process.returncode}"}
            results.setdefault(str(path), {})[part] = record
            with out.open("a") as handle:
                handle.write(json.dumps({"file": str(path), "part": part, "record": record}) + "\n")
            print(f"done {path.name} [{part}] {record.get('bars', 0)} bars in {time.time() - started:.0f}s", file=sys.stderr, flush=True)
    summarise(results)


if __name__ == "__main__":
    main()
