"""The piano reduction against the original parts, bar by bar, on real scores."""
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest
from music21 import converter, stream

from engine import piano
from tools.robustness import CORPUS

SCORES = Path(__file__).parent.parent / "out" / "engraving" / "scores"


def _score(name: str) -> bytes:
    if name == "mozart-k458":
        return (CORPUS / "mozart/k458/movement1.mxl").read_bytes()
    path = next(iter(SCORES.glob(f"{name}.*")), None)
    if path is None:
        pytest.skip(f"ignored fixture missing: {name}")
    return path.read_bytes()


def _parse(data: bytes):
    with tempfile.NamedTemporaryFile(suffix=".mxl" if data[:2] == b"PK" else ".musicxml") as file:
        file.write(data)
        file.flush()
        return converter.parse(file.name, format="musicxml")


@lru_cache(maxsize=None)
def _both(name: str, first: int, last: int):
    data = _score(name)
    return _parse(data).toSoundingPitch(), _parse(piano.reduce(data, (first, last)))


def _notes(part, number: int):
    """(offset, length, pitch, tie type) of every note sounding in bar `number` of one part."""
    measure = next(m for m in part.getElementsByClass(stream.Measure) if m.number == number)
    def tie(n, p):
        t = n.getTie(p) if n.isChord else n.tie
        return t.type if t else None

    return [
        (float(n.getOffsetInHierarchy(measure)), float(n.quarterLength), p.ps, tie(n, p))
        for n in measure.recurse().notes
        for p in n.pitches
    ]


def _sounding(parts, number: int, step=0.25):
    """Pitches sounding at the middle of each slice of the bar."""
    notes = [n for part in parts for n in _notes(part, number)]
    bar = float(next(m for m in parts[0].getElementsByClass(stream.Measure) if m.number == number).barDuration.quarterLength)
    slices = {}
    for k in range(int(bar / step)):
        t = k * step + step / 2
        slices[k * step] = {ps for o, d, ps, _ in notes if o <= t < o + d}
    return slices


def _tied_pairs(part, number: int):
    """(pitch, end of the tied note) for every tie that starts inside the bar and ends inside it."""
    notes = _notes(part, number)
    return [(ps, o + d) for o, d, ps, tie in notes if tie in ("start", "continue") and any(
        ps2 == ps and abs(o2 - (o + d)) < 1e-6 and t2 in ("stop", "continue") for o2, _, ps2, t2 in notes)]


def test_melody_notes_keep_their_offsets():
    """K.458 bar 5: the tune stays where the violin plays it, so every voice fills the bar exactly."""
    original, reduced = _both("mozart-k458", 0, 8)
    measure = next(m for m in reduced.parts[0].getElementsByClass(stream.Measure) if m.number == 5)
    tune = {(o, ps) for o, d, ps, _ in _notes(original.parts[0], 5)}
    voices = [measure] + list(measure.voices)
    assert tune <= {(o, ps) for o, d, ps, _ in _notes(reduced.parts[0], 5)}
    for voice in measure.voices:
        assert sum(float(e.quarterLength) for e in voice.notesAndRests) == pytest.approx(3.0), voices


def test_bar_5_beams_follow_the_6_8_groups():
    """No beam joins the first dotted quarter of the bar to the second."""
    _, reduced = _both("mozart-k458", 0, 8)
    for part in reduced.parts:
        measure = next(m for m in part.getElementsByClass(stream.Measure) if m.number == 5)
        for voice in [measure, *measure.voices]:
            run = []
            for e in voice.notes:
                beam = e.beams.getByNumber(1) if e.beams.beamsList else None
                if beam is not None:
                    run.append(float(e.getOffsetInHierarchy(measure)))
                    if beam.type == "stop":
                        assert (min(run) < 1.5) == (max(run) < 1.5), run
                        run = []


def test_bar_8_has_the_originals_pitches_and_no_invented_ties():
    original, reduced = _both("mozart-k458", 0, 8)
    assert _sounding(reduced.parts, 8) == _sounding(original.parts, 8)
    # A tie is written only where one note of the original sounds across the change.
    for part in reduced.parts:
        for ps, end in _tied_pairs(part, 8):
            assert any(o < end < o + d and p == ps for orig in original.parts for o, d, p, _ in _notes(orig, 8)), (ps, end)


@pytest.mark.parametrize("name,first,last", [("dvorak-9-2", 5, 12), ("mozart-41", 1, 8)])
def test_the_lowest_line_of_the_original_is_kept(name, first, last):
    original, reduced = _both(name, first, last)
    for number in range(first, last + 1):
        before, after = _sounding(original.parts, number), _sounding(reduced.parts, number)
        for start, pitches in before.items():
            if pitches:
                assert min(pitches) in after[start], (number, start)


def test_dvorak_left_hand_is_not_chopped_up_by_ties():
    """A held bass is written once, as its own voice; a tie inside a bar is left only for a note the reduction
    could not write as one value."""
    _, reduced = _both("dvorak-9-2", 5, 12)
    for number in range(5, 13):
        assert _tied_pairs(reduced.parts[1], number) == [], number
