from pathlib import Path

import pytest
from music21 import midi

from engine.export import export_midi
from engine import notes as note_list
from engine.performance import marked_index, performance_text

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


def read_text(text):
    notes, now, velocity = [], 0, None
    for token in text.split()[1:]:
        if token[0] == "v":
            velocity = int(token[1:])
            continue
        delta, length, pitch = (int(part) for part in token.split("."))
        now += delta * 10
        notes.append((now, now + length * 10, pitch, velocity))
    return notes


def test_the_performance_text_holds_the_same_notes_as_the_midi(chopin, opening):
    played = read_text(performance_text(marked_index(chopin), (1, 8)))
    midi = sorted(onsets(opening), key=lambda note: (note[0], note[1]))
    assert [pitch for _, _, pitch, _ in played] == [pitch for _, pitch, _ in midi]
    assert all(abs(start - time) <= 10 for (start, *_), (time, _, _) in zip(played, midi))


def test_notes_released_under_the_pedal_ring_until_it_lifts(chopin):
    lengths = [end - start for start, end, _, _ in read_text(performance_text(marked_index(chopin), (1, 1)))]
    assert max(lengths) >= 2_500


def test_the_note_list_carries_everything_the_performance_needs(chopin):
    index = marked_index(chopin)
    relayed = note_list.decode(note_list.encode(index))
    assert performance_text(relayed) == performance_text(index)
