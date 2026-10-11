import collections
import io
import os
from pathlib import Path

import pytest
from PIL import Image

from engine.read_pdf import clean, is_scan, notice, open_pdf, problem_spots, read_pdf, without_slurs
from engine.render import engrave, load_toolkit
from engine.score import ScoreIndex

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
