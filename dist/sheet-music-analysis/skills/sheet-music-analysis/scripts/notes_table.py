"""Print a beat-by-beat table of a MusicXML score's notes.

    python3 notes_table.py SCORE [--measures 1-8]
"""

import argparse
import sys
from pathlib import Path

from engine import reduce
from engine.render import ScoreError, load_toolkit
from engine.score import PositionError, ScoreIndex


def parse_measures(text: str | None) -> tuple[int | None, int | None]:
    if not text or text == "all":
        return None, None
    first, _, last = text.partition("-")
    return int(first), int(last or first)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score", type=Path, help=".mxl or .musicxml file")
    parser.add_argument("--measures", help='printed measure numbers, e.g. "1-8"; default is the whole score')
    args = parser.parse_args()
    try:
        index = ScoreIndex(load_toolkit(args.score.read_bytes()).getMEI())
        first, last = parse_measures(args.measures)
        for number in (first, last):
            if number is not None:
                index.measure(number)
    except (ScoreError, PositionError, ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(reduce.as_text(index, first, last))
    return 0


if __name__ == "__main__":
    sys.exit(main())
