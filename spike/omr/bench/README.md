# OMR accuracy benchmark (Audiveris 5.11)

Measures how well the PDF-reading step recovers a piece, by kind of mistake, so a change to Audiveris (for example a
retrained symbol classifier) can be judged before/after. Local only; nothing here touches engine/, server/ or skill/.

## Run

```
cd spike/omr/bench
../../../.venv/bin/python run.py                 # -> results-baseline.json (use --out results-after.json for a later run)
../../../.venv/bin/python run.py --only mozart   # a subset (substring of the PDF path)
../../../.venv/bin/python run.py --set bench bench-heldout bench-heldout2 bench-heldout3 --audiveris PATH --tag prod2
```

- PDFs are read through `engine.read_pdf.read_pdf`, exactly as production (best of three settings, -Xmx1g, re-export
  when pages are skipped), except that each Audiveris run gets the full 240 s from when it starts.
- Only Audiveris's own output is cached, in `<set>/cache/raw/`, per PDF and per settings, keyed by sha256 of the PDF,
  the settings and a signature of the Audiveris install tree (file names, sizes, mtimes), so a rebuilt install
  re-reads everything. Cleaning, choosing a reading and the triplet fix run from the current engine code every time:
  a change there is measured in seconds (two PDFs: 22 s first run, 0.9 s after). `--tag X` forces a new cache key;
  change it too when files outside the install tree change. `seconds` per PDF is the Audiveris time in production's
  order (first reading, then the retries side by side), from the cache when cached.
- `--set` runs several benchmark folders (same manifest format) in one pool; each gets `<set>/<out>`. `--jobs` caps
  Audiveris processes at once (default and cap 6, ~1.7 GB each); scoring runs 12 at a time, a separate process per
  PDF (`score_one.py`), so a Verovio segfault is recorded as a scoring error instead of killing the run.

## What the numbers mean (per PDF, then summed; ratios are sums over all PDFs, so big pieces weigh more)

Pitch and onset are measured at the engine's level (`engine_check.py`: `load_toolkit` + `ScoreIndex`, after
`read_pdf`'s `clean`), never on raw MusicXML.
- **pitch**: shared pitches per aligned bar / truth notes. **pitch_onset**: shared (pitch, onset in quarter notes) / truth notes.
- **bar_duration_errors**: bars `engine.read_pdf.problem_spots` flags as not adding up (the warning users see);
  `bar_duration_errors_in_truth` is the same check on the truth, i.e. false alarms of the check itself.
- **tuplet_notes, ornaments, grace, octave_lines, clef_changes**: counted on the MusicXML, per bar, over bars aligned by
  shared pitches. `truth` = marks in the truth; `found` = marks in the same bar in both (min per bar); `missed` = truth - found;
  `invented` = marks in the OMR with no counterpart in that bar of the truth. Tuplet notes = non-rest notes with a
  time-modification; ornaments = turn, inverted/delayed turn, trill-mark, mordent, inverted mordent; octave_lines =
  octave-shift up/down starts; clef_changes = a clef that differs from the staff's previous clef (opening clefs not counted);
  grace = notes with `<grace>`.
- **pages_skipped**: pages Audiveris found no staves on. **crashed**: no MusicXML at all (all truth notes count as lost).
  **seconds_per_page**: wall time of `read_pdf` / pages.
- Because a piece appears in several PDFs (different engravers), totals count it once per PDF.

## Pieces (23, 57 PDFs)

Truth is MusicXML in `truth/`; PDFs in `pdfs/`; source URL and licence per piece in `manifest.json`.
Engravers: ms = MuseScore 4, vr = Verovio (repo engine), ly = LilyPond 2.24.4 (via musicxml2ly), scan = synthetic scan
(300 dpi grey raster of the ms PDF, rotation <=0.8 deg, blur, noise, uneven paper tone, JPEG; fixed seed per piece),
plus 2 Mutopia (LilyPond) PDFs and 2 real scans (Peters, Schirmer) already in `spike/omr/`.
Excerpts keep only the first N bars (chamber pieces; a whole movement exceeds 12 pages).

