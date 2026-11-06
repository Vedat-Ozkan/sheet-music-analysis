"""List PDF readings that came back much shorter than their reference score.

    PYTHONPATH=. .venv/bin/python tools/reading_coverage.py READINGS --data-root spike/omr SET [SET ...]

READINGS holds one SET--STEM.musicxml per PDF, as spike/omr/speed/variants.py writes them.
A reading under MIN_SHARE of the reference's bars has lost music whichever way it was lost,
even with outcome "done". The exit code is 1 when any reading is listed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import warnings

MIN_SHARE = 0.8


def bars(path: Path) -> int:
    from engine.read_pdf import _archived_score
    import xml.etree.ElementTree as ET

    data = path.read_bytes()
    root = _archived_score(data) if data[:2] == b"PK" else ET.fromstring(data)
    return max(len(part.findall("measure")) for part in root.findall("part"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readings", type=Path)
    parser.add_argument("sets", nargs="+")
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    warnings.filterwarnings("ignore")
    checked, short = 0, []
    for name in args.sets:
        manifest = json.loads((args.data_root / name / "manifest.json").read_text())
        for entry in manifest["pdfs"]:
            stem = Path(entry["pdf"]).stem
            reading = args.readings / f"{name}--{stem}.musicxml"
            truth = args.data_root / name / manifest["pieces"][entry["piece"]]["truth"]
            read, expected = bars(reading), bars(truth)
            checked += 1
            if read < MIN_SHARE * expected:
                short.append(f"{name}/{stem}: {read} of {expected} bars")
    print(f"{checked} readings, {len(short)} under {MIN_SHARE:.0%} of the reference's bars")
    print("\n".join(short))
    return 1 if short else 0


if __name__ == "__main__":
    sys.exit(main())
