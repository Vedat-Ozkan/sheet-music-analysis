"""Print the compact note list that the analysis connector's draft tool reads.

    python3 model_notes.py SCORE [--measures 1-8]

Pass the output, unchanged, as the `notes` argument of the connector's draft_from_notes tool.
"""

import argparse
import sys
from pathlib import Path

from engine import notes
from engine.render import ScoreError, load_toolkit
from engine.score import PositionError, ScoreIndex


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score", type=Path, help=".mxl or .musicxml file")
    parser.add_argument("--measures", help='printed measure numbers, e.g. "1-8"; default is the whole score')
    args = parser.parse_args()
    first = last = None
    try:
        if args.measures and args.measures != "all":
            start, _, end = args.measures.partition("-")
            first, last = int(start), int(end or start)
        index = ScoreIndex(load_toolkit(args.score.read_bytes()).getMEI())
        print(notes.encode(index, first, last))
    except (ScoreError, PositionError, notes.NotesError, ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
