from engine.key_readings import alternatives
from engine.render import load_toolkit
from engine.score import ScoreIndex


def harmony(measure, beat, label, key=None):
    return {"type": "harmony", "at": {"measure": measure, "beat": beat}, "label": label, **({"key": key} if key else {})}


def test_short_key_area_and_applied_run_get_the_other_key_reading(chopin):
    index = ScoreIndex(load_toolkit(chopin).getMEI())
    short = [harmony(1, 1, "I", "Eb"), harmony(2, 1, "IV"), harmony(3, 1, "V7", "Bb"), harmony(3, 3, "I"), harmony(4, 1, "V7", "Eb"), harmony(5, 1, "I")]
    assert [a["label"] for a in alternatives(short, index)] == ["Eb: V7/V V"]
    run = [harmony(1, 1, "I", "Eb"), harmony(2, 1, "ii7/V"), harmony(2, 3, "V7/V"), harmony(3, 1, "viio7/V"), harmony(3, 3, "V"), harmony(4, 1, "V7"), harmony(5, 1, "I")]
    assert alternatives(run, index) == [{"type": "alternative", "start": {"measure": 2, "beat": 1}, "end": {"measure": 3, "beat": 3}, "label": "Bb: ii7 V7 viio7 I"}]
    minor = [harmony(1, 1, "i", "c"), harmony(2, 1, "V7", "bb"), harmony(2, 3, "i"), harmony(3, 1, "V7", "c"), harmony(4, 1, "i")]
    assert [a["label"] for a in alternatives(minor, index)] == ["c: V7/bvii bvii"]
