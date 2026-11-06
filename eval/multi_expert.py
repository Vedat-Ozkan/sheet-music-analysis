"""Our reading scored as one more analyst on pieces that two or more independent experts have analysed.

    .venv/bin/python -m eval.multi_expert [--reviewed out/eval/reviewed/<run>]

Pieces are the `multi` set (eval/multi-expert-set.txt). Every expert file in the piece's When in Rome folder
from a different source is placed on the score by the rule in eval/ceiling.py (shifted -1, 0 or +1 bar to fit
the notes) and kept when it fits at least 0.85. On the reviewed bars only, each piece reports every pair of
experts (both directions averaged), the review against each expert and the draft against each expert, at every
level by time and by chord. By chord, each chord counts once and agrees when the other reading agrees with it
over more than half of it: recall counts the expert's chords, precision the reading's. Pooled figures are
bar-weighted and per-piece means, with a 95% bootstrap interval over pieces for ours minus experts. Where the
expert files come from DCML, its cadences are counted against the review's. Results go to
out/eval/multi-expert-<run>.json, or multi-expert-draft.json without --reviewed.
"""

from __future__ import annotations

import argparse
import json
import random
import urllib.parse
from fractions import Fraction
from itertools import combinations
from pathlib import Path

from engine.comparison import agreement
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import ceiling, compare, pieces
from eval.any_expert import folder_for
from eval.review import passages
from eval.run import cached_draft

LEVELS = ("key", "root", "chord", "chord_and_bass", "function", "idea", "full")
HEADLINE = ("root", "function", "full")
CADENCES = {"PAC": "PAC", "IAC": "IAC", "HC": "HC", "PHC": "HC", "DC": "DC", "EC": "EC", "PC": "PC"}


def experts_for(folder: str, files: list[str], timeline: compare.Timeline) -> dict[str, tuple[float, list[compare.Label], int]]:
    name = folder.removeprefix("Corpus/")
    texts = {file: ceiling.fetch(ceiling.ROME + urllib.parse.quote(f"{folder}/{file}"), name.replace("/", "__") + "__" + file).decode("utf-8", "ignore") for file in files}
    found, bodies = {}, set()
    for file, text in texts.items():
        source, body = ceiling.source(text, file), text.split("\n", 3)[-1]
        if source is None or source in found or body in bodies:
            continue
        bodies.add(body)
        fit, labels = ceiling.aligned(text, timeline)
        found[source] = (round(fit, 3), labels, labels[0].measure - compare.from_romantext(text)[0].measure if labels else 0)
    return found


def by_chord(reference: list[compare.Label], reading: list[compare.Label], timeline: compare.Timeline, windows: list[tuple[Fraction, Fraction]]) -> dict:
    ref, hyp = timeline.spans(reference)[0], timeline.spans(reading)[0]

    def side(counted, other, counted_is_reference):
        agreed, total = dict.fromkeys(LEVELS, 0), 0
        for start, end, chord in counted:
            window = next((window for window in windows if window[0] <= start < window[1]), None)
            if chord is None or window is None:
                continue
            end = min(end, window[1])
            time = dict.fromkeys(LEVELS, Fraction(0))
            for low, high, found in other:
                overlap = min(end, high) - max(start, low)
                if found is None or overlap <= 0:
                    continue
                same = agreement(chord, found) if counted_is_reference else agreement(found, chord)
                for level in LEVELS:
                    time[level] += overlap * same[level]
            total += 1
            for level in LEVELS:
                agreed[level] += time[level] * 2 > end - start
        return {level: agreed[level] / total if total else None for level in LEVELS}, total

    recall, chords = side(ref, hyp, True)
    precision, _ = side(hyp, ref, False)
    return {"recall": recall, "precision": precision, "chords": chords}


def scored(reference, reading, index, timeline, bars, windows) -> dict:
    return {"time": {level: compare.compare(reference, reading, index, bars)[level] for level in LEVELS}, **by_chord(reference, reading, timeline, windows)}


def mean_of(results: list[dict]) -> dict:
    out = {}
    for measure in ("time", "recall", "precision"):
        out[measure] = {level: sum(r[measure][level] for r in results) / len(results) for level in LEVELS}
    return out


def both_ways(a: dict, b: dict) -> dict:
    out = {"time": {level: (a["time"][level] + b["time"][level]) / 2 for level in LEVELS}}
    for measure in ("recall", "precision"):
        out[measure] = {level: (a[measure][level] + b[measure][level]) / 2 for level in LEVELS}
    return out


