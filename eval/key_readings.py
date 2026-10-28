"""How often the rules in engine/key_readings.py flag places where another expert names a different key.

    .venv/bin/python -m eval.key_readings

Each pair of independent expert analyses (as in eval/ceiling.py, fit 0.85 or more) is used both ways: the
rules run on one expert's analysis, and a flagged span counts as a hit when the other expert names a
different key over at least a quarter of it. Random spans of the same lengths in the same piece give the
chance rate. The pairs are split in two by piece name (alternate pieces), so a rule tuned on one half can be
checked on the other.
"""

from __future__ import annotations

import random
import re
import urllib.parse
from fractions import Fraction
from itertools import combinations
from pathlib import Path

from engine.key_readings import alternatives
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import ceiling, compare, pieces

HIT = 0.25


def key_disagreements(a: list, b: list) -> list[tuple[Fraction, Fraction, bool]]:
    cuts = sorted({p for spans in (a, b) for x, y, _ in spans for p in (x, y)})
    at = lambda spans, time: next((chord for x, y, chord in spans if x <= time < y), None)
    found = []
    for x, y in zip(cuts, cuts[1:]):
        r, h = at(a, x), at(b, x)
        if r is not None and h is not None:
            found.append((x, y, r.tonic != h.tonic))
    return found


def share(found: list, start: Fraction, end: Fraction) -> float:
    parts = [(max(x, start), min(y, end), differ) for x, y, differ in found if x < end and y > start]
    total = sum((y - x for x, y, _ in parts), Fraction(0))
    return float(sum((y - x for x, y, differ in parts if differ), Fraction(0)) / total) if total else 0.0


def pairs() -> list[tuple]:
    found = []
    paths = set(pieces.rome_tree())
    for folder, files, url in ceiling.candidates(paths):
        name = folder.removeprefix("Corpus/")
        try:
            data = ceiling.fetch(url, name.replace("/", "__") + Path(url).suffix)
            if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
                data = re.sub(r"encoding=['\"]UTF-16['\"]", "encoding='UTF-8'", data.decode("utf-16"), flags=re.I).encode("utf-8")
            index = ScoreIndex(load_toolkit(pieces.without_harmony(data)).getMEI())
            texts = {f: ceiling.fetch(ceiling.ROME + urllib.parse.quote(f"{folder}/{f}"), name.replace("/", "__") + "__" + f).decode("utf-8", "ignore") for f in files}
        except Exception:
            continue
        sources = {f: ceiling.source(text, f) for f, text in texts.items()}
        first = {source: f for f, source in reversed(sources.items())}
        timeline = compare.Timeline(index)
        for a, b in combinations([f for f in files if first.get(sources[f]) == f], 2):
            if None in (sources[a], sources[b]) or sources[a] == sources[b] or texts[a].split("\n", 3)[-1] == texts[b].split("\n", 3)[-1]:
                continue
            try:
                (fit_a, labels_a), (fit_b, labels_b) = ceiling.aligned(texts[a], timeline), ceiling.aligned(texts[b], timeline)
            except Exception:
                continue
            if min(fit_a, fit_b) >= ceiling.FIT:
                found.append((name, labels_a, labels_b, timeline, index))
    return sorted(found, key=lambda pair: pair[0])


def measure(chosen: list[tuple], generator: random.Random) -> dict:
    hits, chance = [], []
    flagged = total = target = covered = Fraction(0)
    for _, labels_a, labels_b, timeline, index in chosen:
        known = {m.number for m in index.measures}
        for reading, other in ((labels_a, labels_b), (labels_b, labels_a)):
            found = key_disagreements(timeline.spans(reading)[0], timeline.spans(other)[0])
            if not found:
                continue
            low, high = found[0][0], found[-1][1]
            total += high - low
            items = [{"type": "harmony", "at": {"measure": l.measure, "beat": l.beat}, "label": l.figure, "key": l.key} for l in reading if l.measure in known]
            spans = [(timeline.starts[a["start"]["measure"]] + (Fraction(a["start"]["beat"]).limit_denominator(96) - 1) * timeline.measures[a["start"]["measure"]].beat_length,
                      timeline.starts[a["end"]["measure"]] + timeline.measures[a["end"]["measure"]].length) for a in alternatives(items, index)]
            for x, y, differ in found:
                if differ:
                    target += y - x
                    covered += (y - x) * any(a <= x < b for a, b in spans)
            for a, b in spans:
                if b <= a:
                    continue
                flagged += b - a
                hits.append(share(found, a, b) >= HIT)
                for _ in range(20):
                    if high - low > b - a:
                        start = low + Fraction(generator.random()).limit_denominator(1000) * (high - low - (b - a))
                        chance.append(share(found, start, start + (b - a)) >= HIT)
    rate = lambda found: round(sum(found) / len(found), 3) if found else None
    return {"flags": len(hits), "hits": rate(hits), "random": rate(chance), "coverage": round(float(covered / target), 3) if target else None,
            "flagged": round(float(flagged / total), 3) if total else None}


def main() -> None:
    ordered = pairs()
    generator = random.Random(0)
    for half, chosen in (("first half", ordered[0::2]), ("second half", ordered[1::2])):
        print(half, measure(chosen, generator))


if __name__ == "__main__":
    main()
