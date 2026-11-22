import gc
import tempfile
import xml.etree.ElementTree as ET
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import pytest
from music21 import converter, key, meter, stream

from engine import piano
from tools.robustness import CORPUS

SCORES = Path(__file__).parent / "data" / "piano"
CORPUS_SCORES = {"mozart-k458": "mozart/k458/movement1.mxl", "beethoven-59-1": "beethoven/opus59no1/movement1.mxl",
                 "weber-concertino": "weber/concertino_clarinet.mxl"}


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
    notes = [n for part in parts for n in _notes(part, number)]
    bar = float(next(m for m in parts[0].getElementsByClass(stream.Measure) if m.number == number).barDuration.quarterLength)
    slices = {}
    for k in range(int(bar / step)):
        t = k * step + step / 2
        slices[k * step] = {ps for o, d, ps, _ in notes if o <= t < o + d}
    return slices


def _tied_pairs(part, number: int):
    notes = _notes(part, number)
    return [(ps, o + d) for o, d, ps, tie in notes if tie in ("start", "continue") and any(
        ps2 == ps and abs(o2 - (o + d)) < 1e-6 and t2 in ("stop", "continue") for o2, _, ps2, t2 in notes)]


def test_melody_notes_keep_their_offsets():
    original, reduced = _both("mozart-k458", 0, 8)
    measure = next(m for m in reduced.parts[0].getElementsByClass(stream.Measure) if m.number == 5)
    tune = {(o, ps) for o, d, ps, _ in _notes(original.parts[0], 5)}
    voices = [measure] + list(measure.voices)
    assert tune <= {(o, ps) for o, d, ps, _ in _notes(reduced.parts[0], 5)}
    for voice in measure.voices:
        assert sum(float(e.quarterLength) for e in voice.notesAndRests) == pytest.approx(3.0), voices


def test_bar_5_beams_follow_the_6_8_groups():
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
    _, reduced = _both("dvorak-9-2", 5, 12)
    for number in range(5, 13):
        bass = min(ps for _, _, ps, _ in _notes(reduced.parts[1], number))
        tied = _tied_pairs(reduced.parts[1], number)
        assert all(ps != bass for ps, _ in tied) and len(tied) <= 1, (number, tied)


OPENINGS = [("mozart-k458", 0, 40), ("mozart-41", 1, 40), ("dvorak-9-2", 1, 40), ("beethoven-59-1", 1, 40), ("haydn-104", 1, 40)]


@pytest.mark.parametrize("name,first,last", OPENINGS)
def test_every_tie_lands_and_every_voice_fills_its_bar(name, first, last):
    original, reduced = _both(name, first, last)
    for part in reduced.parts:
        heads = [(start, start + length, ps, tie) for number in range(first, last + 1)
                 for start, length, ps, tie in _notes(part, number, offsets_in=part)]
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
                for e in [e for e in voice.notesAndRests if float(e.offset) < length]:
                    assert float(e.offset) == pytest.approx(time), (name, measure.number)
                    time = float(e.offset + e.quarterLength)
                assert time == pytest.approx(length), (name, measure.number)


@pytest.mark.parametrize("name,first,last", OPENINGS)
def test_no_note_of_the_original_is_lost(name, first, last):
    original, reduced = _both(name, first, last)
    for number in range(first, last + 1):
        here = [n for part in reduced.parts for n in _notes(part, number)]
        for part in original.parts:
            for start, length, ps, _ in _notes(part, number):
                for k in range(int(length * 12)):
                    t = start + (k + 0.5) / 12
                    assert any(p % 12 == ps % 12 and o <= t < o + d for o, d, p, _ in here), (name, number, start, ps)


def test_a_bar_whose_part_runs_past_its_time_signature_is_written_at_the_signatures_length():
    _, reduced = _both("weber-concertino", 1, 10)
    assert [float(m.quarterLength) for m in reduced.parts[0].getElementsByClass(stream.Measure)] == [3.0] * 10


def test_a_range_in_which_no_part_sounds_is_the_same_bars_of_rests():
    score = (Path(__file__).parent / "data/part_writing_motion.musicxml").read_bytes()
    reduced = converter.parse(piano.reduce(score, (24, 24)), format="musicxml")
    hands = list(reduced.parts)
    assert len(hands) == 2
    assert all(len(hand.getElementsByClass(stream.Measure)) == 1 and not hand.flatten().notes for hand in hands)


def test_the_opening_signatures_are_written_when_the_parsed_score_is_collected_before_the_bars_are_read(monkeypatch):
    score = (Path(__file__).parent / "data/part_writing_motion.musicxml").read_bytes()
    original = piano._parts

    def collected(data, positions):
        parts = original(data, positions)
        gc.collect()
        return parts

    monkeypatch.setattr(piano, "_parts", collected)
    reduced = converter.parse(piano.reduce(score, (3, 6)), format="musicxml")
    for hand in reduced.parts:
        first = hand.getElementsByClass(stream.Measure)[0]
        assert first.getElementsByClass(meter.TimeSignature) and first.getElementsByClass(key.KeySignature)


