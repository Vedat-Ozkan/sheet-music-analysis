import collections
import gzip
import io
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from engine import tint
from engine.overlay import Box, PageLayout
from engine.read_pdf import PREVIEW_OPTIONS, SETTINGS, clean, is_scan, notice, number_bars, open_pdf, preview, problem_spots, _problem_spots, read_pdf, without_slurs
from engine.render import engrave, load_toolkit
from engine.score import ScoreIndex
from engine.triplets import infer_triplets

# Audiveris is not a Python package; point AUDIVERIS at its launcher, e.g. the spike's unpacked copy:
# AUDIVERIS=spike/omr/tools/audiveris-deb/x/opt/audiveris/bin/Audiveris
AUDIVERIS = os.environ.get("AUDIVERIS", "/opt/audiveris/bin/Audiveris")


def notes_and_left_hand_chords(score: bytes, first: int, last: int) -> tuple[int, int]:
    """What the analysis sees: notes after Verovio's import, and the left hand's chords (log 33: Verovio dropped
    nearly all of them from Audiveris's output while the MusicXML itself held every note)."""
    index = ScoreIndex(load_toolkit(score).getMEI())
    notes = [e for m in index.measures if first <= m.number <= last for e in m.events if e.pitch and not e.grace]
    onsets = collections.Counter((e.measure, e.onset) for e in notes if e.staff == 2)
    return len(notes), sum(1 for count in onsets.values() if count > 1)


@pytest.mark.skipif(not os.path.exists(AUDIVERIS), reason="Audiveris is not installed; set AUDIVERIS")
def test_reads_an_engraved_pdf_back_into_a_score(chopin):
    # Bars 9-12: here Audiveris's beamed chords made Verovio drop 29 of 137 notes before the clean-up.
    engraving = engrave(chopin, (9, 12))
    reading = read_pdf(engraving.pdf(), audiveris=AUDIVERIS)

    assert (reading.pages, reading.scan, reading.skipped) == (1, False, [])
    notes, chords = notes_and_left_hand_chords(chopin, 9, 12)  # 137 notes, 32 chords
    read_notes, read_chords = notes_and_left_hand_chords(reading.musicxml, 0, 99)
    assert abs(read_notes - notes) <= notes * 0.05
    assert read_chords >= chords - 2
    assert engrave(reading.musicxml).page_count == 1

    # The same page as a picture only, as a scanner makes it.
    picture = io.BytesIO()
    Image.open(io.BytesIO(engraving.png(1))).convert("RGB").save(picture, "PDF")
    assert is_scan(open_pdf(picture.getvalue()))


def test_names_the_bars_a_reading_likely_got_wrong():
    # Audiveris 5.11.0's reading of the Mutopia PDF of Chopin's Prelude Op. 28 No. 4. Against the original: bars 12
    # and 18 lost their triplets, and bar 16's turn became a double sharp on the G. Every other bar adds up.
    score = without_slurs(clean((Path(__file__).parent / "data/chopin_prelude_op28_no4_audiveris.mxl").read_bytes()))

    assert problem_spots(score) == ([12, 18], False)
    assert b"<slur" not in score
    assert notice(score, False, [], False) == (
        "This is what I read from your PDF; check it against your copy before I analyse it. Bars 12 and 18 (shaded) don't "
        "add up to a full bar, so a note or triplet may be misread there. "
        "Slurs are left out, because they are often misread from PDFs; ask if you want them kept."
    )


def test_names_bars_with_durations_that_disagree_with_written_notes():
    # The production reading lost the singer's initial divisions. These bars have
    # wrong onsets against the benchmark truth but escaped the voice-total check.
    score = (Path(__file__).parent / 'data/pdf_warnings/schubert_die_stadt_audiveris.musicxml').read_bytes()
    uneven, meter = problem_spots(score)
    assert {5, 7, 8, 10, 11} <= set(uneven)
    assert meter  # this part never had a time signature
    assert 'The shaded bars (1, 2, 3, 4 and 17 more) don' in notice(score, False, [], False)


