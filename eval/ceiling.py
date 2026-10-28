"""How far independent expert analysts agree with each other, scored the way our own output is scored.

    .venv/bin/python -m eval.ceiling

When in Rome keeps a second analysis beside some pieces (analysis_<x>.txt). Many of those are copies or
conversions of the same source, so a pair is kept only when the two files name different sources in their
Analyst line: DCML, BPS-FH (Chen and Su), BCMH, TAVERN's two encoders, or Tymoczko's TAOM team. Corelli
is left out: its scores exist only as MuseScore files. Each analysis may number bars one off from the
score, so each is shifted by -1, 0 or +1 to fit the notes best, and a pair is kept only when both fit
(at least 0.85 of the notes inside their chords; also reported at 0.80, since chorales with many passing notes fit about 0.82 even when aligned). Pairs are scored in both directions and averaged;
results go to out/eval/ceiling.json, by style and overall, with the share of disagreement by cause.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections import Counter
from fractions import Fraction
from itertools import combinations
from pathlib import Path

from engine.render import load_toolkit
from engine.score import ScoreIndex
from engine.comparison import same_function
from eval import compare, pieces
from eval.survey import categorise

ROME = "https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/"
DCML_SCORES = "https://raw.githubusercontent.com/fosfrancesco/piano_corpora_dcml/main/scores/"
CACHE = pieces.OUT / "ceiling"
COLUMNS = ("key", "root", "chord", "chord_and_bass", "function", "idea", "full")
FIT = 0.85
KEEP = 0.75
STYLES = (("Chorales", "Bach chorales"), ("Variations_and_Grounds", "TAVERN variations"), ("Mozart", "Mozart sonatas"), ("Beethoven", "Beethoven sonatas"), ("Mazurkas", "Chopin mazurkas"))


def fetch(url: str, name: str) -> bytes:
    return pieces._download(url, CACHE / name)


def source(text: str, file: str) -> str | None:
    analyst = next((line for line in text.splitlines()[:10] if line.startswith("Analyst:")), "")
    if file == "analysis_B.txt":
        return "TAVERN b"
    if "Encoder" in text[:500] or "TAVERN" in text[:500]:
        return "TAVERN a"
    for mark, name in (("DCML", "DCML"), ("Chen", "BPS-FH"), ("Bach Chorales Melody-Harmony", "BCMH")):
        if mark in analyst:
            return name
    return "TAOM" if analyst or file == "analysis_DT.txt" else None


def score_url(folder: str, paths: set[str]) -> str | None:
    if f"{folder}/score.mxl" in paths:
        return ROME + urllib.parse.quote(folder + "/score.mxl")
    if f"{folder}/remote.json" not in paths:
        return None
    remote = json.loads(fetch(ROME + urllib.parse.quote(folder + "/remote.json"), folder.replace("/", "__") + "__remote.json"))
    if remote.get("remote_score_music21"):
        return "corpus:" + remote["remote_score_music21"]
    if "Beethoven" in folder and remote.get("sonata_number"):
        return f"{DCML_SCORES}beethoven_piano_sonatas/{remote['sonata_number']:02d}-{remote['movement']}.musicxml"
    if "Mazurkas" in folder and remote.get("remote_score_mscx"):
        return f"{DCML_SCORES}chopin_mazurkas/{Path(remote['remote_score_mscx']).stem}.musicxml"
    if str(remote.get("remote_score_krn", "")).endswith(".xml"):
        return remote["remote_score_krn"]
    return None


def candidates(paths: set[str]) -> list[tuple[str, list[str], str]]:
    by: dict[str, set[str]] = {}
    for path in paths:
        match = re.match(r"(Corpus/.*)/(analysis(?:_[A-Za-z]+)?\.txt)$", path)
        if match:
            by.setdefault(match[1], set()).add(match[2])
    found = []
    for folder, files in sorted(by.items()):
        if len(files) < 2 or "Corelli" in folder:
            continue
        url = score_url(folder, paths)
        if url:
            found.append((folder, sorted(files), url))
    return found


def aligned(text: str, timeline: compare.Timeline) -> tuple[float, list[compare.Label]]:
    labels = compare.from_romantext(text)
    best = (0.0, labels)
    for shift in (0, 1, -1):
        moved = [compare.Label(label.measure + shift, label.beat, label.key, label.figure) for label in labels]
        fit = timeline.fit(timeline.spans(moved)[0])
        if fit > best[0]:
            best = (fit, moved)
    return best


def causes(a: list[compare.Label], b: list[compare.Label], timeline: compare.Timeline) -> Counter:
    spans_a, spans_b = timeline.spans(a)[0], timeline.spans(b)[0]
    cuts = sorted({point for start, end, _ in spans_a + spans_b for point in (start, end)})
    at = lambda spans, time: next((chord for start, end, chord in spans if start <= time < end), None)
    found = Counter()
    for start, end in zip(cuts, cuts[1:]):
        r, h = at(spans_a, start), at(spans_b, start)
        if r is None:
            continue
        found["labelled"] += float(end - start)
        kind = categorise(r, h)
        if kind and kind in ("seventh", "quality", "related chord") and h and same_function(r, h):
            kind = "cadential 6/4 or seventh, same function"
        if kind:
            found[kind] += float(end - start)
    return found


def style(folder: str) -> str:
    return next((name for mark, name in STYLES if mark in folder), "other")


def main() -> None:
    paths = set(pieces.rome_tree())
    results = []
    for folder, files, url in candidates(paths):
        name = folder.removeprefix("Corpus/")
        try:
            data = fetch(url, name.replace("/", "__") + Path(url).suffix)
            if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
                data = re.sub(r"encoding=['\"]UTF-16['\"]", "encoding='UTF-8'", data.decode("utf-16"), flags=re.I).encode("utf-8")
            index = ScoreIndex(load_toolkit(pieces.without_harmony(data)).getMEI())
            texts = {f: fetch(ROME + urllib.parse.quote(f"{folder}/{f}"), name.replace("/", "__") + "__" + f).decode("utf-8", "ignore") for f in files}
        except Exception as error:
            print(f"{name:60s} skipped: {type(error).__name__}: {str(error)[:80]}")
            continue
        sources = {f: source(text, f) for f, text in texts.items()}
        first = {s: f for f, s in reversed(sources.items())}
        timeline = compare.Timeline(index)
        for a, b in combinations([f for f in files if first.get(sources[f]) == f], 2):
            if None in (sources[a], sources[b]) or sources[a] == sources[b] or texts[a].split("\n", 3)[-1] == texts[b].split("\n", 3)[-1]:
                continue
            pair = f"{sources[a]} v {sources[b]}"
            try:
                (fit_a, labels_a), (fit_b, labels_b) = aligned(texts[a], timeline), aligned(texts[b], timeline)
                if min(fit_a, fit_b) < KEEP:
                    print(f"{name:60s} {pair}: dropped, fit {fit_a:.2f}/{fit_b:.2f}")
                    continue
                forward, backward = compare.compare(labels_a, labels_b, index), compare.compare(labels_b, labels_a, index)
            except Exception as error:
                print(f"{name:60s} {pair}: dropped, {str(error)[:70]}")
                continue
            both = {c: (forward[c] + backward[c]) / 2 for c in COLUMNS}
            lost = causes(labels_a, labels_b, timeline) + causes(labels_b, labels_a, timeline)
            results.append({"piece": name, "style": style(folder), "pair": pair, "fit": round(min(fit_a, fit_b), 3), "bars": len(index.measures), **{c: round(v, 3) for c, v in both.items()}, "causes": dict(lost)})
            print(f"{name:60s} {pair}: " + "  ".join(f"{c[:5]} {both[c]:.2f}" for c in COLUMNS))
    summary = {}
    for group in sorted({r["style"] for r in results}) + ["all", "all, fit 0.80+"]:
        rows = [r for r in results if r["fit"] >= (0.80 if group == "all, fit 0.80+" else FIT) and group in ("all", "all, fit 0.80+", r["style"])]
        weight = sum(r["bars"] for r in rows)
        lost = sum((Counter(r["causes"]) for r in rows), Counter())
        labelled = lost.pop("labelled", 0) or 1
        summary[group] = {"pairs": len(rows), "bars": weight, **{c: round(sum(r[c] * r["bars"] for r in rows) / weight, 3) for c in COLUMNS}, "lost": {k: round(v / labelled, 3) for k, v in lost.most_common()}}
    print(f"\n{'':20s} pairs   bars  " + "  ".join(f"{c[:9]:>9s}" for c in COLUMNS))
    for group, row in summary.items():
        print(f"{group:20s} {row['pairs']:5d} {row['bars']:6d}  " + "  ".join(f"{row[c]:9.3f}" for c in COLUMNS))
    print("\nShare of the music lost, by cause (all pairs): " + ", ".join(f"{k} {v:.3f}" for k, v in summary["all"]["lost"].items()))
    (pieces.OUT / "ceiling.json").write_text(json.dumps({"summary": summary, "pairs": results}, indent=1))


if __name__ == "__main__":
    main()
