"""Run the draft model on the evaluation pieces and score it against the human chord labels.

    .venv/bin/python -m eval.run [--only ID] [--reviewed FOLDER]

Each piece is read, drafted by the model (cached in out/eval/drafts/) and, where a human
chord-by-chord reading exists, compared with it. `--reviewed` also scores annotation lists
written after review, one `<id>.json` per piece in that folder. The table goes to
out/eval/report.json.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from engine import draft, notes
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import compare, pieces

RAW = pieces.OUT / "raw"  # the model's output, kept so that changes to engine/draft.py need no new model run
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
            result["draft"] = compare.compare(reference, compare.from_draft(drafted), index)
            path = reviewed / f"{piece.id}.json" if reviewed else None
            if path and path.exists():
                result["reviewed"] = compare.compare(reference, compare.from_annotations(json.loads(path.read_text())), index)
    except Exception as error:  # one broken file should not stop the rest
        result["error"] = f"{type(error).__name__}: {str(error)[:300]}"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", help="run only this piece (repeatable)")
    parser.add_argument("--reviewed", type=Path, help="folder of reviewed annotation lists, <id>.json")
    args = parser.parse_args()
    path = pieces.OUT / "report.json"
    report = json.loads(path.read_text()) if path.exists() and args.only else {}
    print(f"{'piece':26s} bars  " + "  ".join(f"{column[:9]:>9s}" for column in COLUMNS))
    for piece in [pieces.BY_ID[name] for name in args.only] if args.only else pieces.PIECES:
        report[piece.id] = result = run(piece, args.reviewed)
        for stage in ("draft", "reviewed"):
            if stage in result:
                print(f"{piece.id:26s} {result['measures']:4d}  " + "  ".join(f"{result[stage][column]:9.2f}" for column in COLUMNS) + f"  {stage}")
        if "draft" not in result:
            print(f"{piece.id:26s} {result.get('measures', 0):4d}  " + (result.get("error") or f"no label file; {result['draft_chords']} chords drafted"))
    pieces.OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
