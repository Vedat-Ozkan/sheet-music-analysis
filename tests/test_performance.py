from pathlib import Path

import pytest
from music21 import midi

from engine.export import export_midi
from engine import notes as note_list
from engine.performance import marked_index, perform, performance_text

DATA = Path(__file__).parent / "data"
NOCTURNE = DATA / "chopin_nocturne_op9_no2_pdmx.mxl"

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
def nocturne():
    return NOCTURNE.read_bytes()


@pytest.fixture(scope="module")
def opening(nocturne):
    return export_midi(nocturne, (1, 8))


def test_only_the_chosen_bars_are_played(opening):
    assert 48_000 < timeline(opening)[-1][0] < 52_000


def test_the_sustain_pedal_is_kept(opening):
    pedal = [event.parameter2 for _, event in timeline(opening) if event.type == CONTROLLER and event.parameter1 == 64]
    assert 127 in pedal and 0 in pedal


def test_dynamics_and_hairpins_change_the_loudness(opening):
    assert len({velocity for _, _, velocity in onsets(opening)}) > 5


def fast_runs(notes, lowest, slowest=130):
    top = [(time, pitch) for time, pitch, _ in notes if pitch >= lowest]
    runs, current = [], [top[0][1]]
    for (before, previous), (time, pitch) in zip(top, top[1:]):
        if 40 <= time - before <= slowest and abs(pitch - previous) <= 3:
            current.append(pitch)
        else:
            if len(current) > 2:
                runs.append(current)
            current = [pitch]
    return runs + [current] * (len(current) > 2)


def test_ornaments_are_played_out(nocturne):
    starts = [run[:4] for run in fast_runs(onsets(export_midi(nocturne)), 70)]
    assert any(start[:3] == [77, 79, 77] for start in starts)
    assert [75, 74, 75, 77] in starts
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


def test_a_romantic_turn_starts_on_its_note_and_dips_a_semitone_below():
    runs = fast_runs(onsets(export_midi((DATA / "chopin_nocturne_op9_no2.mxl").read_bytes(), (1, 4))), 70, slowest=200)
    assert [72, 73, 72, 71, 72] in [run[:5] for run in runs]


def test_a_turn_dips_a_semitone_below_unless_the_score_prints_another_note():
    runs = fast_runs(onsets(export_midi((DATA / "ornament_accidentals.musicxml").read_bytes())), 60, slowest=300)
    assert [71, 69, 68, 69] in [run[:4] for run in runs]
    assert [74, 72, 70, 72] in [run[:4] for run in runs]


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


def test_the_performance_text_holds_the_same_notes_as_the_midi(nocturne, opening):
    played = read_text(performance_text(marked_index(nocturne), (1, 8)))
    midi = sorted(onsets(opening), key=lambda note: (note[0], note[1]))
    assert [pitch for _, _, pitch, _ in played] == [pitch for _, pitch, _ in midi]
    assert all(abs(start - time) <= 10 for (start, *_), (time, _, _) in zip(played, midi))


def test_notes_released_under_the_pedal_ring_until_it_lifts(nocturne):
    lengths = [end - start for start, end, _, _ in read_text(performance_text(marked_index(nocturne), (1, 1)))]
    assert max(lengths) >= 2_500


def test_the_note_list_carries_everything_the_performance_needs(nocturne):
    index = marked_index(nocturne)
    relayed = note_list.decode(note_list.encode(index))
    assert performance_text(relayed) == performance_text(index)


def test_a_tempo_word_sets_the_speed_when_there_is_no_metronome_mark():
    plain = (DATA / "ornament_accidentals.musicxml").read_bytes()
    worded = plain.replace(b"<note><pitch><step>F</step>", b"<direction placement=\"above\"><direction-type><words>Adagio</words></direction-type></direction><note><pitch><step>F</step>", 1)
    assert timeline(export_midi(plain))[-1][0] == 6_000
    assert timeline(export_midi(worded))[-1][0] == round(6_000 * 120 / 66)


def test_a_pedal_printed_just_before_the_barline_reads_back():
    index = marked_index((DATA / "chopin_ballade_op23_pdmx.mxl").read_bytes())
    pedals = [(mark.offset, mark.value) for mark in note_list.decode(note_list.encode(index, 246, 246)).measures[0].marks if mark.kind == "pedal"]
    assert (0, "down") in pedals


def test_a_trill_after_a_key_change_takes_its_upper_note_from_the_new_key():
    played, _, _ = perform(marked_index((DATA / "piano" / "dvorak-9-2.mxl").read_bytes()), (91, 91))
    pitches = {note.pitch for note in played}
    assert {82, 85} <= pitches
