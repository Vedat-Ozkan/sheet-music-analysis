"""Draw an annotation list on the engraved score and save PNG, PDF and annotated MusicXML files.

    python3 render_analysis.py SCORE ANNOTATIONS.json --out-dir DIR [--measures 1-8] [--view all] [--name analysis] [--piano]
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from engine.annotate import AnnotationError, render
from engine.annotations import AnnotationList
from engine.export import export_midi, export_musicxml, export_romantext

VIEWS = ("all", "harmony", "voice_leading", "form")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score", type=Path, help=".mxl or .musicxml file")
    parser.add_argument("annotations", type=Path, help="annotation list as JSON")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--measures", help='printed measure numbers, e.g. "1-8"; default is the whole score')
    parser.add_argument("--view", choices=VIEWS, default="all")
    parser.add_argument("--style", choices=("current", "abrsm", "figured_bass"), help="override the annotation list's notation style")
    parser.add_argument("--name", default="analysis", help="file name without extension")
    parser.add_argument("--piano", action="store_true", help="draw the passage as a two-staff piano reduction")
    args = parser.parse_args()

    try:
        annotations = AnnotationList.model_validate_json(args.annotations.read_text())
    except ValidationError as error:
        print("The annotation list does not match the format. Fix these and run again:", file=sys.stderr)
        for problem in error.errors():
            print(f"  {'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}", file=sys.stderr)
        return 1

    if args.style:
        annotations = annotations.model_copy(update={"style": args.style})

    measures = None
    if args.measures and args.measures != "all":
        first, _, last = args.measures.partition("-")
        measures = (int(first), int(last or first))
    try:
        score = args.score.read_bytes()
        engraving = render(score, annotations, measures=measures, view=args.view, piano=args.piano)
    except AnnotationError as error:
        print("Some annotations point at places that are not in the score. Fix these and run again:", file=sys.stderr)
        for problem in error.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    xml = args.out_dir / f"{args.name}.musicxml"
    if xml.resolve() == args.score.resolve():
        # Never delete or overwrite the user's own score, which may share the default output name.
        xml = args.out_dir / f"{args.name}-annotated.musicxml"
    # Reused output names must not pair new pages with a previous analysis's export.
    xml.unlink(missing_ok=True)
    for page in range(1, engraving.page_count + 1):
        suffix = "" if engraving.page_count == 1 else f"-p{page}"
        path = args.out_dir / f"{args.name}{suffix}.png"
        path.write_bytes(engraving.png(page, width=1600))
        print(path)
    pdf = args.out_dir / f"{args.name}.pdf"
    pdf.write_bytes(engraving.pdf())
    print(pdf)
    # Optional extras: a failure in one must not discard the pages or the other files.
    for suffix, make in (("-worksheet.pdf", lambda: render(score, AnnotationList(annotations=[]), measures=measures, piano=args.piano).pdf()),
                         (".mid", lambda: export_midi(score, measures)),
                         (".rntxt", lambda: export_romantext(score, annotations.model_dump(), measures))):
        path = args.out_dir / f"{args.name}{suffix}"
        path.unlink(missing_ok=True)
        try:
            data = make()
        except Exception as error:
            print(f"{path.name} unavailable for this score ({error}).", file=sys.stderr)
            continue
        if data:
            path.write_bytes(data)
            print(path)
    # Optional export failures must not discard an engraving Verovio already accepted.
    try:
        musicxml = export_musicxml(score, annotations.model_dump())
    except Exception as error:
        print(f"MusicXML export unavailable for this score ({error}). PNG and PDF are available.", file=sys.stderr)
        return 0
    xml.write_bytes(musicxml)
    print(xml)
    return 0


if __name__ == "__main__":
    sys.exit(main())
