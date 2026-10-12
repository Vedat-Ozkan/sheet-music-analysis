"""Print the compact note list that the analysis connector's draft tool reads.

    python3 model_notes.py SCORE [--measures 1-8] [--student-analysis "m1 I, m2 V6 ..." | score]

Pass the output, unchanged, as the `notes` argument of the connector's draft_from_notes tool.
With --student-analysis the user's own Roman numerals are checked against the score first (the word "score"
reads the numerals written into the file). If they are unclear, the script prints a question for the user and
stops; otherwise it also prints a line "student_analysis: ..." on stderr, whose text goes, unchanged, into the
tool's `student_analysis` argument.
"""

import argparse
import sys
from pathlib import Path

from engine import check_analysis, notes
from engine.render import ScoreError, load_toolkit
from engine.score import PositionError, ScoreIndex


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score", type=Path, help=".mxl or .musicxml file")
    parser.add_argument("--measures", help='printed measure numbers, e.g. "1-8"; default is the whole score')
    parser.add_argument("--student-analysis", help='the user\'s Roman numerals to check, or "score" for those written in the file')
    args = parser.parse_args()
    first = last = None
    try:
        if args.measures and args.measures != "all":
            start, _, end = args.measures.partition("-")
            first, last = int(start), int(end or start)
        score = args.score.read_bytes()
        index = ScoreIndex(load_toolkit(score).getMEI())
        student = check_analysis.student_labels(args.student_analysis, score, index) if args.student_analysis else None
        print(notes.encode(index, first, last))
        if student:
            print(f"student_analysis: {check_analysis.as_typed(student)}", file=sys.stderr)
    except check_analysis.ClarificationNeeded as error:
        print(f"Ask the user: {error.question}", file=sys.stderr)
        return 1
    except (ScoreError, PositionError, notes.NotesError, ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