def dcml_cadences(folder: str, index: ScoreIndex, shift: int) -> list[tuple[Fraction, str]] | None:
    remote_path = folder.removeprefix("Corpus/").replace("/", "__") + "__remote.json"
    remote = json.loads(ceiling.fetch(ceiling.ROME + urllib.parse.quote(folder + "/remote.json"), "Corpus__" + remote_path))
    source = str(remote.get("analysis_source", ""))
    if "DCMLab" in source:
        repository, stem = source.split("DCMLab/")[1].split("/")[0], Path(source).name.removesuffix(".tsv").removesuffix(".harmonies")
    elif "Beethoven" in folder and remote.get("sonata_number"):
        repository, stem = "beethoven_piano_sonatas", f"{remote['sonata_number']:02d}-{remote['movement']}"
    else:
        return None
    url = f"https://raw.githubusercontent.com/DCMLab/{repository}/main/harmonies/{urllib.parse.quote(stem)}.harmonies.tsv"
    lines = ceiling.fetch(url, f"dcml__{repository}__{stem}.harmonies.tsv").decode("utf-8").splitlines()
    header = lines[0].split("\t")
    starts, total = [], Fraction(0)
    for measure in index.measures:
        starts.append((total, measure))
        total += measure.length
    found = []
    place = {id(m): k for k, (_, m) in enumerate(starts)}
    for line in lines[1:]:
        row = dict(zip(header, line.split("\t")))
        if not row.get("cadence") or row["cadence"] not in CADENCES:
            continue
        if index.renumbered:
            position = Fraction(row.get("quarterbeats_all_endings") or row["quarterbeats"])
            start, measure = next(((s, m) for s, m in reversed(starts) if s <= position), starts[0])
            offset = position - start
        else:
            measure, offset = index.measure(int(row["mn"])), Fraction(row["mn_onset"]) * 4
            if measure is index.measures[0] and measure.declared_length is None and measure.meter:
                count, unit = measure.meter.split("/")
                offset -= Fraction(int(count) * 4, int(unit)) - measure.length
        k = place[id(measure)] + shift
        if not 0 <= k < len(starts):
            continue
        start, measure = starts[k]
        if 0 <= offset < measure.length:
            found.append((start + offset, CADENCES[row["cadence"]]))
    return found


def our_cadences(review: dict, timeline: compare.Timeline) -> list[tuple[Fraction, str]]:
    found = []
    for item in review["annotations"]:
        if item.get("type") != "cadence" or "at" not in item:
            continue
        at = item["at"]
        measure = timeline.measures.get(at["measure"])
        if measure is None:
            continue
        kind = str(item.get("label", "")).upper()
        found.append((timeline.starts[at["measure"]] + (Fraction(at.get("beat", 1)).limit_denominator(96) - 1) * measure.beat_length, CADENCES.get(kind, kind)))
    return found


def cadence_counts(expert: list, ours: list, windows, timeline: compare.Timeline) -> dict:
    expert = [c for c in expert if any(low <= c[0] < high for low, high in windows)]
    bars = sorted((timeline.starts[number], measure.beat_length) for number, measure in timeline.measures.items())
    beat_at = lambda time: next(beat for start, beat in reversed(bars) if start <= time)
    near = lambda a, b: abs(a[0] - b[0]) <= beat_at(a[0])
    return {
        "expert": len(expert),
        "ours": len(ours),
        "same place and type": sum(any(near(e, o) and e[1] == o[1] for o in ours) for e in expert),
        "same place, any type": sum(any(near(e, o) for o in ours) for e in expert),
        "ours with no expert cadence": sum(not any(near(o, e) for e in expert) for o in ours),
    }


def piece_report(piece: pieces.Piece, folders: dict, paths: set, reviewed: Path | None) -> dict:
    index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
    timeline = compare.Timeline(index)
    folder = folder_for(piece, folders, paths)
    review_path = reviewed / f"{piece.id}.json" if reviewed else None
    review = json.loads(review_path.read_text()) if review_path and review_path.exists() else None
    bars = [tuple(p) for p in review["passages"]] if review else passages(index, 24, 2)
    windows = [(timeline.starts[first], timeline.starts[last] + timeline.measures[last].length) for first, last in bars]
    experts = experts_for(folder, folders[folder], timeline)
    kept = {source: labels for source, (fit, labels, _) in experts.items() if fit >= ceiling.FIT}
    entry = {"folder": folder, "style": ceiling.style(folder), "bars": sum(last - first + 1 for first, last in bars), "passages": bars, "fits": {s: f for s, (f, _, _) in experts.items()}, "reviewed": review is not None}
    if len(kept) < 2:
        entry["skipped"] = "fewer than two experts at fit 0.85"
        return entry
    entry["pairs"] = {f"{a} v {b}": both_ways(scored(kept[a], kept[b], index, timeline, bars, windows), scored(kept[b], kept[a], index, timeline, bars, windows)) for a, b in combinations(kept, 2)}
    drafted = compare.from_draft(cached_draft(piece, index))
    entry["draft"] = {source: scored(labels, drafted, index, timeline, bars, windows) for source, labels in kept.items()}
    if review:
        reading = compare.from_annotations(review)
        entry["ours"] = {source: scored(labels, reading, index, timeline, bars, windows) for source, labels in kept.items()}
        expert_cadences = dcml_cadences(folder, index, experts["DCML"][2]) if "DCML" in kept else None
        if expert_cadences is not None:
            entry["cadences"] = cadence_counts(expert_cadences, our_cadences(review, timeline), windows, timeline)
    return entry