def test_accepts_the_correct_schubert_with_dots_and_triplets():
    score = clean((Path(__file__).parent / 'data/pdf_warnings/schubert_die_stadt.mxl').read_bytes())
    assert problem_spots(score) == ([], False)


@pytest.mark.parametrize('filename', ['haydn_she_never_told_audiveris.musicxml',
                                     'lang_auf_der_reise_audiveris.musicxml'])
def test_names_bars_whose_backup_runs_before_the_start(filename):
    # Both production readings lose notes in bar 1, leaving their second voices
    # backed up beyond the start; their individual voice totals still look valid.
    score = (Path(__file__).parent / 'data/pdf_warnings' / filename).read_bytes()
    assert 1 in problem_spots(score)[0]
    assert "(1, " in notice(score, False, [], False)


def test_warning_signals_preserve_haydn_reading_selection():
    folder = Path(__file__).parent / 'data/pdf_warnings'
    variants = [(folder / f'haydn_she_never_told_variant{i}.mxl').read_bytes() for i in range(3)]

    def raw(data, audiveris, options, deadline):
        return variants[SETTINGS.index(options)], []

    # Extra warning signals reversed the ranking and lost 31 correct pitch/onset
    # events. Replay the real cached outputs through the production selection.
    reading = read_pdf((folder / 'haydn_she_never_told.pdf').read_bytes(), raw=raw)
    assert reading.musicxml == infer_triplets(clean(variants[1]))
    assert 1 in problem_spots(reading.musicxml)[0]


def test_fractional_durations_do_not_backup_before_the_bar():
    score = (Path(__file__).parent / 'data/pdf_warnings/fractional_durations.musicxml').read_bytes()
    assert problem_spots(score) == ([], False)


def test_preview_shades_the_named_bars_and_does_not_ring_the_double_sharp():
    score = without_slurs(clean((Path(__file__).parent / "data/chopin_prelude_op28_no4_audiveris.mxl").read_bytes()))
    svg = preview(score).svgs[0]
    # One pale-yellow tint per named bar (12 and 18), no ring (a turn written out as a double sharp is not a mistake), and a number on every bar.
    assert svg.count('fill="#FFE066" fill-opacity="0.35"') == 2
    assert "#B07800" not in svg
    assert {str(n) for n in range(2, 25)} <= set(re.findall(r'<(?:text|tspan)[^>]*>(\d+)</', svg))


def test_preview_bar_numbers_stay_clear_of_the_music():
    # A number on every bar is how "check bar 12" is followed; it must not print over a trill, volta or ledger note.
    score = without_slurs(clean((Path(__file__).parent / "data/chopin_prelude_op28_no4_audiveris.mxl").read_bytes()))
    toolkit = load_toolkit(score, PREVIEW_OPTIONS)
    index = ScoreIndex(toolkit.getMEI())
    layout = PageLayout(toolkit.renderToSVG(1), index)
    before = [list(system.content) for system in layout.systems]
    number_bars(layout, index)
    placed = 0
    for system, old in zip(layout.systems, before):
        for box in system.content[len(old):]:
            placed += 1
            core = Box(box.x + 21, box.y + 21, box.width - 42, box.height - 42)  # the number itself, without its reserved margin
            assert not any(o.x < core.right and o.right > core.x and o.y < core.bottom and o.bottom > core.y for o in old), core
    assert placed >= 15


def test_preview_bar_numbers_rise_above_the_barline_instead_of_moving_beside_noteheads():
    # Mozart K. 545 from a scan: where the space above a barline was taken, the number moved 200-400 units right, onto
    # the notes, where it reads as a fingering or tuplet number (bar 21 read "621").
    score = gzip.decompress((Path(__file__).parent / "data/pdf_warnings/mozart_k545_scan_reading.musicxml.gz").read_bytes())
    toolkit = load_toolkit(score, PREVIEW_OPTIONS)
    index = ScoreIndex(toolkit.getMEI())
    layout = PageLayout(toolkit.renderToSVG(1), index)
    before = [len(system.content) for system in layout.systems]
    number_bars(layout, index)
    starts = [m.x0 for m in layout.measures.values()]
    added = [box for system, n in zip(layout.systems, before) for box in system.content[n:]]
    assert len(added) >= 8
    assert all(min(abs(box.x + 21 - x) for x in starts) <= 100 for box in added)


