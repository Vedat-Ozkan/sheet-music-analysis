import collections
import io
import os
from pathlib import Path

import pytest
from PIL import Image

from engine.read_pdf import SETTINGS, clean, is_scan, notice, open_pdf, problem_spots, read_pdf, without_slurs
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

    assert problem_spots(score) == ([12, 18], [(16, "G", "double sharp")])
    assert b"<slur" not in score
    assert notice(score, False, [], False) == (
        "This is what I read from your PDF; check it against your copy before I analyse it. Bars 12 and 18 don't add "
        "up to a full bar, so a note or triplet may be misread there. Bar 16: the G has a double sharp, which is rare; "
        "please check it. Slurs are left out, because they are often misread from PDFs; ask if you want them kept."
    )


def test_names_bars_with_durations_that_disagree_with_written_notes():
    # The production reading lost the singer's initial divisions. These bars have
    # wrong onsets against the benchmark truth but escaped the voice-total check.
    score = (Path(__file__).parent / 'data/pdf_warnings/schubert_die_stadt_audiveris.musicxml').read_bytes()
    uneven, doubles = problem_spots(score)
    assert {5, 7, 8, 10, 11} <= set(uneven)
    assert doubles == []
    assert 'Bars 1, 5, 6, 7 and 13 more' in notice(score, False, [], False)


def test_accepts_the_correct_schubert_with_dots_and_triplets():
    score = clean((Path(__file__).parent / 'data/pdf_warnings/schubert_die_stadt.mxl').read_bytes())
    assert problem_spots(score) == ([], [])


@pytest.mark.parametrize('filename', ['haydn_she_never_told_audiveris.musicxml',
                                     'lang_auf_der_reise_audiveris.musicxml'])
def test_names_bars_whose_backup_runs_before_the_start(filename):
    # Both production readings lose notes in bar 1, leaving their second voices
    # backed up beyond the start; their individual voice totals still look valid.
    score = (Path(__file__).parent / 'data/pdf_warnings' / filename).read_bytes()
    assert 1 in problem_spots(score)[0]
    assert "Bars 1," in notice(score, False, [], False)


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
    assert problem_spots(score) == ([], [])
