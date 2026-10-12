"""Correct bars of a reading and redraw only the changed bars for confirmation.

    python3 correct_score.py SCORE.musicxml BARS.txt --out-dir DIR [--part P1] [--name corrected]

BARS.txt uses the engine's N1 format; each supplied voice must fill its bar.
"""

import argparse
import sys
from pathlib import Path

import verovio

try:
    from engine.correct import CorrectionError, replace_bars, review_correction
except ModuleNotFoundError as error:
    if error.name != "music21":
        raise
    sys.exit("Bar correction needs music21. Run python3 -m pip install music21, then retry.")
from engine.render import ScoreError
from engine.score import PositionError

verovio.enableLog(False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score", type=Path)
    parser.add_argument("bars", type=Path, help="replacement bars in N1 format")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--part", help="part id, required for scores with multiple parts")
    parser.add_argument("--name", default="corrected", help="file name without extension")
    args = parser.parse_args()

    try:
        before = args.score.read_bytes()
        after = replace_bars(before, args.bars.read_text(), part=args.part)
        review = review_correction(before, after, part=args.part)
    except (CorrectionError, ScoreError, PositionError, OSError) as error:
        print(f"Fix the replacement bars and run again: {error}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    score = args.out_dir / f"{args.name}.musicxml"
    score.write_bytes(after)
    print(score)
    count = sum(engraving.page_count for engraving in review.engravings)
    number = 0
    for engraving in review.engravings:
        for page in range(1, engraving.page_count + 1):
            number += 1
            suffix = "" if count == 1 else f"-p{number}"
            path = args.out_dir / f"{args.name}{suffix}.png"
            path.write_bytes(engraving.png(page, width=1600))
            print(path)
    print("\n".join(review.notes.values()) or "No bars changed.")
    print("Show the user every PNG and the note; ask them to confirm against their copy. "
          "Analyse the corrected MusicXML only after they confirm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
