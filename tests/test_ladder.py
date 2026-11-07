from fractions import Fraction
from pathlib import Path

from engine.comparison import Label, Timeline
from engine.render import load_toolkit
from engine.score import ScoreIndex
from eval import ladder

ROOT = Path(__file__).parent.parent


def test_a_skipped_short_chord_costs_more_by_chord_than_by_time():
    index = ScoreIndex(load_toolkit((ROOT / 'tests/data/cadential_64.musicxml').read_bytes()).getMEI())
    timeline = Timeline(index)
    expert = [Label(1, 1, 'C', 'I'), Label(1, 4, 'C', 'V'), Label(2, 1, 'C', 'I'), Label(3, 1, 'C', 'IV')]
    reading = [Label(1, 1, 'C', 'I'), Label(3, 1, 'C', 'IV')]
    windows = [(timeline.starts[1], timeline.starts[2] + timeline.measures[2].length)]

    found = ladder.measures(expert, reading, index, timeline, [(1, 2)], windows)

    assert found['time']['full'] == 0.875
    assert found['chord']['expert_chords'] == 3
    assert found['chord']['recall']['full'] == 2
    assert found['chord']['precision']['full'] == 1
    assert found['changes'] == {'expert': 2, 'shared': 0, 'missed': 2, 'extra': 0}


def test_cadences_count_within_a_beat_and_keep_extra_marks_apart():
    index = ScoreIndex(load_toolkit((ROOT / 'tests/data/cadential_64.musicxml').read_bytes()).getMEI())
    timeline = Timeline(index)
    windows = [(Fraction(0), timeline.total)]
    expert = [(timeline.starts[2], 'PAC'), (timeline.starts[4], 'HC')]
    ours = ladder.our_cadences([{'type': 'cadence', 'at': {'measure': 2, 'beat': 1}, 'label': 'PAC'}, {'type': 'cadence', 'at': {'measure': 3, 'beat': 4}, 'label': 'HC'}, {'type': 'cadence', 'at': {'measure': 1, 'beat': 2}, 'label': 'IAC'}], timeline)

    found = ladder.cadence_counts(expert, ours, windows, timeline)

    assert found == {'expert': 2, 'ours': 3, 'same place and type': 2, 'same place, any type': 2, 'ours with no expert cadence': 1}