def test_a_score_whose_parts_share_a_name_is_drawn_with_the_notes_of_all_its_parts():
    data = (Path(__file__).parent / "data/triplet_mayer.musicxml").read_bytes()
    written = _parse(data).measures(1, 4).toSoundingPitch().flatten().pitches
    reduced = _parse(piano.reduce(data, (1, 4))).flatten().pitches
    assert (min(p.ps for p in reduced), max(p.ps for p in reduced)) == (min(p.ps for p in written), max(p.ps for p in written))


@pytest.mark.parametrize("path, first, last", [("piano/mozart-41.mxl", 1, 12), ("triplet_brahms_fruhlingstrost.musicxml", 1, 12)])
def test_the_piano_version_names_no_instruments(path, first, last):
    from engine.annotate import render
    from engine.annotations import AnnotationList

    engraving = render((Path(__file__).parent / "data" / path).read_bytes(), AnnotationList(annotations=[]), measures=(first, last), piano=True)
    assert not any('class="dir"' in svg for svg in engraving.svgs)


def _bars(score):
    return [list(part.getElementsByClass(stream.Measure)) for part in score.parts]


@pytest.mark.parametrize("path, first, last", [("triplet_brahms_fruhlingstrost.musicxml", 1, 6), ("triplet_mayer.musicxml", 1, 4)])
def test_the_piano_version_writes_only_lengths_a_musician_writes(path, first, last):
    data = (Path(__file__).parent / "data" / path).read_bytes()
    ratios = {(t.numberNotesActual, t.numberNotesNormal) for e in _parse(data).recurse().notesAndRests for t in e.duration.tuplets}
    grid = Fraction(1, 32)
    for hand in _bars(_parse(piano.reduce(data, (first, last)))):
        for bar in hand:
            for voice in bar.voices or [bar]:
                group = []
                for element in [*voice.notesAndRests, None]:
                    written = element.duration if element is not None else None
                    if written is not None and not (element.isRest and element.fullMeasure in (True, "always")):
                        assert written.dots <= 2 and written.type not in ("inexpressible", "complex"), (bar.number, element)
                    kind = [(t.numberNotesActual, t.numberNotesNormal) for t in written.tuplets] if written is not None else []
                    assert set(kind) <= ratios, (bar.number, element, kind)
                    if group and kind != group[0][0]:
                        start, end = Fraction(group[0][1].offset), Fraction(group[-1][1].offset) + Fraction(group[-1][1].quarterLength)
                        assert start % grid == 0 and end % grid == 0, (bar.number, start, end)
                        group = []
                    if kind:
                        group.append((kind, element))


@pytest.mark.parametrize("path, first, last", [("triplet_mayer.musicxml", 1, 4), ("movements/choral-songs-02-invalid-page-3.mxl", 46, 49),
                                               ("triplet_brahms_fruhlingstrost.musicxml", 37, 40), ("chopin_nocturne_op9_no2_pdmx.mxl", 31, 34)])
def test_both_hands_are_as_long_as_the_longest_part_of_each_bar(path, first, last):
    data = (Path(__file__).parent / "data" / path).read_bytes()
    source = _bars(_parse(data).measures(first, last))
    longest = [max(max((e.offset + e.quarterLength for e in bar.recurse().notesAndRests), default=0) for bar in bars) for bars in zip(*source)]
    for hand in _written_lengths(piano.reduce(data, (first, last))):
        assert hand == longest


def _written_lengths(xml: bytes) -> list[list[Fraction]]:
    hands = []
    for part in ET.fromstring(xml).iter("part"):
        lengths, divisions = [], 1
        for bar in part.iter("measure"):
            divisions = int(bar.findtext("attributes/divisions") or divisions)
            time = end = 0
            for child in bar:
                step = int(child.findtext("duration") or 0)
                if child.tag == "backup":
                    time -= step
                elif child.tag == "forward" or (child.tag == "note" and child.find("chord") is None):
                    time += step
                end = max(end, time)
            lengths.append(Fraction(end, divisions))
        hands.append(lengths)
    return hands


def test_a_reading_whose_parts_hold_different_bars_gets_no_piano_version():
    from engine.annotate import render
    from engine.annotations import AnnotationList

    data = (Path(__file__).parent / "data/pdf_warnings/schubert_die_stadt_audiveris.musicxml").read_bytes()
    for bars in ((2, 5), (10, 13)):
        with pytest.raises(piano.PianoError) as refused:
            render(data, AnnotationList(annotations=[]), measures=bars, piano=True)
        assert str(refused.value) == piano.PARTS_DO_NOT_LINE_UP
    assert render(data, AnnotationList(annotations=[]), measures=(2, 5)).page_count == 1
