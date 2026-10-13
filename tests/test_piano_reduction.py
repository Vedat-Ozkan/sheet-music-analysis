"""The piano reduction against the original parts, bar by bar, on real scores."""
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest
from music21 import converter, stream

from engine import piano
from tools.robustness import CORPUS

# Dvořák 9 and Mozart 41 from the MIT-licensed MCTL symphony set (tools/engraving_check.py), Haydn 104 from
# When in Rome (eval/pieces.py), stored here so the tests run on a clean checkout.
SCORES = Path(__file__).parent / "data" / "piano"
CORPUS_SCORES = {"mozart-k458": "mozart/k458/movement1.mxl", "beethoven-59-1": "beethoven/opus59no1/movement1.mxl"}


def _score(name: str) -> bytes:
    if name in CORPUS_SCORES:
        return (CORPUS / CORPUS_SCORES[name]).read_bytes()
    return (SCORES / f"{name}.mxl").read_bytes()


def _parse(data: bytes):
    with tempfile.NamedTemporaryFile(suffix=".mxl" if data[:2] == b"PK" else ".musicxml") as file:
        file.write(data)
        file.flush()
        return converter.parse(file.name, format="musicxml")


@lru_cache(maxsize=None)
def _both(name: str, first: int, last: int):
    data = _score(name)
    return _parse(data).toSoundingPitch(), _parse(piano.reduce(data, (first, last)))


def _notes(part, number: int, offsets_in=None):
    """(offset, length, pitch, tie type) of every note sounding in bar `number` of one part, offsets from the bar
    start or from the start of `offsets_in`."""
    measure = next(m for m in part.getElementsByClass(stream.Measure) if m.number == number)
    def tie(n, p):
        t = n.getTie(p) if n.isChord else n.tie
        return t.type if t else None

    return [
        (float(n.getOffsetInHierarchy(offsets_in if offsets_in is not None else measure)), float(n.quarterLength), p.ps, tie(n, p))
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
    """A held bass is written once, as its own voice, not tied through every chord above it. (In bars 11-12 the second
    violins' A-flat is tied once, held under the clarinets' eighths.)"""
    _, reduced = _both("dvorak-9-2", 5, 12)
    for number in range(5, 13):
        bass = min(ps for _, _, ps, _ in _notes(reduced.parts[1], number))
        tied = _tied_pairs(reduced.parts[1], number)
        assert all(ps != bass for ps, _ in tied) and len(tied) <= 1, (number, tied)


OPENINGS = [("mozart-k458", 0, 40), ("mozart-41", 1, 40), ("dvorak-9-2", 1, 40), ("beethoven-59-1", 1, 40), ("haydn-104", 1, 40)]


@pytest.mark.parametrize("name,first,last", OPENINGS)
def test_every_tie_lands_and_every_voice_fills_its_bar(name, first, last):
    """A held note keeps its octave and staff to its end, so each tie reaches the same pitch on the same staff."""
    original, reduced = _both(name, first, last)
    for part in reduced.parts:
        heads = [(start, start + length, ps, tie) for number in range(first, last + 1)
                 for start, length, ps, tie in _notes(part, number, offsets_in=part)]
        # Triplet offsets come back from MusicXML as rounded floats.
        heads = [(round(s, 4), round(e, 4), ps, t) for s, e, ps, t in heads]
        starts = {(s, ps) for s, _, ps, t in heads if t in ("stop", "continue")}
        ends = {(e, ps) for _, e, ps, t in heads if t in ("start", "continue")}
        bars = list(part.getElementsByClass(stream.Measure))
        outside = (round(float(bars[0].offset), 4), round(float(bars[-1].offset + bars[-1].quarterLength), 4))
        for s, e, ps, t in heads:
            if t in ("start", "continue"):
                assert (e, ps) in starts or e == outside[1], (name, s, ps)
            if t in ("stop", "continue"):
                assert (s, ps) in ends or s == outside[0], (name, s, ps)
        for measure in bars:
            length = float(original.parts[0].measure(measure.number).quarterLength)
            for voice in list(measure.voices) or [measure]:
                time = 0.0
                # The exporter pads a pickup bar with hidden rests after its music.
                for e in [e for e in voice.notesAndRests if float(e.offset) < length]:
                    assert float(e.offset) == pytest.approx(time), (name, measure.number)
                    time = float(e.offset + e.quarterLength)
                assert time == pytest.approx(length), (name, measure.number)


@pytest.mark.parametrize("name,first,last", OPENINGS)
def test_no_note_of_the_original_is_lost(name, first, last):
    """Every note of the score sounds in the piano version for its whole length, in some octave: only unisons and
    octave doublings are merged away (K.458 bar 1 lost its second violin and viola in thirds and sixths)."""
    original, reduced = _both(name, first, last)
    for number in range(first, last + 1):
        here = [n for part in reduced.parts for n in _notes(part, number)]
        for part in original.parts:
            for start, length, ps, _ in _notes(part, number):
                for k in range(int(length * 12)):
                    t = start + (k + 0.5) / 12
                    assert any(p % 12 == ps % 12 and o <= t < o + d for o, d, p, _ in here), (name, number, start, ps)
