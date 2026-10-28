"""Do our `alternative` marks fall where experts read the music differently?

    .venv/bin/python -m eval.second_readings --reviewed out/eval/reviewed/<run with --second-readings>

For each reviewed piece with one expert analysis, every `alternative` span is checked two ways: whether the
expert's reading differs from our main reading over at least a quarter of the span (at the function level),
and whether the expert holds the alternative itself (its key, or at least half of its chords, appear in the
expert's reading of the span). Two baselines get spans of the same lengths in the same passages: random
spans (also carrying the same alternative, for the second check), and spans around the draft's least
confident chords. Coverage is the share of the music where we
disagree with the expert that lies inside a flagged span; rarity is flagged bars per 100 reviewed bars.
"""

from __future__ import annotations

import argparse
import json
import random
from fractions import Fraction
from pathlib import Path

from engine.comparison import agreement, sounding
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import compare, pieces
from eval.run import cached_draft

DISAGREES = 0.25


def position(timeline: compare.Timeline, measure: int, beat: float | None, end: bool = False) -> Fraction:
    bar = timeline.measures[measure]
    if beat is None:
        return timeline.starts[measure] + (bar.length if end else 0)
    return timeline.starts[measure] + min(max(Fraction(0), (Fraction(beat).limit_denominator(96) - 1) * bar.beat_length), bar.length)


def share_disagreeing(start: Fraction, end: Fraction, expert: list, ours: list) -> float:
    cuts = sorted({start, end} | {p for spans in (expert, ours) for a, b, _ in spans for p in (a, b) if start < p < end})
    at = lambda spans, time: next((chord for a, b, chord in spans if a <= time < b), None)
    labelled = differ = Fraction(0)
    for a, b in zip(cuts, cuts[1:]):
        r, h = at(expert, a), at(ours, a)
        if r is None:
            continue
        labelled += b - a
        differ += (b - a) * (h is None or not agreement(r, h)["function"])
    return float(differ / labelled) if labelled else 0.0


def holds(label: str, key: str, start: Fraction, end: Fraction, expert: list) -> bool:
    tokens = label.split()
    named = tokens[0][:-1] if tokens and tokens[0].endswith(":") else None
    chords = [sounding(named or key, token) for token in tokens[1 if named else 0:]]
    inside = [chord for a, b, chord in expert if chord is not None and a < end and b > start]
    if named and (probe := sounding(named, "I")) and inside:
        if sum(1 for chord in inside if (chord.tonic, chord.minor) == (probe.tonic, probe.minor)) * 2 >= len(inside):
            return True
    found = [chord for chord in chords if chord is not None]
    return bool(found) and sum(any(c.root == e.root and c.tones == e.tones for e in inside) for c in found) * 2 >= len(found)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed", type=Path, required=True)
    args = parser.parse_args()
    generator = random.Random(0)
    flagged, random_hits, draft_hits, holding, random_holding = [], [], [], [], []
    reviewed_bars = flagged_bars = 0
    disagreeing = covered = Fraction(0)
    for piece in pieces.PIECES + pieces.HELDOUT:
        path = args.reviewed / f"{piece.id}.json"
        if not path.exists() or not pieces.labels(piece):
            continue
        review = json.loads(path.read_text())
        bars = [tuple(passage) for passage in review.get("passages", [])]
        index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
        timeline = compare.Timeline(index)
        expert = timeline.spans([compare.Label(l.measure + piece.bar_offset, l.beat, l.key, l.figure) for l in compare.from_romantext(pieces.labels(piece))])[0]
        ours = timeline.spans(compare.from_annotations(review))[0]
        windows = [(timeline.starts[a], timeline.starts[b] + timeline.measures[b].length) for a, b in bars]
        reviewed_bars += sum(b - a + 1 for a, b in bars)
        keys = {item["at"]["measure"]: item["key"] for item in review["annotations"] if item["type"] == "harmony" and item.get("key")}
        drafted = cached_draft(piece, index)
        doubtful = sorted((chord.confidence, position(timeline, chord.measure, chord.beat)) for chord in drafted.chords if any(a <= timeline.starts.get(chord.measure, -1) < b for a, b in windows))
        spans = []
        for item in review["annotations"]:
            if item["type"] != "alternative":
                continue
            start, end = position(timeline, item["start"]["measure"], item["start"].get("beat")), position(timeline, item["end"]["measure"], item["end"].get("beat"), True)
            if end <= start:
                continue
            spans.append((start, end))
            flagged_bars += item["end"]["measure"] - item["start"]["measure"] + 1
            key = keys[max([m for m in keys if m <= item["start"]["measure"]] or [min(keys)])] if keys else "C"
            flagged.append(share_disagreeing(start, end, expert, ours) >= DISAGREES)
            holding.append(holds(item["label"], key, start, end, expert))
            for _ in range(50):
                window = generator.choice(windows)
                if window[1] - window[0] > end - start:
                    shift = window[0] + Fraction(generator.random()).limit_denominator(1000) * (window[1] - window[0] - (end - start))
                    random_hits.append(share_disagreeing(shift, shift + (end - start), expert, ours) >= DISAGREES)
                    random_holding.append(holds(item["label"], key, shift, shift + (end - start), expert))
            if doubtful:
                _, centre = doubtful.pop(0)
                draft_hits.append(share_disagreeing(centre - (end - start) / 2, centre + (end - start) / 2, expert, ours) >= DISAGREES)
        cuts = sorted({p for s in (expert, ours) for a, b, _ in s for p in (a, b)} | {p for w in windows for p in w})
        at = lambda s, time: next((chord for a, b, chord in s if a <= time < b), None)
        for a, b in zip(cuts, cuts[1:]):
            r, h = at(expert, a), at(ours, a)
            if r is None or not any(low <= a < high for low, high in windows) or (h is not None and agreement(r, h)["function"]):
                continue
            disagreeing += b - a
            covered += (b - a) * any(low <= a < high for low, high in spans)
    rate = lambda hits: round(sum(hits) / len(hits), 3) if hits else None
    print(f"{len(flagged)} alternatives over {reviewed_bars} reviewed bars ({100 * flagged_bars / max(reviewed_bars, 1):.1f} flagged bars per 100)")
    print(f"where the expert disagrees with our main reading: ours {rate(flagged)}, random spans {rate(random_hits)}, draft's least confident {rate(draft_hits)}")
    print(f"where the expert holds our alternative: ours {rate(holding)}, the same alternative at random spans {rate(random_holding)}")
    print(f"coverage of our disagreements with the expert: {round(float(covered / disagreeing), 3) if disagreeing else None}")


if __name__ == "__main__":
    main()
