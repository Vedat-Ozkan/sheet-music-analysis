"""Draw an annotation list on the engraved score and save a PNG and a PDF.

    python3 render_analysis.py SCORE ANNOTATIONS.json --out-dir DIR [--measures 1-8] [--view all] [--name analysis]
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from engine.annotate import AnnotationError, render
from engine.annotations import AnnotationList
from engine.render import ScoreError
from engine.score import PositionError

VIEWS = ("all", "harmony", "voice_leading", "form")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score", type=Path, help=".mxl or .musicxml file")
    parser.add_argument("annotations", type=Path, help="annotation list as JSON")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--measures", help='printed measure numbers, e.g. "1-8"; default is the whole score')
    parser.add_argument("--view", choices=VIEWS, default="all")
    parser.add_argument("--name", default="analysis", help="file name without extension")
    args = parser.parse_args()

    try:
        annotations = AnnotationList.model_validate_json(args.annotations.read_text())
    except ValidationError as error:
        print("The annotation list does not match the format. Fix these and run again:", file=sys.stderr)
        for problem in error.errors():
            print(f"  {'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}", file=sys.stderr)
        return 1

    measures = None
    if args.measures and args.measures != "all":
        first, _, last = args.measures.partition("-")
        measures = (int(first), int(last or first))
    try:
        engraving = render(args.score.read_bytes(), annotations, measures=measures, view=args.view)
    except AnnotationError as error:
        print("Some annotations point at places that are not in the score. Fix these and run again:", file=sys.stderr)
        for problem in error.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    except (ScoreError, PositionError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for page in range(1, engraving.page_count + 1):
        suffix = "" if engraving.page_count == 1 else f"-p{page}"
        path = args.out_dir / f"{args.name}{suffix}.png"
        path.write_bytes(engraving.png(page, width=1600))
        print(path)
    pdf = args.out_dir / f"{args.name}.pdf"
    pdf.write_bytes(engraving.pdf())
    print(pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
