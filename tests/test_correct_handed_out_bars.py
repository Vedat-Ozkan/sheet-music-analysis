from pathlib import Path

import pytest

from engine import correct

DATA = Path(__file__).parent / "data"
LONG_VOICE = DATA / "correct_voice_longer_than_bar.musicxml"


def index(score, part):
    return correct._read(score, part)[2]


def voices(bar):
    found = {}
    for event in (event for event in bar.events if event.pitch):
        found.setdefault((event.staff, event.layer), []).append((event.onset, event.duration, event.pitch, event.grace, event.tied))
    return found


def test_a_bar_with_a_voice_longer_than_the_bar_can_be_corrected_in_another_voice():
    score = LONG_VOICE.read_bytes()
    handed_out = correct.bars_from_musicxml(score, 6, part="P2")
    assert "1.3: 8 r 3 C4" in handed_out
    result = correct.replace_bars(score, handed_out.replace("1.2: 4 r 3 D#4 1 E4", "1.2: 4 r 3 D#4 1 F4"), part="P2")
    before, after = voices(index(score, "P2").measure(6)), voices(index(result, "P2").measure(6))
    assert [pitch for _, _, pitch, *_ in after[(1, 2)] if pitch] == ["D#4", "F4"]
    assert {key: events for key, events in after.items() if key != (1, 2)} == {key: events for key, events in before.items() if key != (1, 2)}


def test_a_bar_without_a_usable_length_is_handed_out_and_accepted_unchanged():
    score = (DATA / "movements" / "choral-songs-02-invalid-page-2.mxl").read_bytes()
    handed_out = correct.bars_from_musicxml(score, 14, part="P1")
    assert handed_out.splitlines()[1:] == ["m14 len=0"]
    assert correct.replace_bars(score, handed_out, part="P1")


def test_one_part_of_an_orchestral_score_can_be_opened_and_handed_out():
    score = (DATA / "piano" / "mozart-41.mxl").read_bytes()
    assert correct.bars_from_musicxml(score, 1, part="P1").startswith("N1 div=")


def test_a_voice_handed_out_too_long_may_change_pitch_but_not_length():
    score = LONG_VOICE.read_bytes()
    handed_out = correct.bars_from_musicxml(score, 6, part="P2")
    result = correct.replace_bars(score, handed_out.replace("1.1: 4 r 1 A4", "1.1: 4 r 1 B4"), part="P2")
    before, after = voices(index(score, "P2").measure(6)), voices(index(result, "P2").measure(6))
    assert [(onset, duration) for onset, duration, *_ in after[(1, 1)]] == [(onset, duration) for onset, duration, *_ in before[(1, 1)]]
    assert [pitch for _, _, pitch, *_ in after[(1, 1)]][0] == "B4"
    assert {key: events for key, events in after.items() if key != (1, 1)} == {key: events for key, events in before.items() if key != (1, 1)}
    shorter = handed_out.replace("1.1: 4 r 1 A4 A3 2 A4~ 1 A4 A3", "1.1: 4 r 1 A4 A3 2 A4~ 1 A4")
    with pytest.raises(correct.CorrectionError, match="voice 1.1 adds up to 9/2"):
        correct.replace_bars(score, shorter, part="P2")
