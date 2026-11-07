"""A reviewed run scored on the ladder of measures, beside the same measures between experts.

    .venv/bin/python -m eval.ladder --set heldout|core|multi [--reviewed out/eval/reviewed/<run>] [--only ID]

On the reviewed bars only, each piece reports the review and the draft against its expert:
- agreement by time at every level (as eval/run.py);
- by chord: each chord counts once and agrees when the other reading agrees with it over more than half of it;
  recall counts the expert's chords, precision the reading's;
- chord changes (a new chord, its notes or its bass) shared with the expert's within a quarter beat, missed and extra;
- where the expert is DCML: the expert's cadences we mark within one beat with the same type, and with any type,
  and our marks with no expert cadence (information, not errors). Cadences count only on pieces whose expert marks
  a cadence within a bar of at least half of its own phrase endings.

In the `multi` set (eval/multi-expert-set.txt) every expert file in the piece's When in Rome folder from a different
source is placed by the rule in eval/ceiling.py and kept when it fits at least 0.85; the review is scored against
each and the experts against each other on the same bars (both directions). For the other sets the expert figure
comes from every expert pair in eval/ceiling.py, over whole pieces, cached in out/eval/ladder-experts.json.
By time and the reading's fit to the notes are weighted by bars; by chord and changes pool the counts. Results go to out/eval/ladder-<set>-<run>.json.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import urllib.parse
from fractions import Fraction
from itertools import combinations
from multiprocessing import Pool
from pathlib import Path

from engine.comparison import agreement
from engine.reduce import midi
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import ceiling, compare, pieces
from eval.any_expert import folder_for
from eval.review import passages
from eval.run import cached_draft

LEVELS = ("key", "root", "chord", "chord_and_bass", "function", "idea", "full")
HEADLINE = ("root", "function", "full")
EXPERTS = pieces.OUT / "ladder-experts.json"
CADENCES = {"PAC": "PAC", "IAC": "IAC", "HC": "HC", "PHC": "HC", "DC": "DC", "EC": "EC", "PC": "PC"}
STYLES = (("beethoven", "Beethoven sonatas"), ("chopin", "Chopin mazurkas"), ("mozart", "Mozart sonatas"), ("chorale", "Bach chorales"), ("well-tempered", "Bach WTC preludes"),
          ("grieg", "Grieg"), ("schubert", "Lieder"), ("reichardt", "Lieder"), ("dichterliebe", "Lieder"), ("wolf", "Lieder"), ("hensel", "Lieder"))


def style(piece_id: str) -> str:
    return next((name for mark, name in STYLES if mark in piece_id), "Other Romantic piano")


def beat_at(timeline: compare.Timeline, time: Fraction) -> Fraction:
    return next(timeline.measures[number].beat_length for number, start in sorted(timeline.starts.items(), key=lambda item: item[1], reverse=True) if start <= time)


def by_chord(ref: list, hyp: list, windows: list) -> dict:
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
        return agreed, total

    recall, expert_chords = side(ref, hyp, True)
    precision, reading_chords = side(hyp, ref, False)
    return {"recall": recall, "precision": precision, "expert_chords": expert_chords, "reading_chords": reading_chords}


def changes(spans: list, windows: list) -> list[Fraction]:
    found, previous = [], None
    for start, _, chord in spans:
        current = (chord.root, chord.tones, chord.bass) if chord else None
        if previous is not None and current != previous and any(low < start < high for low, high in windows):
            found.append(start)
        previous = current
    return found


def change_counts(ref: list, hyp: list, windows: list, timeline: compare.Timeline) -> dict:
    expert, reading = changes(ref, windows), changes(hyp, windows)
    near = lambda x, others: any(abs(x - y) <= beat_at(timeline, x) / 4 for y in others)
    shared = sum(near(x, reading) for x in expert)
    return {"expert": len(expert), "shared": shared, "missed": len(expert) - shared, "extra": sum(not near(y, expert) for y in reading)}


def fit(spans: list, windows: list, timeline: compare.Timeline) -> dict:
    inside = total = Fraction(0)
    for measure in timeline.index.measures:
        if timeline.measures[measure.number] is not measure:
            continue
        for event in measure.events:
            onset = timeline.starts[measure.number] + event.onset
            if not event.pitch or event.grace or not any(low <= onset < high for low, high in windows):
                continue
            chord = next((chord for start, end, chord in spans if start <= onset < end), None)
            if chord is not None:
                total += event.duration
                inside += event.duration * (midi(event.pitch) % 12 in chord.tones)
    return {"inside": float(inside), "total": float(total)}


def measures(reference, reading, index, timeline, bars, windows) -> dict:
    ref, hyp = timeline.spans(reference)[0], timeline.spans(reading)[0]
    time = compare.compare(reference, reading, index, bars)
    return {"time": {level: time[level] for level in LEVELS}, "chord": by_chord(ref, hyp, windows), "changes": change_counts(ref, hyp, windows, timeline), "fit": fit(hyp, windows, timeline)}


def dcml_marks(tsv: str, index: ScoreIndex, shift: int = 0) -> dict:
    lines = tsv.splitlines()
    header = lines[0].split("\t")
    starts, total = [], Fraction(0)
    for measure in index.measures:
        starts.append((total, measure))
        total += measure.length
    place = {id(m): k for k, (_, m) in enumerate(starts)}
    cadences, phrase_ends = [], []
    for line in lines[1:]:
        row = dict(zip(header, line.split("\t")))
        if not row.get("cadence") and "}" not in row.get("phraseend", ""):
            continue
        if index.renumbered:
            position = Fraction(row.get("quarterbeats_all_endings") or row["quarterbeats"])
            measure = next((m for s, m in reversed(starts) if s <= position), starts[0][1])
            offset = position - starts[place[id(measure)]][0]
        else:
            try:
                measure, offset = index.measure(int(row["mn"])), Fraction(row["mn_onset"]) * 4
            except (KeyError, ValueError):
                continue
            if measure is index.measures[0] and measure.declared_length is None and measure.meter:
                count, unit = measure.meter.split("/")
                offset -= Fraction(int(count) * 4, int(unit)) - measure.length
        k = place[id(measure)] + shift
        if not 0 <= k < len(starts) or not 0 <= offset < starts[k][1].length:
            continue
        x = starts[k][0] + offset
        if row.get("cadence"):
            cadences.append((x, CADENCES.get(row["cadence"], row["cadence"])))
        if "}" in row.get("phraseend", ""):
            phrase_ends.append((x, starts[k][1].length))
    marked = sum(any(abs(c - x) <= bar for c, _ in cadences) for x, bar in phrase_ends)
    return {"cadences": cadences, "phrase_ends": len(phrase_ends), "phrase_ends_with_cadence": marked, "complete": bool(phrase_ends) and marked * 2 >= len(phrase_ends)}


def our_cadences(annotations: list, timeline: compare.Timeline) -> list[tuple[Fraction, str]]:
    found = []
    for item in annotations:
        measure = timeline.measures.get(item.get("at", {}).get("measure")) if item.get("type") == "cadence" else None
        if measure is not None:
            beat = max(Fraction(0), (Fraction(item["at"].get("beat", 1)).limit_denominator(96) - 1) * measure.beat_length)
            kind = str(item.get("label", "")).split()[0].upper() if item.get("label") else ""
            found.append((timeline.starts[item["at"]["measure"]] + beat, CADENCES.get(kind, kind)))
    return found


def cadence_counts(expert: list, ours: list, windows: list, timeline: compare.Timeline) -> dict:
    inside = lambda marks: [m for m in marks if any(low <= m[0] < high for low, high in windows)]
    expert, ours = inside(expert), inside(ours)
    near = lambda x, y: abs(x - y) <= beat_at(timeline, x)
    return {
        "expert": len(expert),
        "ours": len(ours),
        "same place and type": sum(any(near(x, y) and kind == other for y, other in ours) for x, kind in expert),
        "same place, any type": sum(any(near(x, y) for y, _ in ours) for x, _ in expert),
        "ours with no expert cadence": sum(not any(near(y, x) for x, _ in expert) for y, _ in ours),
    }


def experts_in(folder: str, files: list[str], timeline: compare.Timeline) -> dict[str, tuple[float, list[compare.Label], int]]:
    name = folder.removeprefix("Corpus/")
    found, bodies = {}, set()
    for file in files:
        text = ceiling.fetch(ceiling.ROME + urllib.parse.quote(f"{folder}/{file}"), name.replace("/", "__") + "__" + file).decode("utf-8", "ignore")
        source, body = ceiling.source(text, file), text.split("\n", 3)[-1]
        if source is None or source in found or body in bodies:
            continue
        bodies.add(body)
        fit, labels = ceiling.aligned(text, timeline)
        found[source] = (round(fit, 3), labels, labels[0].measure - compare.from_romantext(text)[0].measure if labels else 0)
    return found


def multi_dcml(folder: str, index: ScoreIndex, shift: int) -> dict | None:
    remote = json.loads(ceiling.fetch(ceiling.ROME + urllib.parse.quote(folder + "/remote.json"), folder.replace("/", "__") + "__remote.json"))
    source = str(remote.get("analysis_source", ""))
    if "DCMLab" in source:
        repository, stem = source.split("DCMLab/")[1].split("/")[0], Path(source).name.removesuffix(".tsv").removesuffix(".harmonies")
    elif "Beethoven" in folder and remote.get("sonata_number"):
        repository, stem = "beethoven_piano_sonatas", f"{remote['sonata_number']:02d}-{remote['movement']}"
    else:
        return None
    url = f"https://raw.githubusercontent.com/DCMLab/{repository}/main/harmonies/{urllib.parse.quote(stem)}.harmonies.tsv"
    return dcml_marks(ceiling.fetch(url, f"dcml__{repository}__{stem}.harmonies.tsv").decode("utf-8"), index, shift)


def piece_report(piece: pieces.Piece, reviewed: Path | None, rome: tuple[dict, set]) -> dict:
    index = ScoreIndex(load_toolkit(pieces.score(piece)).getMEI())
    timeline = compare.Timeline(index)
    review_path = reviewed / f"{piece.id}.json" if reviewed else None
    review = json.loads(review_path.read_text()) if review_path and review_path.exists() else None
    if reviewed and review is None:
        return {"skipped": "not reviewed"}
    bars = [tuple(p) for p in review["passages"]] if review and "passages" in review else passages(index, 24, 2) if piece in pieces.MULTI else [(index.measures[0].number, index.measures[-1].number)]
    windows = [(timeline.starts[first], timeline.starts[last] + timeline.measures[last].length) for first, last in bars]
    entry = {"style": style(piece.id), "bars": sum(last - first + 1 for first, last in bars), "passages": bars}
    if piece in pieces.MULTI:
        folders, paths = rome
        folder = folder_for(piece, folders, paths)
        found = experts_in(folder, folders[folder], timeline)
        entry["fits"] = {source: fit for source, (fit, _, _) in found.items()}
        experts = {source: labels for source, (fit, labels, _) in found.items() if fit >= ceiling.FIT}
        if len(experts) < 2:
            return entry | {"skipped": "fewer than two experts at fit 0.85"}
        entry["pairs"] = {f"{a} v {b}": [measures(experts[a], experts[b], index, timeline, bars, windows), measures(experts[b], experts[a], index, timeline, bars, windows)] for a, b in combinations(experts, 2)}
        marks = multi_dcml(folder, index, found["DCML"][2]) if "DCML" in experts else None
    else:
        experts = {"expert": [compare.Label(label.measure + piece.bar_offset, label.beat, label.key, label.figure) for label in compare.from_romantext(pieces.labels(piece) or "")]}
        if not experts["expert"]:
            return entry | {"skipped": "no expert labels"}
        is_dcml = (piece.labels or "").endswith(".harmonies.tsv")
        marks = dcml_marks(pieces._download(piece.labels, pieces.OUT / "labels" / f"{piece.id}.harmonies.tsv").decode("utf-8"), index) if is_dcml else None
    drafted = cached_draft(piece, index)
    readings = {"draft": (compare.from_draft(drafted), [(c.measure, c.beat, c.label) for c in drafted.cadences])}
    if review:
        readings["ours"] = (compare.from_annotations(review), None)
    for arm, (labels, _) in readings.items():
        entry[arm] = {source: measures(reference, labels, index, timeline, bars, windows) for source, reference in experts.items()}
    if marks is not None:
        entry["expert_marking"] = {key: marks[key] for key in ("phrase_ends", "phrase_ends_with_cadence", "complete")}
        if review:
            entry["cadences"] = cadence_counts(marks["cadences"], our_cadences(review["annotations"], timeline), windows, timeline)
    return entry


def folder_pairs(job: tuple[str, list[str], str]) -> list[dict]:
    folder, files, url = job
    name = folder.removeprefix("Corpus/")
    try:
        data = ceiling.fetch(url, name.replace("/", "__") + Path(url).suffix)
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            data = re.sub(r"encoding=['\"]UTF-16['\"]", "encoding='UTF-8'", data.decode("utf-16"), flags=re.I).encode("utf-8")
        index = ScoreIndex(load_toolkit(pieces.without_harmony(data)).getMEI())
        timeline = compare.Timeline(index)
        found = experts_in(folder, files, timeline)
    except Exception as error:
        print(f"{name:60s} skipped: {type(error).__name__}: {str(error)[:80]}", flush=True)
        return []
    bars = [(index.measures[0].number, index.measures[-1].number)]
    windows = [(Fraction(0), timeline.total)]
    return [{"piece": name, "style": ceiling.style(folder), "pair": f"{a} v {b}", "bars": len(index.measures),
             "both": [measures(found[a][1], found[b][1], index, timeline, bars, windows), measures(found[b][1], found[a][1], index, timeline, bars, windows)]}
            for a, b in combinations([source for source, (fit, _, _) in found.items() if fit >= ceiling.FIT], 2)]


def expert_pairs() -> list[dict]:
    if not EXPERTS.exists():
        with Pool(6) as workers:
            rows = [row for found in workers.map(folder_pairs, ceiling.candidates(set(pieces.rome_tree())), chunksize=1) for row in found]
        EXPERTS.write_text(json.dumps(rows, indent=1, default=str))
    return json.loads(EXPERTS.read_text())


def pool(results: list[tuple[int, list[dict]]]) -> dict:
    each = [(bars, 1 / len(group), m) for bars, group in results for m in group]
    weight = sum(bars for bars, _ in results)
    total = lambda pick: sum(share * pick(m) for _, share, m in each)
    expert_chords = total(lambda m: m["chord"]["expert_chords"]) or 1
    reading_chords = total(lambda m: m["chord"]["reading_chords"]) or 1
    expert_changes = total(lambda m: m["changes"]["expert"]) or 1
    return {
        "pieces": len(results),
        "bars": weight,
        "time": {level: sum(bars * share * m["time"][level] for bars, share, m in each) / weight for level in LEVELS},
        "recall": {level: total(lambda m: m["chord"]["recall"][level]) / expert_chords for level in LEVELS},
        "precision": {level: total(lambda m: m["chord"]["precision"][level]) / reading_chords for level in LEVELS},
        "changes per 100": {key: 100 * total(lambda m: m["changes"][key]) / expert_changes for key in ("shared", "missed", "extra")},
        "reading fit": sum(bars * share * m["fit"]["inside"] / m["fit"]["total"] for bars, share, m in each if m["fit"]["total"]) / weight,
    }


def per_piece(entry: dict, arm: str) -> list[dict]:
    if arm == "experts":
        return [m for both in entry["pairs"].values() for m in both]
    return list(entry[arm].values())


def gap_interval(entries: list[dict], resamples: int = 2000) -> dict:
    rows = [(e["bars"], pool([(e["bars"], per_piece(e, "ours"))]), pool([(e["bars"], per_piece(e, "experts"))])) for e in entries]
    generator = random.Random(0)
    samples = [generator.choices(rows, k=len(rows)) for _ in range(resamples)]
    out = {}
    for measure in ("time", "recall", "precision"):
        for level in HEADLINE:
            gap = lambda sample: sum(w * (o[measure][level] - x[measure][level]) for w, o, x in sample) / sum(w for w, _, _ in sample)
            spread = sorted(gap(sample) for sample in samples)
            out[f"{measure} {level}"] = [round(gap(rows), 3), round(spread[int(0.025 * resamples)], 3), round(spread[int(0.975 * resamples)], 3)]
    return out


def cadence_total(entries: list[dict]) -> dict:
    found = [e["cadences"] for e in entries if "cadences" in e and e["expert_marking"]["complete"]]
    total = {key: sum(c[key] for c in found) for key in ("expert", "ours", "same place and type", "same place, any type", "ours with no expert cadence")}
    return {"pieces": len(found), "left out (expert marks under half its phrase ends)": sum("cadences" in e and not e["expert_marking"]["complete"] for e in entries), **total,
            "same place and type, share": total["same place and type"] / total["expert"] if total["expert"] else None,
            "same place, share": total["same place, any type"] / total["expert"] if total["expert"] else None,
            "ours with no expert cadence, share": total["ours with no expert cadence"] / total["ours"] if total["ours"] else None}


def summary(entries: dict, pairs: list[dict] | None) -> dict:
    scored = [e for e in entries.values() if "skipped" not in e]
    out = {}
    for group in sorted({e["style"] for e in scored}) + ["all"]:
        mine = [e for e in scored if group in ("all", e["style"])]
        row = {arm: pool([(e["bars"], per_piece(e, arm)) for e in mine if arm in e]) for arm in ("ours", "draft") if any(arm in e for e in mine)}
        if pairs is None:
            row["experts"] = pool([(e["bars"], per_piece(e, "experts")) for e in mine])
            if "ours" in row:
                row["ours minus experts"] = gap_interval([e for e in mine if "ours" in e])
        else:
            theirs = [p for p in pairs if group == "all" or p["style"] == group]
            if theirs:
                row["experts (all pairs of the style)"] = pool([(p["bars"], p["both"]) for p in theirs])
        row["cadences"] = cadence_total(mine)
        out[group] = row
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", default="heldout", choices=sorted(pieces.SETS))
    parser.add_argument("--reviewed", type=Path, help="folder of reviewed annotation lists, <id>.json; without it only the draft is scored")
    parser.add_argument("--only", action="append", help="score only this piece (repeatable)")
    args = parser.parse_args()
    paths = set(pieces.rome_tree())
    rome = ({folder: files for folder, files, _ in ceiling.candidates(paths)}, paths)
    entries = {}
    for piece in [pieces.BY_ID[name] for name in args.only] if args.only else pieces.SETS[args.set]:
        entries[piece.id] = entry = piece_report(piece, args.reviewed, rome)
        if "skipped" not in entry and "ours" in entry:
            m = pool([(entry["bars"], per_piece(entry, "ours"))])
            print(f"{piece.id:50s} {entry['bars']:4d} bars  ours " + "  ".join(f"{level[:5]} {m['time'][level]:.2f}/{m['recall'][level]:.2f}/{m['precision'][level]:.2f}" for level in HEADLINE), flush=True)
    report = {"pieces": entries, "summary": summary(entries, None if args.set == "multi" else expert_pairs())}
    name = args.reviewed.name if args.reviewed else "draft"
    (pieces.OUT / f"ladder-{args.set}-{name}.json").write_text(json.dumps(report, indent=1, default=str))
    for group, row in report["summary"].items():
        for arm, s in row.items():
            if "time" in s:
                print(f"{group:22s} {arm:34s} {s['pieces']:4d} {s['bars']:6d}  " + "  ".join(f"{level[:5]} {s['time'][level]:.3f}/{s['recall'][level]:.3f}/{s['precision'][level]:.3f}" for level in HEADLINE)
                      + "  changes " + "/".join(f"{v:.0f}" for v in s["changes per 100"].values()) + f"  fit {s['reading fit']:.3f}")
        print(f"{group:22s} cadences {row['cadences']}")


if __name__ == "__main__":
    main()
