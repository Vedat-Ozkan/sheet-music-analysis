from __future__ import annotations

import argparse
import json
from collections import Counter
from fractions import Fraction
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DATA = HERE / "tests/data"
SKIP = {"verovio-crashes"}
GRID = Fraction(1, 32)
USAGE = """Corpus check for the piano version: draws several bar ranges of every score in tests/data with piano=True and counts
ranges that fail (a refusal is not a failure), notes or rests of a length no musician writes, and bars whose two hands
differ in length. A length is unwritable when it has 3+ dots or no note value, uses a tuplet ratio the source never uses
(3:2 always allowed), or sits in a run of tuplet notes that does not start and end on the 1/32-quarter grid. A fault the
source bar also has is counted apart.

    PYTHONPATH=. .venv/bin/python tools/piano_check.py --out piano.json
    PYTHONPATH=. .venv/bin/python tools/piano_check.py --out after.json --compare before.json"""


def scores() -> list[Path]:
    return sorted(p for p in DATA.rglob("*") if p.suffix in (".musicxml", ".mxl", ".xml") and not SKIP & set(p.parts))


def ranges(path: Path) -> list[tuple[int, int]]:
    from music21 import converter, stream
    bars = list(converter.parse(path).parts[0].getElementsByClass(stream.Measure))
    numbers = [bar.number for bar in bars]
    n = len(numbers)
    found = [(numbers[0], numbers[min(3, n - 1)]), (numbers[n // 2], numbers[min(n // 2 + 3, n - 1)]), (numbers[max(n - 4, 0)], numbers[-1])]
    change = next((bar.number for i, bar in enumerate(bars) if i > 0 and (bar.timeSignature or bar.keySignature)), None)
    if change:
        found.append((change, min(change + 3, numbers[-1])))
    return list(dict.fromkeys(found))


def faults(score, allowed: set[tuple[int, int]]) -> dict[str, list[str]]:
    from music21 import stream
    found: dict[str, set[str]] = {}
    lengths: dict[tuple[int, int], list[Fraction]] = {}
    for part in score.parts:
        for position, bar in enumerate(part.getElementsByClass(stream.Measure)):
            lengths.setdefault((position, bar.number), []).append(Fraction(bar.duration.quarterLength))
            for voice in bar.voices or [bar]:
                run = []
                for element in [*voice.notesAndRests, None]:
                    written = element.duration if element is not None else None
                    if written is not None and not written.isGrace:
                        whole_bar_rest = element.isRest and element.fullMeasure in (True, "always")
                        if (written.type in ("inexpressible", "complex", "zero") and not whole_bar_rest) or written.dots > 2:
                            found.setdefault(str(bar.number), set()).add("unnamed")
                        if any((t.numberNotesActual, t.numberNotesNormal) not in allowed for t in written.tuplets):
                            found.setdefault(str(bar.number), set()).add("tuplet")
                    kind = (written.tuplets[0].numberNotesActual, written.tuplets[0].numberNotesNormal) if written is not None and written.tuplets else None
                    if run and kind != run[0][0]:
                        start, end = Fraction(run[0][1].offset), Fraction(run[-1][1].offset) + Fraction(run[-1][1].quarterLength)
                        if start % GRID or end % GRID:
                            found.setdefault(str(bar.number), set()).add("open")
                        run = []
                    if kind is not None:
                        run.append((kind, element))
    for (_, number), seen in lengths.items():
        if len(set(seen)) > 1:
            found.setdefault(str(number), set()).add("hands")
    return {bar: sorted(kinds) for bar, kinds in found.items()}


def check(job: tuple[str, int, int]) -> tuple[str, dict]:
    path, first, last = job
    from music21 import converter
    from engine import annotate, piano
    from engine.annotations import AnnotationList
    written = []
    reduce = piano.reduce
    piano.reduce = lambda *args, **kwargs: written.append(reduce(*args, **kwargs)) or written[-1]
    result: dict = {}
    try:
        annotate.render(Path(path).read_bytes(), AnnotationList(annotations=[]), (first, last), piano=True)
    except Exception as error:
        if type(error).__name__ == "PianoError":
            result["refused"] = str(error)
        else:
            result["error"] = f"{type(error).__name__}: {str(error)[:150]}"
    if written:
        source = converter.parse(path)
        allowed = {(t.numberNotesActual, t.numberNotesNormal) for e in source.recurse().notesAndRests for t in e.duration.tuplets} | {(3, 2)}
        ours = faults(converter.parse(written[0], format="musicxml"), allowed)
        theirs = faults(source.measures(first, last), allowed)
        result["faults"] = {bar: [k for k in kinds if k not in theirs.get(bar, [])] for bar, kinds in ours.items()}
        result["faults"] = {bar: kinds for bar, kinds in result["faults"].items() if kinds}
        result["also_in_source"] = {bar: [k for k in kinds if k in theirs.get(bar, [])] for bar, kinds in ours.items() if set(kinds) & set(theirs.get(bar, []))}
    return f"{Path(path).relative_to(DATA)}:{first}-{last}", result


def summary(results: dict) -> dict:
    unwritable = lambda kinds: set(kinds) & {"unnamed", "tuplet", "open"}
    return {
        "ranges": len(results),
        "failed": dict(Counter(r["error"].split(":")[0] for r in results.values() if "error" in r)),
        "refused": dict(Counter(r["refused"][:60] for r in results.values() if "refused" in r)),
        "unwritable ranges": sum(any(unwritable(k) for k in r.get("faults", {}).values()) for r in results.values()),
        "unwritable bars": sum(bool(unwritable(k)) for r in results.values() for k in r.get("faults", {}).values()),
        "also in source, bars": sum(bool(unwritable(k)) for r in results.values() for k in r.get("also_in_source", {}).values()),
        "hands differ, bars": sum("hands" in k for r in results.values() for k in r.get("faults", {}).values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=USAGE, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compare", type=Path, help="an earlier --out file; prints every range whose result differs")
    args = parser.parse_args()
    jobs = [(str(path), first, last) for path in scores() for first, last in ranges(path)]
    with Pool(8, maxtasksperchild=1) as pool:
        results = dict(sorted(pool.imap_unordered(check, jobs)))
    args.out.write_text(json.dumps(results, indent=1))
    print(json.dumps(summary(results), indent=1))
    if args.compare:
        before = json.loads(args.compare.read_text())
        print("before:", json.dumps(summary(before)))
        for name in sorted(set(before) | set(results)):
            if before.get(name) != results.get(name):
                print(f"{name}\n  before: {before.get(name)}\n  after:  {results.get(name)}")


if __name__ == "__main__":
    main()
