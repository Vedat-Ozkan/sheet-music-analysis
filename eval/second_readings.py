"""Do our `alternative` marks fall where experts read the music differently?

    .venv/bin/python -m eval.second_readings --reviewed out/eval/reviewed/<run with --second-readings>

For each reviewed piece with one expert analysis, every `alternative` span is checked two ways: whether the
expert's reading differs from our main reading over at least a quarter of the span (at the function level),
and whether the expert holds the alternative itself (the expert names its key over at least half of the span
when it names one; otherwise at least half of its chords appear in the expert's reading of the span). Two baselines get spans of the same lengths in the same passages: random
spans (also carrying the same alternative, for the second check), and spans around the draft's least
confident chords. Coverage is the share of the music where we
disagree with the expert that lies inside a flagged span; rarity is flagged bars per 100 reviewed bars.

With --experts-split, only pieces with two or more independent expert analyses at fit 0.85 or more are used
(as in eval/any_expert.py), and the target is the music where the experts disagree with each other; the
second check asks whether any of them holds the alternative.
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
from eval import any_expert, ceiling, compare, pieces
from eval.run import cached_draft

DISAGREES = 0.25


def position(timeline: compare.Timeline, measure: int, beat: float | None, end: bool = False) -> Fraction:
    bar = timeline.measures[measure]
    if beat is None:
        return timeline.starts[measure] + (bar.length if end else 0)
    return timeline.starts[measure] + min(max(Fraction(0), (Fraction(beat).limit_denominator(96) - 1) * bar.beat_length), bar.length)


def disagreements(readings: list[list], windows: list[tuple[Fraction, Fraction]], split: bool) -> list[tuple[Fraction, Fraction, bool]]:
    cuts = sorted({p for spans in readings for a, b, _ in spans for p in (a, b)} | {p for window in windows for p in window})
    at = lambda spans, time: next((chord for a, b, chord in spans if a <= time < b), None)
    found = []
    for a, b in zip(cuts, cuts[1:]):
        if not any(low <= a < high for low, high in windows):
            continue
        chords = [at(spans, a) for spans in readings]
        if split:
            labelled = [chord for chord in chords if chord is not None]
            if len(labelled) < 2:
                continue
            differ = any(not agreement(x, y)["function"] for i, x in enumerate(labelled) for y in labelled[i + 1:])
        else:
            reference, reading = chords
            if reference is None:
                continue
            differ = reading is None or not agreement(reference, reading)["function"]
        found.append((a, b, differ))
    return found


def share(found: list[tuple[Fraction, Fraction, bool]], start: Fraction, end: Fraction) -> float:
    parts = [(max(a, start), min(b, end), differ) for a, b, differ in found if a < end and b > start]
    labelled = sum((b - a for a, b, _ in parts), Fraction(0))
    return float(sum((b - a for a, b, differ in parts if differ), Fraction(0)) / labelled) if labelled else 0.0


def holds(label: str, key: str, start: Fraction, end: Fraction, expert: list) -> bool:
    tokens = label.split()
    named = tokens[0][:-1] if tokens and tokens[0].endswith(":") else None
    chords = [sounding(named or key, token) for token in tokens[1 if named else 0:]]
    inside = [chord for a, b, chord in expert if chord is not None and a < end and b > start]
    if named:
        probe = sounding(named, "I")
        return bool(inside) and probe is not None and sum(1 for chord in inside if (chord.tonic, chord.minor) == (probe.tonic, probe.minor)) * 2 >= len(inside)
    found = [chord for chord in chords if chord is not None]
    return bool(found) and sum(any(c.root == e.root and c.tones == e.tones for e in inside) for c in found) * 2 >= len(found)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed", type=Path, required=True)
    parser.add_argument("--experts-split", action="store_true", help="score against places where two or more independent experts disagree with each other")
    args = parser.parse_args()
    generator = random.Random(0)
    flagged, random_hits, draft_hits, holding, random_holding = [], [], [], [], []
    reviewed_bars = flagged_bars = 0
    disagreeing = covered = Fraction(0)
    if args.experts_split:
        paths = set(pieces.rome_tree())
        folders = {folder: files for folder, files, _ in ceiling.candidates(paths)}
    for piece in pieces.PIECES + pieces.HELDOUT:
        path = args.reviewed / f"{piece.id}.json"
        if not path.exists() or not pieces.labels(piece):
            continue
        review = json.loads(path.read_text())
        index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
        timeline = compare.Timeline(index)
        if args.experts_split:
            folder = any_expert.folder_for(piece, folders, paths)
            found = any_expert.experts_for(piece, folder, folders[folder], timeline) if folder in folders else {}
            experts = [timeline.spans(labels)[0] for fit, labels in found.values() if fit >= ceiling.FIT]
            if len(experts) < 2:
                continue
        else:
            experts = [timeline.spans([compare.Label(l.measure + piece.bar_offset, l.beat, l.key, l.figure) for l in compare.from_romantext(pieces.labels(piece))])[0]]
        ours = timeline.spans(compare.from_annotations(review))[0]
        bars = [tuple(passage) for passage in review.get("passages", [])] or [(index.measures[0].number, index.measures[-1].number)]
        windows = [(timeline.starts[a], timeline.starts[b] + timeline.measures[b].length) for a, b in bars]
        found = disagreements(experts if args.experts_split else [experts[0], ours], windows, args.experts_split)
        reviewed_bars += sum(b - a + 1 for a, b in bars)
        keys = {item["at"]["measure"]: item["key"] for item in review["annotations"] if item["type"] == "harmony" and item.get("key")}
        drafted = cached_draft(piece, index)
        doubtful = sorted((chord.confidence, position(timeline, chord.measure, chord.beat)) for chord in drafted.chords if any(a <= timeline.starts.get(chord.measure, -1) < b for a, b in windows))
        holds_any = lambda label, key, start, end: any(holds(label, key, start, end, expert) for expert in experts)
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
            flagged.append(share(found, start, end) >= DISAGREES)
            holding.append(holds_any(item["label"], key, start, end))
            for _ in range(50):
                window = generator.choice(windows)
                if window[1] - window[0] > end - start:
                    shift = window[0] + Fraction(generator.random()).limit_denominator(1000) * (window[1] - window[0] - (end - start))
                    random_hits.append(share(found, shift, shift + (end - start)) >= DISAGREES)
                    random_holding.append(holds_any(item["label"], key, shift, shift + (end - start)))
            if doubtful:
                _, centre = doubtful.pop(0)
                draft_hits.append(share(found, centre - (end - start) / 2, centre + (end - start) / 2) >= DISAGREES)
        for a, b, differ in found:
            if differ:
                disagreeing += b - a
                covered += (b - a) * any(low <= a < high for low, high in spans)
    target = "the experts disagree with each other" if args.experts_split else "the expert disagrees with our main reading"
    rate = lambda hits: round(sum(hits) / len(hits), 3) if hits else None
    print(f"{len(flagged)} alternatives over {reviewed_bars} reviewed bars ({100 * flagged_bars / max(reviewed_bars, 1):.1f} flagged bars per 100)")
    print(f"where {target}: ours {rate(flagged)}, random spans {rate(random_hits)}, draft's least confident {rate(draft_hits)}")
    print(f"where {'an' if args.experts_split else 'the'} expert holds our alternative: ours {rate(holding)}, the same alternative at random spans {rate(random_holding)}")
    print(f"coverage (share of that disagreement inside a flagged span): {round(float(covered / disagreeing), 3) if disagreeing else None}")


if __name__ == "__main__":
    main()
