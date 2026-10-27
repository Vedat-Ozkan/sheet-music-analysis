"""Run the draft model on the evaluation pieces and score it against the human chord labels.

    .venv/bin/python -m eval.run [--set core|heldout] [--only ID] [--reviewed FOLDER]

Each piece is read, drafted by the model (cached in out/eval/drafts/) and, where a human
chord-by-chord reading exists, compared with it. `--reviewed` also scores annotation lists
written after review, one `<id>.json` per piece in that folder. The table goes to
out/eval/report.json.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from engine import draft, notes
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import compare, pieces

RAW = pieces.OUT / "raw"
DRAFTS = pieces.OUT / "drafts"
COLUMNS = ("key", "root", "chord", "chord_and_bass", "full", "reference_fit", "reading_fit")


def cached_draft(piece: pieces.Piece, index: ScoreIndex) -> draft.Draft:
    path = RAW / f"{piece.id}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(draft.run_analysisgnn(notes.encode(index).encode(), "notes")))
    drafted = draft.build(json.loads(path.read_text()), index)
    DRAFTS.mkdir(parents=True, exist_ok=True)
    (DRAFTS / f"{piece.id}.txt").write_text(draft.as_text(drafted))
    return drafted


def run(piece: pieces.Piece, reviewed: Path | None) -> dict:
    result: dict = {"title": piece.title}
    try:
        index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
        numbers = [measure.number for measure in index.measures]
        result.update(measures=len(numbers), first=numbers[0], last=numbers[-1], meter=index.meter)
        started = time.time()
        drafted = cached_draft(piece, index)
        result.update(draft_seconds=round(time.time() - started, 1), draft_chords=len(drafted.chords), draft_cadences=len(drafted.cadences))
        reference = [
            compare.Label(label.measure + piece.bar_offset, label.beat, label.key, label.figure)
            for label in compare.from_romantext(pieces.labels(piece) or "")
        ]
        if reference:
            path = reviewed / f"{piece.id}.json" if reviewed else None
            review = json.loads(path.read_text()) if path and path.exists() else None
            bars = [tuple(passage) for passage in review["passages"]] if review and "passages" in review else None
            result["draft"] = compare.compare(reference, compare.from_draft(drafted), index, bars)
            if review:
                result["reviewed"] = compare.compare(reference, compare.from_annotations(review), index, bars)
                if bars:
                    result["scored_bars"] = bars
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {str(error)[:300]}"
    return result


def totals(report: dict, stage: str, column: str = "full", resamples: int = 2000) -> tuple[float, float, float] | None:
    weight = lambda result: sum(last - first + 1 for first, last in result["scored_bars"]) if "scored_bars" in result else result["measures"]
    rows = [(weight(result), result[stage][column]) for result in report.values() if stage in result and result[stage][column] is not None]
    if not rows:
        return None
    mean = lambda sample: sum(w * v for w, v in sample) / sum(w for w, _ in sample)
    generator = random.Random(0)
    spread = sorted(mean(generator.choices(rows, k=len(rows))) for _ in range(resamples))
    return mean(rows), spread[int(0.025 * resamples)], spread[int(0.975 * resamples)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", default="core", choices=sorted(pieces.SETS), help="which pieces: core (the 25 chosen pieces) or heldout (labelled pieces the draft model was not trained on)")
    parser.add_argument("--only", action="append", help="run only this piece (repeatable)")
    parser.add_argument("--reviewed", type=Path, help="folder of reviewed annotation lists, <id>.json")
    args = parser.parse_args()
    path = pieces.OUT / ("report.json" if args.set == "core" else f"report-{args.set}.json")
    report = json.loads(path.read_text()) if path.exists() and args.only else {}
    print(f"{'piece':26s} bars  " + "  ".join(f"{column[:9]:>9s}" for column in COLUMNS))
    for piece in [pieces.BY_ID[name] for name in args.only] if args.only else pieces.SETS[args.set]:
        report[piece.id] = result = run(piece, args.reviewed)
        for stage in ("draft", "reviewed"):
            if stage in result:
                print(f"{piece.id:26s} {result['measures']:4d}  " + "  ".join(f"{result[stage][column]:9.2f}" for column in COLUMNS) + f"  {stage}")
        if "draft" not in result:
            print(f"{piece.id:26s} {result.get('measures', 0):4d}  " + (result.get("error") or f"no label file; {result['draft_chords']} chords drafted"))
    pieces.OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1))
    for stage in ("draft", "reviewed"):
        for column in ("key", "full"):
            if found := totals(report, stage, column):
                print(f"{stage:8s} {column:4s} {found[0]:.3f}  (95% interval {found[1]:.3f} to {found[2]:.3f}, {sum(stage in r for r in report.values())} pieces)")


if __name__ == "__main__":
    main()