| piece | kind | PDFs |
|---|---|---|
| bach-chorale-269 | chorale | ms (2p), vr (1p) |
| bach-prelude-846 | keyboard | ms (2p), ly (2p) |
| mozart-k545-1 | keyboard | ms (5p), ly (4p), scan (5p), lilypond-mutopia (5p), real-scan-peters (4p) |
| chopin-prelude-4 | keyboard | ms (2p), vr (2p), scan (2p), lilypond-mutopia (1p), real-scan-schirmer (1p) |
| joplin-maple-leaf-rag | keyboard | ms (4p), ly (4p) |
| clara-schumann-polonaise-1 | keyboard | ms (3p), vr (2p) |
| clara-schumann-polonaise-3 | keyboard | ms (3p), ly (6p), scan (3p) |
| clara-schumann-polonaise-4 | keyboard | ms (2p), vr (2p) |
| cpe-bach-h186 | keyboard | ms (5p), ly (5p), scan (5p) |
| faisst-op18-2-lied-der-nacht | song | ms (3p), vr (2p), scan (3p) |
| lehmann-golden-bridges | song | ms (2p) |
| hensel-op7-1-nachtwanderer | song | ms (4p), vr (3p) |
| schumann-op96-4-gesungen | song | ms (4p), ly (3p) |
| kinkel-op8-5-trennung | song | ms (2p), vr (1p), scan (2p) |
| schubert-die-stadt | song | ms (4p), ly (4p) |
| schubert-ave-maria | song | ms (5p), vr (3p) |
| beethoven-op52-2-feuerfarb | song | ms (3p), ly (2p) |
| haydn-canzonet-she-never-told | song | ms (3p), vr (2p) |
| beethoven-op48-5-gottes-macht | song | ms (1p), ly (1p), scan (1p) |
| haydn-quartet-op20-6 (first 28 bars) | quartet | ms (2p), vr (2p) |
| mozart-quartet-k155 (first 28 bars) | quartet | ms (2p), ly (2p) |
| mozart-quartet-k80 (first 28 bars) | quartet | ms (1p), vr (3p), scan (1p) |
| mayer-quartet-op14 (first 28 bars) | quartet | ms (3p), ly (2p) |

Licences: OpenScore (Lieder, StringQuartets) is CC0. The other files come from the music21 corpus, When-in-Rome and
musetrainer: the works are public domain but the encodings' licences were NOT individually verified (music21's corpus
licence says some encodings are non-commercial). Do not redistribute `truth/` or `pdfs/` before checking.

mozart-k545-1's truth has the left-hand clefs of the Peters edition (the encoding kept bass clef in bars 42-45 and
58-62, where Peters and other editions switch to treble). A clef printed just before a barline is written at the end of
that bar, as Audiveris reads it. MuseScore draws such a clef after the barline, so its ms/ly/scan PDFs were engraved from
a copy that writes those four changes (end of bars 21, 41, 57, 62) at the start of the next bar instead
(`truth/mozart-k545-1-engrave.mxl`, not picked up by `build.py`); the music is the same.

Not built:
- lehmann-golden-bridges / ly: CalledProcessError: ical objects...\nFinding the ideal numbe

## Rebuild the inputs

```
git clone --depth 1 https://github.com/OpenScore/Lieder.git DIR1 ; git clone --depth 1 https://github.com/OpenScore/StringQuartets.git DIR2
# LilyPond: https://gitlab.com/lilypond/lilypond/-/releases/v2.24.4/downloads/lilypond-2.24.4-linux-x86_64.tar.gz, unpacked, no sudo
../../../.venv/bin/python build.py --lieder DIR1 --sq DIR2 --lilypond-bin LILYPOND/bin
```
Piece list and engraver choices: `pieces.py`. The feature counters: `features.py`.

## Known limits

- Coverage per mistake kind is uneven: octave lines appear in only 2 pieces (Faisst, Lehmann), ornaments mostly in
  Mozart/C.P.E. Bach/Haydn, grace notes mostly in Clara Schumann/Kinkel/quartets. Treat small counts as noisy.
- The bar alignment for marks is by shared pitches; a badly misread bar can lose its marks to "missed"/"invented".
- Tuplets are counted per note, so one misread triplet bar moves several counts.
- Songs carry lyrics, which the truth keeps and Audiveris OCRs; lyrics are not scored.
