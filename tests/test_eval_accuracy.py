from pathlib import Path

import pytest
from music21 import corpus

from engine.comparison import Label, from_romantext
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval.accuracy import METRICS, aggregate, score_readings


def test_catalogue_covers_all_real_analysis_folders():
    from eval.unseen import catalogue_readings

    root = Path("/tmp/claude-1000/codex/03z-eval-free-steps/data/When-in-Rome/Corpus")
    if not root.exists():
        pytest.skip("expanded evaluation corpus is not installed")
    folders = {p.parent for p in root.rglob("analysis*.txt") if "Kostka" not in str(p)}
    readings = catalogue_readings(root)
    assert {p.parent for p in readings} == folders
    assert len(readings) == len(folders)
    for path in readings:
        assert path.exists()
        assert path.name == "analysis.txt" or not (path.parent / "analysis.txt").exists()


@pytest.fixture(scope="module")
def real_readings():
    root = Path(corpus.__file__).parent
    result = []
    for number, bwv in ((1, "269"), (2, "347")):
        index = ScoreIndex(load_toolkit((root / f"bach/bwv{bwv}.mxl").read_bytes()).getMEI())
        labels = from_romantext((root / f"bach/choraleAnalyses/riemenschneider{number:03d}.rntxt").read_text())
        result.append((index, labels))
    return result


def test_two_real_chorales_duration_beats_and_exact_labels(real_readings):
    rows = []
    for number, (index, labels) in enumerate(real_readings):
        same = [Label(l.measure, l.beat, l.key, l.figure.replace("65", "6/5").replace("43", "4/3")) for l in labels]
        scores = score_readings(labels, same, index)
        assert scores["duration_weight"] > 0
        assert scores["beat_weight"] > 0
        for mode in ("duration", "beat"):
            assert scores[mode] == dict.fromkeys(METRICS, 1)
        missing = score_readings(labels, [], index)
        assert missing["duration"] == dict.fromkeys(METRICS, 0)
        assert missing["beat"] == dict.fromkeys(METRICS, 0)
        rows.append(dict(piece=str(number), bars=len(index.measures), **(scores if number == 0 else missing)))
    summary = aggregate(rows, resamples=100)
    for mode in ("duration", "beat"):
        expected = rows[0][mode + "_weight"] / sum(r[mode + "_weight"] for r in rows)
        assert summary[mode]["full"]["pooled"] == pytest.approx(expected)
        assert summary[mode]["full"]["piece_mean"] == .5
        assert summary[mode]["full"]["pooled_ci95"] == [0, 1]


def test_all_real_references_reject_labels_outside_score(real_readings):
    for index, labels in real_readings:
        outside = Label(max(m.number for m in index.measures) + 1, 1, labels[-1].key, labels[-1].figure)
        with pytest.raises(ValueError, match="outside the score"):
            score_readings(labels + [outside], labels, index)
        with pytest.raises(ValueError, match="outside the score"):
            score_readings(labels, labels + [outside], index, common=True)


def test_either_expert_agreement_on_two_real_pieces(real_readings):
    from eval.accuracy import agrees_with_any

    for index, labels in real_readings:
        other = [Label(l.measure, l.beat, l.key, "V" if l.figure != "V" else "I") for l in labels]
        result = agrees_with_any(labels, [other, labels], index)
        assert result["duration_full"] == 1
        assert result["beat_full"] == 1
        absent = agrees_with_any([], [labels, other], index)
        assert absent["duration_full"] == 0
        assert absent["beat_full"] == 0


def test_all_real_references_reject_unreadable_chords(real_readings):
    for index, labels in real_readings:
        first = labels[0]
        broken = [Label(first.measure, first.beat, first.key, "not-a-chord"), *labels[1:]]
        with pytest.raises(ValueError, match="unreadable"):
            score_readings(broken, labels, index)
        with pytest.raises(ValueError, match="unreadable"):
            score_readings(labels, broken, index, common=True)


def test_same_real_music_is_one_bootstrap_cluster(real_readings):
    rows = []
    for number, (index, labels) in enumerate(real_readings):
        scores = score_readings(labels, labels if number == 0 else [], index)
        rows.append(dict(piece=str(number), cluster=str(number), **scores))
    expected = aggregate(rows, resamples=100)
    alias = dict(rows[0], piece="another catalogue number")
    actual = aggregate([*rows, alias], resamples=100)
    assert actual["pieces"] == 2
    assert actual["duration"]["full"] == expected["duration"]["full"]
    assert actual["beat"]["full"] == expected["beat"]["full"]


def test_all_real_chorale_readings_preserve_incomplete_bar_positions():
    from fractions import Fraction
    from engine.comparison import Timeline
    from eval.accuracy import labelled_spans

    root = Path(corpus.__file__).parent / "bach"
    checked = 0
    for path in sorted((root / "choraleAnalyses").glob("riemenschneider*.rntxt")):
        score = corpus.chorales.ChoraleListRKBWV().byRiemenschneider[int(path.stem[-3:])]["bwv"]
        index = ScoreIndex(load_toolkit((root / f"bwv{score}.mxl").read_bytes()).getMEI())
        timeline = Timeline(index)
        labels = from_romantext(path.read_text())
        for number, measure in timeline.measures.items():
            if measure.declared_length is not None:
                continue
            within = [l for l in labels if l.measure == number]
            if not within:
                continue
            offsets = [(Fraction(l.beat).limit_denominator(96) - 1) * measure.beat_length for l in within]
            if max(offsets) >= measure.length:
                continue
            checked += 1
            spans, _ = timeline.spans(within)
            exact = labelled_spans(timeline, within)
            expected = sorted({timeline.starts[number] + offset for offset in offsets})
            assert [s[0] for s in spans] == expected, (path.name, number)
            assert [s[0] for s in exact] == expected, (path.name, number)
            for position, label in enumerate(within):
                if any(l.beat == label.beat for l in within[position + 1:]):
                    continue
                changed = [Label(l.measure, l.beat, l.key, "IV" if l.figure != "IV" else "V") if l == label else l for l in within]
                result = score_readings(within, changed, index)
                assert result["duration"]["exact_label"] < 1, (path.name, label)
            count, unit = measure.meter.split("/")
            padding = Fraction(int(count) * 4, int(unit)) - measure.length
            if padding > 0 and max(offsets) + padding >= measure.length:
                shifted = [Label(l.measure, l.beat + float(padding / measure.beat_length), l.key, l.figure) for l in within]
                assert timeline.spans(shifted) == timeline.spans(within)
                assert labelled_spans(timeline, shifted) == exact
    assert checked > 0


def test_all_real_catalogue_sources_require_evidence_for_merging():
    import json
    from eval.independent import independent_readings

    root = Path("/tmp/claude-1000/codex/03z-eval-free-steps/data/When-in-Rome/Corpus")
    if not root.exists():
        pytest.skip("expanded evaluation corpus is not installed")
    for folder in sorted({p.parent for p in root.rglob("analysis*.txt")}):
        remote = json.loads((folder / "remote.json").read_text()) if (folder / "remote.json").exists() else {}
        selected, excluded = independent_readings(folder, remote)
        by_name = {r["file"]: r for r in selected}
        for entry in excluded:
            if not entry["reason"].startswith("same source as "):
                continue
            original = by_name[entry["reason"].removeprefix("same source as ")]
            if entry["family"] == "TAOM" and entry["analyst"] and original["analyst"]:
                assert entry["analyst"] == original["analyst"] or (entry["source"] and entry["source"] == original["source"]), folder