def summary_of(entries: dict) -> dict:
    rows = [e for e in entries.values() if "pairs" in e]
    out = {}
    for arm in ("experts", "ours", "draft"):
        values = []
        for e in rows:
            if arm == "experts":
                values.append((e["bars"], mean_of(list(e["pairs"].values()))))
            elif arm in e:
                values.append((e["bars"], mean_of(list(e[arm].values()))))
        if values:
            out[arm] = {"pieces": len(values), "bars": sum(w for w, _ in values), **pooled(values)}
    return out


def pooled(values: list[tuple[int, dict]]) -> dict:
    weight = sum(w for w, _ in values)
    return {
        way: {measure: {level: sum((w if way == "bar-weighted" else 1) * v[measure][level] for w, v in values) / (weight if way == "bar-weighted" else len(values)) for level in LEVELS} for measure in ("time", "recall", "precision")}
        for way in ("bar-weighted", "per piece")
    }


def gap_interval(entries: dict, resamples: int = 2000) -> dict:
    rows = [(e["bars"], mean_of(list(e["ours"].values())), mean_of(list(e["pairs"].values()))) for e in entries.values() if "ours" in e and "pairs" in e]
    if not rows:
        return {}
    generator = random.Random(0)

    def gap(sample, way, measure, level):
        weights = [w if way == "bar-weighted" else 1 for w, _, _ in sample]
        return sum(w * (o[measure][level] - x[measure][level]) for w, (_, o, x) in zip(weights, sample)) / sum(weights)

    out = {}
    samples = [generator.choices(rows, k=len(rows)) for _ in range(resamples)]
    for way in ("bar-weighted", "per piece"):
        for measure in ("time", "recall", "precision"):
            for level in HEADLINE:
                spread = sorted(gap(sample, way, measure, level) for sample in samples)
                out[f"{way} {measure} {level}"] = [round(gap(rows, way, measure, level), 3), round(spread[int(0.025 * resamples)], 3), round(spread[int(0.975 * resamples)], 3)]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed", type=Path, help="folder of reviewed annotation lists, <id>.json; without it only experts and the draft are scored, on the passages a review would take")
    parser.add_argument("--only", action="append", help="score only this piece (repeatable)")
    args = parser.parse_args()
    paths = set(pieces.rome_tree())
    folders = {folder: files for folder, files, _ in ceiling.candidates(paths)}
    entries = {}
    for piece in [pieces.BY_ID[name] for name in args.only] if args.only else pieces.MULTI:
        entries[piece.id] = entry = piece_report(piece, folders, paths, args.reviewed)
        line = f"{piece.id:50s} {entry['bars']:4d} bars  " + ("  ".join(f"{s} {f:.2f}" for s, f in entry["fits"].items()))
        if "pairs" in entry:
            for arm in ("experts", "ours", "draft"):
                if arm == "experts" or arm in entry:
                    m = mean_of(list(entry["pairs" if arm == "experts" else arm].values()))
                    line += f"\n    {arm:8s} " + "  ".join(f"{level[:5]} {m['time'][level]:.2f}" for level in HEADLINE) + "  by chord R/P " + "  ".join(f"{level[:5]} {m['recall'][level]:.2f}/{m['precision'][level]:.2f}" for level in HEADLINE)
        print(line + (f"  {entry['skipped']}" if "skipped" in entry else ""), flush=True)
    styles = sorted({e["style"] for e in entries.values()})
    report = {"pieces": entries, "summary": {group: summary_of({k: e for k, e in entries.items() if group == "all" or e["style"] == group}) for group in styles + ["all"]}}
    report["gap"] = {group: gap_interval({k: e for k, e in entries.items() if group == "all" or e["style"] == group}) for group in styles + ["all"]}
    cadences = [e["cadences"] for e in entries.values() if "cadences" in e]
    report["cadences"] = {key: sum(c[key] for c in cadences) for key in (cadences[0] if cadences else {})} | {"pieces": len(cadences)}
    out = pieces.OUT / f"multi-expert-{args.reviewed.name if args.reviewed else 'draft'}.json"
    out.write_text(json.dumps(report, indent=1, default=str))
    for group, row in report["summary"].items():
        for arm, s in row.items():
            print(f"{group:20s} {arm:8s} {s['pieces']:3d} pieces {s['bars']:5d} bars  " + "  ".join(f"{level[:5]} {s['bar-weighted']['time'][level]:.3f}" for level in LEVELS))
    print(json.dumps(report["gap"].get("all", {}), indent=None))
    print("cadences", report["cadences"])


if __name__ == "__main__":
    main()
