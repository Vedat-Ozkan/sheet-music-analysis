"""How far two human experts agree with each other, measured the way eval/run.py measures us.

    .venv/bin/python -m eval.ceiling

When in Rome holds independent expert analyses of the same music: Beethoven sonata movements analysed by
two of three separate teams (DCML, Tymoczko's TAOM, BPS-FH), and the TAVERN variation sets, analysed by two
annotators by design. Each pair is scored in both directions with eval/compare.py. A pair is used only if
both analyses fit the score (at least 0.85 of the notes in their chords), so that a bar-numbering mismatch
is not counted as disagreement. Results go to out/eval/ceiling.json.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from itertools import combinations
from pathlib import Path

from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import compare, pieces

ROME = "https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/"
DCML_SCORES = "https://raw.githubusercontent.com/fosfrancesco/piano_corpora_dcml/main/scores/beethoven_piano_sonatas/"
CACHE = pieces.OUT / "ceiling"
COLUMNS = ("key", "root", "chord", "chord_and_bass", "full")
FIT = 0.85
INCLUDE_TAVERN = False  # TAVERN scores crash Verovio (see the engineering log); Beethoven pairs only for now


def fetch(url: str, name: str) -> bytes:
    return pieces._download(url, CACHE / name)


def folders(paths: list[str]) -> list[tuple[str, list[str], str]]:
    """(folder, analysis files to pair, score url) for every independent pair we can score."""
    by: dict[str, set[str]] = {}
    for path in paths:
        match = re.match(r"(Corpus/.*)/(analysis(?:_[A-Z]+)?\.txt)$", path)
        if match:
            by.setdefault(match[1], set()).add(match[2])
    found = []
    for folder, files in sorted(by.items()):
        remote = json.loads(fetch(ROME + urllib.parse.quote(folder + "/remote.json"), folder.replace("/", "__") + "__remote.json") or b"{}") if f"{folder}/remote.json" in paths else {}
        if "Piano_Sonatas/Beethoven" in folder:
            external = sorted(f for f in files if f in ("analysis_DCML.txt", "analysis_DT.txt", "analysis_BPS.txt"))
            if len(external) >= 2 and remote.get("sonata_number"):
                found.append((folder, external, f"{DCML_SCORES}{remote['sonata_number']:02d}-{remote['movement']}.musicxml"))
        elif "analysis_B.txt" in files and remote.get("remote_score_krn") and INCLUDE_TAVERN:
            found.append((folder, ["analysis.txt", "analysis_B.txt"], remote["remote_score_krn"]))
    return found


def main() -> None:
    paths = pieces.rome_tree()
    results, totals, weight = [], {name: 0.0 for name in COLUMNS}, 0.0
    for folder, files, score_url in folders(paths):
        name = folder.removeprefix("Corpus/")
        try:
            index = ScoreIndex(load_toolkit(pieces.without_harmony(fetch(score_url, name.replace("/", "__") + Path(score_url).suffix))).getMEI())
            readings = {f: compare.from_romantext(fetch(ROME + urllib.parse.quote(f"{folder}/{f}"), name.replace("/", "__") + "__" + f).decode("utf-8", "ignore")) for f in files}
        except Exception as error:  # a score or analysis that will not load is skipped, and said so
            print(f"{name:55s} skipped: {type(error).__name__}: {str(error)[:80]}")
            continue
        for a, b in combinations(files, 2):
            try:
                forward, backward = compare.compare(readings[a], readings[b], index), compare.compare(readings[b], readings[a], index)
            except Exception as error:  # an analysis naming a beat the score's bar lacks: misaligned, so dropped
                print(f"{name:55s} {a[9:-4] or 'A'} v {b[9:-4] or 'B'}: dropped, {str(error)[:70]}")
                continue
            fits = (forward["reference_fit"], backward["reference_fit"])
            if min(fits) < FIT:
                print(f"{name:55s} {a[9:-4] or 'A'} v {b[9:-4] or 'B'}: dropped, fit {fits[0]:.2f}/{fits[1]:.2f}")
                continue
            both = {c: (forward[c] + backward[c]) / 2 for c in COLUMNS}
            bars = len(index.measures)
            results.append({"piece": name, "pair": [a, b], "bars": bars, **{c: round(v, 3) for c, v in both.items()}})
            for c in COLUMNS:
                totals[c] += both[c] * bars
            weight += bars
            print(f"{name:55s} {a[9:-4] or 'A'} v {b[9:-4] or 'B'}: " + "  ".join(f"{c[:5]} {both[c]:.2f}" for c in COLUMNS))
    print(f"\n{len(results)} pairs, {weight:.0f} bars; human against human, weighted by length:")
    print("  " + "  ".join(f"{c} {totals[c] / weight:.3f}" for c in COLUMNS))
    (pieces.OUT / "ceiling.json").write_text(json.dumps({"pairs": results, "weighted": {c: round(totals[c] / weight, 3) for c in COLUMNS}}, indent=1))


if __name__ == "__main__":
    main()
