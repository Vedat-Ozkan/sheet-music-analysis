"""Agreement with any of several independent expert analyses, beside agreement with one.

    .venv/bin/python -m eval.any_expert [--reviewed out/eval/reviewed/<run>]

A moment of music counts as agreeing when the reading matches at least one expert who labels it. Pieces
are the evaluation pieces whose When in Rome folder holds a second analysis from a different source
(the rule in eval/ceiling.py). Every analysis is placed on the score the review was made on: the piece's
own reference with its bar offset, the others shifted by -1, 0 or +1 to agree best with it (some reviews
and references share a numbering one bar off the score's notes), and kept only when their best fit to the
notes is 0.85 or more. Each piece reports the reviewed reading and the draft against each expert and against
any, and each expert against any of the others (the experts' own figure; with three or more experts,
the reviewed reading is also scored against the same others, so the two are comparable). Scoring is
limited to the reviewed passages. Results go to out/eval/any-expert.json.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from fractions import Fraction
from pathlib import Path

from engine.comparison import matches, same_function
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import ceiling, compare, pieces
from eval.run import cached_draft

LEVELS = ("key", "root", "chord_and_bass", "function", "full")
OUT = pieces.OUT / "any-expert.json"


def compare_any(references: list[list[compare.Label]], reading: list[compare.Label], index: ScoreIndex, bars: list[tuple[int, int]] | None = None) -> dict:
    timeline = compare.Timeline(index)
    refs = [timeline.spans(reference)[0] for reference in references]
    hyp = timeline.spans(reading)[0]
    windows = [(timeline.starts[first], timeline.starts[last] + timeline.measures[last].length) for first, last in bars or []]
    cuts = sorted({point for spans in refs + [hyp] for start, end, _ in spans for point in (start, end)} | {point for window in windows for point in window})
    at = lambda spans, time: next((chord for start, end, chord in spans if start <= time < end), None)
    weights = dict.fromkeys(("labelled", *LEVELS), Fraction(0))
    for start, end in zip(cuts, cuts[1:]):
        if windows and not any(low <= start < high for low, high in windows):
            continue
        experts = [chord for chord in (at(spans, start) for spans in refs) if chord is not None]
        if not experts:
            continue
        length = end - start
        weights["labelled"] += length
        h = at(hyp, start)
        if h is None:
            continue
        agreed = [{**matches(r, h), "function": same_function(r, h) or matches(r, h)["chord_and_bass"]} for r in experts]
        for level in LEVELS:
            weights[level] += length * any(found[level] for found in agreed)
    labelled = weights.pop("labelled")
    return {level: round(float(value / labelled), 3) if labelled else None for level, value in weights.items()}


def folder_for(piece: pieces.Piece, folders: dict[str, list[str]], paths: set[str]) -> str | None:
    label = piece.labels or ""
    if label.startswith(pieces.ROME):
        return "Corpus/" + urllib.parse.unquote(label.removeprefix(pieces.ROME)).rsplit("/", 1)[0]
    if match := re.search(r"riemenschneider(\d{3})", label):
        return next((f for f in folders if f.endswith(f"Chorales/{match[1]}")), None)
    if "mozart_sonatas" in piece.id and (match := re.fullmatch(r".*-(K\d+)-(\d)", piece.id)):
        return next((f for f in folders if f.endswith(f"Mozart,_Wolfgang_Amadeus/{match[1]}/{match[2]}")), None)
    if "chopin_mazurkas" in piece.id and (match := re.search(r"-(BI[\d]+-?\d*)op", piece.id)):
        return next((f for f in folders if f.endswith(f"Mazurkas/{match[1]}")), None)
    if "beethoven_piano_sonatas" in piece.id and (match := re.fullmatch(r".*-(\d\d)-(\d)", piece.id)):
        for folder in folders:
            if "Beethoven" in folder and "Piano_Sonatas" in folder and f"{folder}/remote.json" in paths:
                remote = json.loads(ceiling.fetch(ceiling.ROME + urllib.parse.quote(folder + "/remote.json"), folder.removeprefix("Corpus/").replace("/", "__") + "__remote.json"))
                if remote.get("sonata_number") == int(match[1]) and str(remote.get("movement")) == match[2]:
                    return folder
    return None


def experts_for(piece: pieces.Piece, folder: str, files: list[str], timeline: compare.Timeline) -> dict[str, tuple[float, list[compare.Label]]]:
    own_text = pieces.labels(piece) or ""
    own_source = "DCML" if (piece.labels or "").endswith(".harmonies.tsv") else ceiling.source(own_text, "analysis.txt") or "reference"
    own = [compare.Label(label.measure + piece.bar_offset, label.beat, label.key, label.figure) for label in compare.from_romantext(own_text)]
    found = {own_source: (round(ceiling.aligned(own_text, timeline)[0], 3), own)}
    name = folder.removeprefix("Corpus/")
    for file in files:
        text = ceiling.fetch(ceiling.ROME + urllib.parse.quote(f"{folder}/{file}"), name.replace("/", "__") + "__" + file).decode("utf-8", "ignore")
        source = ceiling.source(text, file)
        if source is None or source in found or text.split("\n", 3)[-1] == own_text.split("\n", 3)[-1]:
            continue
        labels = compare.from_romantext(text)
        shifted = [[compare.Label(label.measure + shift, label.beat, label.key, label.figure) for label in labels] for shift in (0, 1, -1)]
        found[source] = (round(ceiling.aligned(text, timeline)[0], 3), max(shifted, key=lambda moved: compare.compare(own, moved, timeline.index)["root"] or 0))
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed", type=Path, default=pieces.OUT / "reviewed" / "opus-medium-2026-10-24")
    parser.add_argument("--fit", type=float, default=ceiling.FIT)
    args = parser.parse_args()
    paths = set(pieces.rome_tree())
    folders = {folder: files for folder, files, _ in ceiling.candidates(paths)}
    report = {}
    for piece in pieces.PIECES + pieces.HELDOUT:
        path = args.reviewed / f"{piece.id}.json"
        folder = folder_for(piece, folders, paths) if path.exists() else None
        if folder not in folders:
            continue
        review = json.loads(path.read_text())
        bars = [tuple(passage) for passage in review["passages"]] if "passages" in review else None
        index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
        timeline = compare.Timeline(index)
        experts = experts_for(piece, folder, folders[folder], timeline)
        kept = {source: labels for source, (fit, labels) in experts.items() if fit >= args.fit}
        entry = {"folder": folder, "fits": {source: fit for source, (fit, _) in experts.items()}, "bars": sum(last - first + 1 for first, last in bars) if bars else len(index.measures)}
        if len(kept) < 2:
            entry["skipped"] = f"fewer than two experts at fit {args.fit}"
            report[piece.id] = entry
            print(f"{piece.id:45s} skipped: fits {entry['fits']}")
            continue
        reading = compare.from_annotations(review)
        drafted = compare.from_draft(cached_draft(piece, index))
        entry["single"] = {source: compare.compare(labels, reading, index, bars) for source, labels in kept.items()}
        entry["any"] = compare_any(list(kept.values()), reading, index, bars)
        entry["draft_any"] = compare_any(list(kept.values()), drafted, index, bars)
        entry["experts"] = {source: compare_any([other for name, other in kept.items() if name != source], labels, index, bars) for source, labels in kept.items()}
        if len(kept) >= 3:
            entry["ours_vs_others"] = {source: compare_any([other for name, other in kept.items() if name != source], reading, index, bars) for source in kept}
        report[piece.id] = entry
        print(f"{piece.id:45s} {'/'.join(kept)}  ours any: " + "  ".join(f"{level[:5]} {entry['any'][level]:.2f}" for level in LEVELS))
    OUT.write_text(json.dumps(report, indent=1))
    scored = {name: entry for name, entry in report.items() if "any" in entry}
    weight = sum(entry["bars"] for entry in scored.values()) or 1
    mean = lambda pick: {level: round(sum(pick(entry)[level] * entry["bars"] for entry in scored.values()) / weight, 3) for level in LEVELS}
    print(f"\n{len(scored)} pieces, {weight} bars (weighted by bars)")
    print("ours, best single expert: ", mean(lambda e: {level: max(s[level] for s in e["single"].values()) for level in LEVELS}))
    print("ours, any expert:         ", mean(lambda e: e["any"]))
    print("draft, any expert:        ", mean(lambda e: e["draft_any"]))
    print("experts, any other expert:", mean(lambda e: {level: sum(x[level] for x in e["experts"].values()) / len(e["experts"]) for level in LEVELS}))


if __name__ == "__main__":
    main()