def test_preview_draws_the_tint_between_the_staff_lines():
    score = without_slurs(clean((Path(__file__).parent / "data/chopin_prelude_op28_no4_audiveris.mxl").read_bytes()))
    # A shaded bar spans the staff lines exactly, not the ledger lines and marks above and below them.
    svg = preview(score).svgs[0]
    lines = {float(y) for y in re.findall(r'<path d="M[-\d.]+ ([-\d.]+) L', svg)}
    shaded = re.findall(r'<rect x="[-\d.]+" y="([-\d.]+)" width="[-\d.]+" height="([-\d.]+)" rx="0" fill="#FFE066"', svg)
    assert shaded
    for y, height in shaded:
        assert float(y) in lines and round(float(y) + float(height)) in {round(line) for line in lines}


def test_a_reading_with_no_problems_is_drawn_without_marks_but_with_every_bar_numbered():
    score = clean((Path(__file__).parent / "data/pdf_warnings/schubert_die_stadt.mxl").read_bytes())
    svg = preview(score).svgs[0]
    assert tint.FLAG_BAR not in svg and "bounding-box" not in svg
    assert {str(n) for n in range(2, 9)} <= set(re.findall(r'<(?:text|tspan)[^>]*>(\d+)</', svg))


def zipped(xml: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("score.xml", xml)
    return out.getvalue()


def test_a_reading_without_a_time_signature_is_checked_against_its_most_common_bar_length():
    # Mozart K. 545 from a scan: the "C" was read as a whole-note C5 and no meter was left. Without a meter no bar was
    # ever flagged, so no other settings were tried and the reading looked clean.
    score = gzip.decompress((Path(__file__).parent / "data/pdf_warnings/mozart_k545_scan_reading.musicxml.gz").read_bytes())
    uneven, guessed = problem_spots(score)
    assert guessed
    assert uneven
    assert _problem_spots(score, timing=False)[0]  # what ranks the readings and triggers the retry
    # The bar length cannot tell 6/8 from 3/4, so the notice does not name a meter.
    assert ("No time signature was read, so bars were checked against the most common bar length. "
            "The shaded bars") in notice(score, True, [], False)


def test_clean_drops_a_key_that_only_restates_the_current_one():
    # Audiveris restates the key at page breaks; the original has one key.
    reading = (Path(__file__).parent / "data/chopin_prelude_op28_no4_reading.musicxml").read_bytes()
    assert reading.count(b"<key") == 2
    assert clean(zipped(reading)).count(b"<key") == 1


def test_clean_keeps_the_home_key_returning_after_a_single_staff_key():
    # Schubert, Die Stadt (LilyPond PDF): the voice staff changes key at bars 3, 16, 18... and returns to three flats
    # for the whole part each time. Comparing that with a stale whole-part key dropped every return (bars 4, 17, 19...).
    raw = (Path(__file__).parent / "data/pdf_warnings/schubert_die_stadt_ly_raw.mxl").read_bytes()
    part = ET.fromstring(clean(raw)).findall("part")[1]
    returns = [m.get("number") for m in part.iter("measure") for k in m.findall("attributes/key")
               if k.get("number") is None and k.findtext("fifths") == "-3"]
    assert returns[:6] == ["0", "4", "17", "19", "21", "23"]


def test_clean_drops_endings_when_the_reading_has_no_repeat():
    reading = (Path(__file__).parent / "data/chopin_prelude_op28_no4_reading.musicxml").read_bytes()
    assert b"<ending" in reading and b"<repeat" not in reading
    assert b"<ending" not in clean(zipped(reading))


def test_clean_keeps_real_endings_where_there_are_repeats():
    reading = gzip.decompress((Path(__file__).parent / "data/pdf_warnings/joplin_maple_leaf_rag_reading.musicxml.gz").read_bytes())
    assert reading.count(b"<ending") == 14
    assert clean(zipped(reading)).count(b"<ending") == 14
