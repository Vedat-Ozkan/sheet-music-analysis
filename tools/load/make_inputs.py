from __future__ import annotations

import json
import sys
from pathlib import Path

from engine import notes
from engine.render import load_toolkit
from engine.score import ScoreIndex

ROOT = Path(__file__).resolve().parent.parent.parent
SCORES = ["part_writing_bwv336.musicxml", "part_writing_bwv418.musicxml", "triplet_hensel.musicxml",
          "export-brahms-118-2.musicxml", "chopin_nocturne_op9_no2.mxl", "export-mozart-k458.musicxml"]


def main() -> None:
    out = Path(sys.argv[1])
    lists = []
    for name in SCORES:
        index = ScoreIndex(load_toolkit((ROOT / "tests/data" / name).read_bytes()).getMEI())
        lists.append({"score": name, "notes": notes.encode(index)})
    annotations = json.loads((ROOT / "examples/chopin_op9_no2_m1-8.json").read_text())
    out.write_text(json.dumps({"note_lists": lists, "render": {"annotations": annotations, "measure_range": "1-8"}}))
    for item in lists:
        print(f"{item['score']}: {len(item['notes'])} characters")


if __name__ == "__main__":
    main()
