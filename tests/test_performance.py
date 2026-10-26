from pathlib import Path

import pytest
from music21 import midi

from engine.export import export_midi

DATA = Path(__file__).parent / "data"

NOTE_ON, CONTROLLER = midi.ChannelVoiceMessages.NOTE_ON, midi.ChannelVoiceMessages.CONTROLLER_CHANGE


def timeline(data: bytes) -> list[tuple[int, midi.MidiEvent]]:
    file = midi.MidiFile()
    file.readstr(data)
    now, found = 0, []
    for event in file.tracks[0].events:
        if isinstance(event, midi.DeltaTime):
            now += event.time
        else:
            found.append((now, event))
    return found


def onsets(data: bytes) -> list[tuple[int, int, int]]:
    return [(time, event.pitch, event.velocity) for time, event in timeline(data) if event.type == NOTE_ON]


@pytest.fixture(scope="module")
def opening(chopin):
    return export_midi(chopin, (1, 8))


def test_only_the_chosen_bars_are_played(opening):
    assert 48_000 < timeline(opening)[-1][0] < 52_000


def test_the_sustain_pedal_is_kept(opening):
    pedal = [event.parameter2 for _, event in timeline(opening) if event.type == CONTROLLER and event.parameter1 == 64]
    assert 127 in pedal and 0 in pedal


def test_dynamics_and_hairpins_change_the_loudness(opening):
    assert len({velocity for _, _, velocity in onsets(opening)}) > 5


def fast_runs(notes, lowest):
    top = [(time, pitch) for time, pitch, _ in notes if pitch >= lowest]
    runs, current = [], [top[0][1]]
    for (before, previous), (time, pitch) in zip(top, top[1:]):
        if 40 <= time - before <= 130 and abs(pitch - previous) <= 3:
            current.append(pitch)
        else:
            if len(current) > 2:
                runs.append(current)
            current = [pitch]
    return runs + [current] * (len(current) > 2)


def test_ornaments_are_played_out(chopin):
    runs = fast_runs(onsets(export_midi(chopin)), 70)
    starts = [run[:4] for run in runs]
    assert any(start[:3] == [77, 79, 77] for start in starts)
    assert [74, 72, 70, 72] in starts
    assert any(start[:3] == [75, 77, 75] for start in starts)


@pytest.fixture(scope="module")
def bach_trills():
    return [run[:2] for run in fast_runs(onsets(export_midi((DATA / "ornament_accidentals.musicxml").read_bytes())), 60)]


def test_a_trill_in_bach_starts_on_the_upper_note(bach_trills):
    assert bach_trills[2] == [65, 64]


def test_an_accidental_earlier_in_the_bar_raises_the_upper_note(bach_trills):
    assert bach_trills[0] == [66, 64]


def test_an_accidental_printed_on_the_trill_sets_the_upper_note(bach_trills):
    assert bach_trills[1] == [70, 69]
