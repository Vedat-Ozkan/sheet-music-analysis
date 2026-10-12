# Awkward inputs

Scores and typed answers that exercise the odd corners of every entry point. Used by `tests/test_awkward.py`
and the `tools/diff_check.py` typed area. Most scores are existing fixtures in `tests/data/` (referenced here, not copied).

| id (in test_awkward.py) | file | why it is awkward / provenance |
|---|---|---|
| pickup-repeat-split | `tests/data/part_writing_bwv303.musicxml` | Pickup bar plus a repeat sign that splits bar 4 in two; Bach chorale BWV 303 from the music21 corpus (public domain). |
| key-change-tuplets | `tests/data/triplet_brahms_fruhlingstrost.musicxml` | Key signature changes mid-piece (-1 to 3 sharps), 6/4, hundreds of tuplet notes, a grace note, cross-staff notes; Brahms, Fruhlingstrost; a triplet regression fixture. |
| compound-6-8-grace | `tests/data/export-mozart-k458.musicxml` | 6/8 string quartet (four parts) with grace notes; Mozart K. 458 excerpt. |
| compound-9-8 | `tests/data/export-debussy-clair.musicxml` | 9/8 with a pickup and a cross-staff voice; Debussy, Clair de lune excerpt. |
| tuplets-6-8 | `tests/data/triplet_hensel.musicxml` | 6/8 with 16 tuplet notes and a cross-staff voice; Fanny Hensel, Nachtwanderer Op. 7/1: a cleaned Audiveris reading of an OpenScore CC0 PDF (see `triplets.md`). Its last bar (39) fails the correct.py round trip. |
| tuplets-4-4 | `tests/data/triplet_mayer.musicxml` | Four-part quartet with triplets; Emilie Mayer, String Quartet Op. 14: a cleaned Audiveris reading of an OpenScore CC0 PDF (see `triplets.md`). |
| grace-mixed-meter | `tests/data/chopin_nocturne_op9_no2.mxl` | 15 grace notes, 29 tuplet notes, meter changes 12/8 to 2/4 to 6/4; Chopin Nocturne Op. 9 No. 2. |
| cross-staff | `tests/data/export-brahms-118-2.musicxml` | Voices that move between the two piano staves, pickup numbered 0; Brahms Op. 118 No. 2 excerpt. |
| two-parts | `tests/data/cadential_64.musicxml` | Two separate parts (not one piano part), four bars; music21-generated fixture. |
| four-parts-pickup | `tests/data/part_writing_motion.musicxml` | Four single-staff parts with a pickup; planted voice-leading errors (music21-generated fixture). |
| pdf-reading-overrun | `tests/data/awkward/kinkel-op8-5-trennung-reading.musicxml` | A real Audiveris 5.11.0 reading of a PDF (Johanna Kinkel, Op. 8 No. 5 "Trennung", CC0 Lieder Corpus engraving). `engine.read_pdf.problem_spots` flags bars 1, 3, 10 and 12; bars 10 and 12 have notes that run past the barline, and `correct.replace_bars` rejects their own `bars_from_musicxml` text. Copied from `spike/omr/bench/cache/runs/results-final--kinkel-op8-5-trennung--ms.musicxml`. |

`pdf-reading-prelude` is `tests/data/chopin_prelude_op28_no4_reading.musicxml`, another real PDF reading (Chopin Prelude Op. 28 No. 4, tuplets).

`typed.txt` is 40+ realistic student answers, one per line, that combine forms: mid-answer key changes, spaced slashes,
slash figures such as V6/5, secondaries, Unicode figures, punctuation, "bar"/"m" mixes, and chords separated by `/`, `-`, commas.
Written by hand for this suite (no source). Every line must parse or raise `ClarificationNeeded`.
