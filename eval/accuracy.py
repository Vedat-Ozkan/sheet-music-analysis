"""Duration and beat metrics for local, CPU-only corpus evaluations."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import defaultdict
from fractions import Fraction

import numpy as np

from engine.comparison import Label, Timeline, matches, sounding

METRICS = ("key", "root", "chord", "chord_and_bass", "full", "exact_label")


def normalised_label(label: Label) -> tuple:
    chord = sounding(label.key, label.figure)
    figure = re.sub(r"(?<=\d)/(?=\d)", "", label.figure.replace("/o", "ø").replace("°", "o"))
    return (chord.tonic, chord.minor, figure) if chord else (label.key, figure)


def labelled_spans(timeline: Timeline, labels: list[Label]) -> list[tuple]:
    positions, _ = timeline.positions(labels)
    placed = [(start, sounding(label.key, label.figure), normalised_label(label)) for start, label in positions]
    ends = [item[0] for item in placed[1:]] + [timeline.total]
    return [(start, end, chord, label) for (start, chord, label), end in zip(placed, ends) if end > start]


def score_readings(reference: list[Label], reading: list[Label], index, *, common=False) -> dict:
    """Expert pairs use shared readable support; draft omissions count as disagreements."""
    timeline = Timeline(index)
    ref_spans, ref_missing = timeline.spans(reference)
    hyp_spans, hyp_missing = timeline.spans(reading)
    if ref_missing or (common and hyp_missing):
        raise ValueError("Reference labels outside the score would silently shorten the comparison")
    ref_unreadable = sum(sounding(l.key, l.figure) is None for l in reference)
    hyp_unreadable = sum(sounding(l.key, l.figure) is None for l in reading)
    if ref_unreadable or (common and hyp_unreadable):
        raise ValueError("Reference has unreadable chord labels")
    ref, hyp = labelled_spans(timeline, reference), labelled_spans(timeline, reading)
    starts = [[span[0] for span in spans] for spans in (ref, hyp)]

    def at(spans, beginnings, time):
        i = bisect_right(beginnings, time) - 1
        return spans[i][2:] if i >= 0 and time < spans[i][1] else (None, None)

    def agreement(time):
        r, rl = at(ref, starts[0], time)
        h, hl = at(hyp, starts[1], time)
        if r is None or (common and h is None):
            return None
        return dict(**matches(r, h), exact_label=rl == hl) if h else dict.fromkeys(METRICS, False)

    weights = {mode: dict.fromkeys(METRICS, Fraction(0)) for mode in ("duration", "beat")}
    denominators = dict.fromkeys(weights, Fraction(0))
    cuts = sorted({point for span in ref + hyp for point in span[:2]})
    for start, end in zip(cuts, cuts[1:]):
        agrees = agreement(start)
        if agrees is not None:
            denominators["duration"] += end - start
            for name, value in agrees.items():
                weights["duration"][name] += (end - start) * value
    for number, measure in timeline.measures.items():
        offset = Fraction(0)
        while offset < measure.length:
            agrees = agreement(timeline.starts[number] + offset)
            if agrees is not None:
                denominators["beat"] += 1
                for name, value in agrees.items():
                    weights["beat"][name] += value
            offset += measure.beat_length
    result = {}
    for mode, counts in weights.items():
        result[mode] = {name: float(value / denominators[mode]) if denominators[mode] else None for name, value in counts.items()}
        result[mode + "_weight"] = float(denominators[mode])
        result[mode + "_matches"] = {name: float(value) for name, value in counts.items()}
    result.update(reference_fit=timeline.fit(ref_spans), reading_fit=timeline.fit(hyp_spans),
                  reference_missing=ref_missing, reading_missing=hyp_missing,
                  reference_unreadable=ref_unreadable, reading_unreadable=hyp_unreadable,
                  score_duration=float(timeline.total))
    return result


def aggregate(rows: list[dict], *, seed=20261013, resamples=10000) -> dict:
    """Resample whole pieces, keeping multiple expert pairs in one cluster."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get("cluster", row["piece"])].append(row)
    result = {"pieces": len(grouped), "catalogue_pieces": len({r["piece"] for r in rows}),
              "comparisons": len(rows), "seed": seed, "resamples": resamples}
    if not rows:
        return result
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(grouped), size=(resamples, len(grouped)))
    for mode in ("duration", "beat"):
        # A work with several catalogue numbers or expert pairs must not gain extra duration.
        weight = np.array([np.mean([r[mode + "_weight"] for r in group]) for group in grouped.values()])
        values = np.array([[np.mean([r[mode + "_matches"][name] for r in group]) for name in METRICS] for group in grouped.values()])
        means = np.array([[np.mean([r[mode][name] for r in group]) for name in METRICS] for group in grouped.values()])
        pooled = values.sum(0) / weight.sum()
        boots = values[samples].sum(1) / weight[samples].sum(1)[:, None]
        piece_boots = means[samples].mean(1)
        result[mode] = {name: {"pooled": float(pooled[i]), "piece_mean": float(means[:, i].mean()),
                              "pooled_ci95": np.quantile(boots[:, i], [.025, .975]).tolist(),
                              "piece_mean_ci95": np.quantile(piece_boots[:, i], [.025, .975]).tolist()} for i, name in enumerate(METRICS)}
        result[mode + "_weight"] = float(weight.sum())
    return result


def agrees_with_any(reading: list[Label], references: list[list[Label]], index) -> dict:
    """Full agreement with either admissible expert on each stretch of music."""
    timeline = Timeline(index)
    if any(timeline.spans(labels)[1] for labels in references):
        raise ValueError("Reference labels outside the score")
    spans = [timeline.spans(labels)[0] for labels in [reading, *references]]
    starts = [[s for s, _, _ in row] for row in spans]

    def at(row, beginnings, time):
        i = bisect_right(beginnings, time) - 1
        return row[i][2] if i >= 0 and time < row[i][1] else None

    def agreement(time):
        hypothesis, *experts = [at(row, beginnings, time) for row, beginnings in zip(spans, starts)]
        experts = [r for r in experts if r is not None]
        if not experts:
            return None
        return hypothesis is not None and any(matches(r, hypothesis)["full"] for r in experts)

    duration = matched = Fraction(0)
    cuts = sorted({p for row in spans for s, e, _ in row for p in (s, e)})
    for start, end in zip(cuts, cuts[1:]):
        value = agreement(start)
        if value is not None:
            duration += end - start
            matched += (end - start) * value
    beats = beat_matches = 0
    for number, measure in timeline.measures.items():
        offset = Fraction(0)
        while offset < measure.length:
            value = agreement(timeline.starts[number] + offset)
            if value is not None:
                beats += 1
                beat_matches += value
            offset += measure.beat_length
    return dict(duration_weight=float(duration), duration_matches=float(matched),
                duration_full=float(matched / duration) if duration else None,
                beat_weight=beats, beat_matches=beat_matches, beat_full=beat_matches / beats if beats else None)
