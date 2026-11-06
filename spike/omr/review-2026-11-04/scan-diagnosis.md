# Scanned paper music: why the reader does badly, and whether the test is fair

Date 2026-11-04. Reader: marks1 (fork dbe09b8a6). Scope: flat scans of printed music. Diagnosis only: no reader or engine code changed, nothing committed, released or deployed. No home PCs, no downloads. The `scan-diag` worktree was not needed, because no fork logging was added.

"Exact" is `whole_bars.py` strict: every pitch, onset, duration, rest and tie right in the bar. "Pitch" and "timing" are note percentages.

## Short answer

- **The test understates the reader, but the problem is real.** On the same 40 inspect items, removing test effects takes 14.5% to about 20% exact (19.7%: true page size, 4 tiny PDFs dropped). Separately, the original 40 was an unlucky draw: the next 40 score 15.7%, against 9.9%. Neither approaches printed-from-software quality.
- **Same music, same reference, print versus real scan:** Chopin Op. 28/4 is 84.6% from Mutopia and 46.2% from the Schirmer scan. Mozart K545/i is 76.7% from Mutopia and 35.6% from the Peters scan. MuseScore PDFs of both are about 96%.
- **The errors are mostly reading errors, not image-input problems.** Resolution, skew, binarizing and time-signature context each moved the score by 0-3 points.
- **Largest buckets:** a few lost note heads per system, wrong clefs (header and mid-system), and rests in old print styles that are not recognized.

## Data changes

- `spike/omr/bench-olimpic` now holds 80 samples. The first 40 are unchanged; samples 41-80 follow the written rule, built from the OLiMPiC archive already on disk at `/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/ol/olimpic-1.0-scanned` (2,931 systems, 100 dev and 100 test works, about 15 systems a work).
- `split.json` in that folder is the random split by work (seed 20261104): 40 inspect, 40 unseen. It was made before any bar-level looking. `SELECTION.md` records the rule.
- The unseen half was used for aggregates only.
- That folder and this one are git-ignored, so nothing here shows up in a diff.
- Whole-set `bench-olimpic` scores now cover 80 PDFs. For the old 40, use `scan-diag/agg.py`.

## Q2. Current numbers (marks1)

| Set | PDFs | Bars | Exact | Pitch | Timing | Failed |
|---|---:|---:|---:|---:|---:|---:|
| bench-olimpic, original 40 | 40 | 161 | 9.9 | 70.0 | 51.3 | 6 |
| bench-olimpic, new 40 | 40 | 172 | 15.7 | 76.1 | 59.4 | 5 |
| bench-olimpic, all 80 | 80 | 333 | 12.9 | 72.9 | 55.0 | 11 |
| inspect half | 40 | 172 | 14.5 | 77.3 | 61.1 | 5 |
| unseen half | 40 | 161 | 11.2 | 68.9 | 49.7 | 6 |
| bench-real | 3 | 154 | 66.9 | 88.8 | 74.3 | 0 |
| five real full-page scans (bench-real plus 2 in bench) | 5 | 253 | 55.7 | 89.2 | 80.1 | 0 |

Part of the 9.9% was bad luck in the sample: another 40 from the same rule gives 15.7%. On about 160 bars each, treat these as a range, not a point.

Per piece, real full pages (exact bars):

| Piece | Exact | Pitch | Timing | Interline at 300 dpi |
|---|---:|---:|---:|---:|
| Bach WTC I/22 (Peters) | 0/24 | 79.3 | 47.1 | 11 |
| Beethoven Op. 2/1/iii (Henle) | 62/77 | 94.0 | 93.5 | 21 |
| Grieg Op. 38/7 | 41/53 | 99.3 | 98.3 | 21 |
| Mozart K545/i (Peters) | 26/73 | 86.5 | 81.3 | 19 |
| Chopin Op. 28/4 (Schirmer) | 12/26 | 96.2 | 95.4 | 21 |

Mutopia comparison, cached: Chopin 84.6% and Mozart 76.7% exact, against the scans above.

## Q1. Is the test fair?

Each row changes one thing and re-reads. Inspect half, 172 bars, unless noted.

| Test effect | Measurement | Effect on exact | Kind |
|---|---|---|---|
| Sampling | old 40 vs new 40 | 9.9 vs 15.7 | test |
| Tiny images (interline 6-8) | 4 PDFs, 25 bars, 0 exact; without them 25/147 | 14.5 to 17.0 | test mix; real low-res files do exist |
| Page size assumed 300 dpi, though most crops are about 600 dpi | same pixels with true page size (interline 21) | 14.5 to 16.9; pitch 77.3 to 81.9; PDFs at interline over 36: pitch 83.0 to 90.5 | test |
| Foreign ink from the voice staff above | blanked above the piano staves | 14.5 to 15.7 (+2 bars) | test |
| No time signature | true signature inserted in the image; read right on 28 PDFs | none: 22/117 before and after on those 28 | not the cause |
| Single system vs page | 12 works, 86 systems, 362 bars, same pixels and scale: singles vs reassembled pages | 19.1 to 20.4; timing 59.6 to 67.0; pitch 84.3 to 84.7 | small |
| Reference error | 6984553-p2-s1 reference has G clef on line 1; the print is a normal G clef and the reading is right | up to 5 bars (2.9 points) | test, seen on the ink |
| Ties running into the next system | bars wrong only because of this | 1 bar inspect, 0 unseen | negligible |

Time-signature caveat: inserting a signature adds its own noise. 5000467-p3-s2 lost 26 timed notes although the inserted 12/8 was not read. Only the 28-PDF comparison is clean.

Truth against ink was checked by eye on four systems: three references match, one is the clef error above. That sample is small.

Fair level for OLiMPiC single systems, measured on one reading: 29/147 = 19.7% (true page size, tiny PDFs dropped). Reassembled pages agree at 20.4%, on a different set of bars. The reference error could add up to about 3 points. These effects overlap, so the rows above do not add up.

**`--scan` PDFs in `bench` are not scans.** `bench/build.py` passes a clean render through `scanify.py` at 300 dpi. They score 64.7% exact and 98.5% pitch, against 88.8% pitch on bench-real and 72.9% on OLiMPiC. They keep modern font shapes, so they say little about old prints. Do not use them as a scan measure.

**bench-real flatters.** Three pieces, and two of them are clean 600 dpi sources in plain style. Adding the two real scans in `bench` takes it from 66.9 to 55.7. Its references come from other editions (When in Rome): Peters prints a bass clef followed by a treble clef in Mozart's first bar where the reference has treble only.

What the gap between OLiMPiC (about 20%) and real full pages (56%) comes from is **not isolated**. Lieder prints, older engraving and piece mix are all candidates.

### What a fair full-page set needs

Real scans; full pages at true page size; a reference made from that edition; all staves in the reference (voice included); split by work; at least 20-30 works so one piece cannot move the score.

On disk:
- 5 real full-page scans (above), with references from other editions.
- About 200 OLiMPiC works, whose references match the print. Pages can be reassembled from their systems with no download (`scan-diag/assemble.py`; dev-split works keep the test split clean). Limits: invented layout, voice line missing.

The archive sits in the session scratchpad, which is temporary. If it is lost, step 1 needs it again (225 MB, https://hdl.handle.net/11234/1-5419).

The two IMSLP volumes in `spike/omr/imslp/` (Chopin Schirmer 62 pages, Mozart Peters 302 pages) hold many more real pages. The manifests I checked have references only for K545/i and Op. 28/4 from them (bench-pitch and bench-octave not checked), so they give no larger set without new references.

Download, if real page layout is wanted (not done): the OpenScore Lieder full scores and the matching IMSLP PDFs, starting from the OLiMPiC tooling at github.com/ufal/olimpic-icdar24. Whether that repository links the IMSLP files directly is not confirmed.

## Q3. Where the errors come from

Each wrong bar counted once, under its first failing kind (`scan-diag/classify.py`). Inspect half 172 bars, 147 wrong; bench-real 154 bars, 51 wrong. PDFs in brackets, because bars cluster.

| Stage | Inspect | bench-real | Total | Evidence | Status |
|---|---:|---:|---:|---|---|
| Note heads: missing or extra | 32 (22) | 11 | 43 | Heads in Audiveris before export are 96.5% of reference notes (1986/2057; real 3662/3752). Export loses only 4 and 12 | Stage narrowed to before export. Decision not traced |
| Image input: no reading | 29 (5) | 0 | 29 | See below | **Verified** |
| Clefs | 13 (4) | 14 | 27 | See below; 5 of the 13 are the reference error | **Verified on 2 PDFs** |
| Rhythm: wrong onsets (rests and voices) | 21 (12) | 1 | 22 | 16 of 21 also have a rest difference | **Rest cause verified on 1 PDF**; the rest are symptom only |
| Accidentals | 11 (9) | 4 | 15 | none | Symptom |
| Rests alone | 9 (8) | 5 | 14 | Includes a whole rest placed after the bar (6378337) | Symptom |
| Octave | 5 (4) | 9 | 14 | 9 are Bach | Symptom |
| Keys | 10 (3) | 0 | 10 | 9 are work 5000467: four sharps read as two at interline 40. True page size cuts key errors 10 to 2, but Lanczos scaling to the same interline raises them to 14 (and clefs 13 to 22) | Unsettled: depends on how the image is resampled |
| Heads on the wrong line | 3 | 3 | 6 | none | Symptom |
| Ties | 5 | 1 | 6 | Mostly not the system-end artefact | Symptom |
| Dots | 4 | 1 | 5 | none | Symptom |
| Staff assignment | 1 | 2 | 3 | none | Symptom |
| Stems, beams, flags (duration) | 2 | 0 | 2 | none | Symptom |
| Bar not paired | 2 | 0 | 2 | none | Symptom |
| Total | 147 | 51 | 198 | | |

Stages with no bars to their name:
- **Skew or warp.** No gain from fixing it (Q4).
- **Staff lines.** Books for the inspect half: 36 of 40 found exactly 2 staves; the other 4 are the interline 6-8 PDFs, which stop before staves are found.
- **Time signatures.** No net effect (Q1), but Bach logs "No target duration" and was not traced.
- **Voices.** `exact` ignores voice labels, so voice errors only appear as onsets and are not separated.

### Traced causes

**1. Image input: no reading (29 bars, 5 PDFs).** Two separate causes.
- Four PDFs at interline 6-8 are below `ScaleBuilder.minInterline` (11). `facts.problems` shows `StepException` and an invalid page. The re-render that rescues small staves (`ScaleStep.renderAgain`) returns null for image pages (`ImageLoading.getVectorImage`), so scans can never use it. Upscaling and binarizing first turns 4 failures into 1, with pitch 45, 65 and 91% on three of them, but still no exact bar. These images are too coarse to read well.
- 6377942-p7-s2 is a crash: Audiveris exported `<divisions>0</divisions>` and `engine/score.py:139` raises `ZeroDivisionError`, which `read_pdf` does not catch as a `ReadError`. This is a reader bug on any input that produces it. Why Audiveris writes 0 was not traced.

**2. Clefs (27 bars, 22 after the reference error).**
- Header clef: `ClefBuilder` logs "Staff#2 no recognized header clef" on 6481218-p5-s1 and "p7-s2". The bass staff is then read as treble.
- **Intervention:** painting a standard bass clef over the printed one and re-reading takes pitch from 53/115 to 101/115 notes on those two PDFs. Exact stays 0 of 9 bars; pooled reaches 2, so other errors remain in those bars. That shows the clef is the decision going wrong, and that fixing it alone does not finish the bars. Why the classifier rejects the printed glyph (`ClefBuilder.java:565`) was not traced further.
- Mid-system clefs: on real pages most differences are "reference treble, read bass" on staff 2 (Mozart 17 bars, Bach 7). Correcting the clef after the fact across the whole bar makes 11 of 35 bars right, against 5 before (inspect: 5 of 13, against 0). That undercounts, since a clef changes partway through a bar, but it shows clefs are not the only fault there.

**3. Rests in old print styles (22 bars have onset errors; 1 PDF proved).** 6986302-p1-s2 prints quarter rests as old "z" shapes. Audiveris does not see them, so the second voice runs on after the first (reference E4+G4 at beat 1; reading at beat 3).
- **Intervention:** painting standard rests over 12 of them and re-reading: timing 30 to 40 of 48 notes, pitch and timing right in 0 to 3 of 6 bars, exact still 0.
- How many of the other 11 PDFs have the same cause is not measured. Rest differences appear in 50 wrong inspect bars and 27 on bench-real.

**Note heads (largest bucket, not traced).** About 3.5% of notes never become heads. At about 12 notes a bar, that alone can spoil about a third of bars, which is why note accuracy of 88% coexists with exact below 20%. Notes on ledger lines are found less often on OLiMPiC (80.3% vs 90.2% pitch match) but not on real pages (89.7 vs 89.1). Hollow versus black, chord size and beaming show no difference. The next step is listing lost heads per bar with their image.

Not traced: Bach 0/24 (time signature, clef, octave). Resolution is ruled out: interline 23 is still 0/24.

## Q4. Pre-processing today

`engine/read_pdf.py` does no image work.
- `is_scan` only decides whether the warning line is shown. There is no upscaling, binarizing or deskewing, and no scan-specific setting.
- The PDF goes straight to Audiveris. It renders every page at a fixed 300 dpi in gray (`ImageLoading`, `pdfResolution`), whatever the image's real resolution, so a 600 dpi scan is halved.
- Audiveris binarizes with its adaptive filter, measures skew and follows the lines without rotating the image, and rejects pages over 20 million pixels (`SheetStub`).

Probes (no fixes kept):

| Probe | Items | Result |
|---|---|---|
| Scale to interline 21 (Lanczos) | inspect 40 | exact 14.5 to 17.4; timing 61.1 to 60.9; failed 5 to 2 |
| Scale to interline 30 | inspect 40 | exact 15.7; pitch 82.9; timing 64.2 |
| True page size, interline 21 | inspect 40 | exact 16.9; pitch 81.9; timing 63.5; failed 3 |
| Deskew | inspect 40, 33 rotated, up to 1.2 degrees | exact 14.5 to 16.3; on the 12 most skewed, +1 bar, timing 426 to 450 of 721 |
| Deskew Mozart (skew 0.9-1.44 degrees, from its binary pages) | 1 piece, 73 bars | exact 35.6 to 32.9; timing 81.3 to 76.3 |
| Binarize only | 5 gray items (35 of 40 are already two-level) | no failure rescued; 6586696 pitch 95 to 90 |
| Binarize and upscale | same 5 | failed 4 to 1; 0 extra exact bars |
| Wrong page size: render real scans at 0.75x | 5 real | collapse: Beethoven 62 to 30, Mozart 26 to 5, Bach no reading |
| Wrong page size: render at 1.5x | 5 real | Bach 0, Grieg 41 to 39, Mozart 26 to 29; Beethoven and Chopin refused |
| Wrong page size: render at 2x | 5 real | Bach 0; the other four refused (over 20 million pixels, seen in the log; 2 GB heap makes no difference) |

Reading: the zoom rows change the render scale only, so a small page loses pixels at render. Below about interline 16 things collapse; from about 19 upward, more pixels add little. A truly low-dpi scan on a correctly sized page, upsampled back to 300 dpi, was not tested. The page-size effect in the OLiMPiC set is mostly a fault of how that set was built.

## Q5. What to do next

| # | Step | Gain | Measured or guessed | Effort |
|---|---|---|---|---:|
| 1 | Make the test fair: rebuild OLiMPiC at true page size, reassemble pages from dev works, report tiny images separately, correct the known reference | Score means something; 14.5 to about 20% on the inspect half, same reader | Measured | Hours |
| 2 | Catch `divisions=0` | 1 of 5 inspect failures stops crashing; 4 bars at stake | Measured crash; reading quality guessed | Under an hour plus tests |
| 3 | List lost heads per bar against the image, then decide | Largest bucket (43 of 198); fix might add 5-10 exact points | Guessed | 1 day to diagnose; fix unknown |
| 4 | Header and mid-system clefs | 22 of 198 bars; pitch 53 to 101 of 115 on 2 PDFs; perhaps 3-6 exact points on real pages | Pitch measured, points guessed | Days |
| 5 | Old-style rests | Timing 30 to 40 of 48 on 1 PDF; perhaps 3-5 exact points on old prints | Timing measured, points guessed | Days to weeks (shapes or training) |
| 6 | Upscale very small image pages (extend the existing re-render) | 3 more PDFs of 40 produce music; no exact bars | Measured | Small |
| 7 | Deskew or binarize | Deskew mixed and within noise (+1.8 exact on inspect, -2.7 on Mozart); binarize alone none | Measured | Not now |
| 8 | Render scans above 300 dpi | Small and hits the 20-million-pixel limit | Measured | Do not do |

Also: **stop using `--scan` PDFs as a scan measure** (no cost).

## Owner decisions

1. Accept the reassembled set from dev works as the working fair set, or also download real page scans (OpenScore Lieder plus IMSLP)? The download gives real layout and voice staves.
2. The log's line about 40% ("below the review's 40% line where scan work outranks the rest"): full real pages are at 56%, OLiMPiC at about 20%. Which of these should the line apply to? This changes whether scan work outranks the rest.

## NOT RUN

- Full test suite, `tests/test_awkward.py`, `tools/diff_check.py`: no code changed.
- Stage tracing for heads, accidentals, octave, Bach; `<divisions>0</divisions>` origin; classifier decision on rejected clefs.
- Voices as a separate stage.
- Fair probes on the unseen half: kept for later testing, so all intervention gains above are inspect-half only and may shrink.
- Reassembled pages from dev works: pages so far use 12 inspect works.
- A truly low-dpi scan on a correctly sized page.

Side effect: `speed/results/bench-marks1.json` was overwritten by this run and now holds only bench-olimpic and bench-real. The wider run is in `bench-marks1-183.json`.

## Files

Scripts and per-item results: `spike/omr/review-2026-11-04/scan-diag/` (`imgs.py` points at the scratchpad for the archive and font; items and runs are written next to the scripts). Readings and images: `/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/scan-diag/`, temporary.

## 2026-11-04, later: lost and extra heads traced, `divisions=0` root cause

Temporary logging build on branch `scan-heads` (worktree `scratchpad/heads/src`, uncommitted, disposable). `sma-pitch` and `reader-next` unchanged. Its readings match the cached marks1 readings bar for bar on all 25 PDFs in the bucket. Scripts: `scan-diag/heads/`. File:line refers to fork dbe09b8a6.

**Correction to the earlier note.** The 96.5% counted final heads in the book against reference notes, not candidates, and false heads offset lost ones. It does not show that 96.5% of notes became candidates.

### Where each head dies (43 bars: 97 missing heads, 51 extra)

| Stage | Heads | Bars | Location |
|---|---:|---:|---|
| No candidate: ledger line accepted, then discarded by the page-wide statistics filter, so that pitch is never scanned | 16 | 13 | `LedgersPostAnalysis.java:299` (range mean +-1 sigma, constants `:342-360`); scan gate `NoteHeadsBuilder.java:1075` |
| No candidate: no ledger stick (2) or stick rejected (1) | 3 | 3 | `LedgersBuilder.lookupLine` |
| No candidate: template too far (5), or within the distance limit with no candidate (3, reason not traced) | 8 | 6 | `NoteHeadsBuilder.Scanner` |
| Dropped against a seed-based head | 3 | 3 | `NoteHeadsBuilder.filterSeedConflicts` |
| Removed: black head has no stem | 21 | 12 | `SigReducer.java:765` |
| Removed: lost an exclusion (10 had only a wrong-shape candidate) | 15 | 12 | `SIGraph.java:1282` |
| Removed: low contextual grade | 3 | 3 | `SIGraph.deleteWeakInters` |
| Head present, wrong alteration (not a head fault) | 16 | 10 | export or accidental stage |
| Head at wrong pitch | 6 | 5 | |
| Head in another bar | 2 | 2 | |
| Survived, not exported | 4 | 1 | |
| Extra: paired with a missing note above | 22 | 13 | |
| Extra: unpaired | 29 | 16 | By eye on crops: about 13 real heads with a wrong pitch, about 10 weak hollow heads (grade 0.17-0.29) beside real ones, about 6 on beams. Counts by eye are approximate |

Note positions come from anchoring on matched notes, and are not exact. Of 19 crops for the "pitch never scanned" group, about 15 clearly show a head on a ledger; the rest look mislocated. 21 no-stem crops checked the same way.

The no-stem heads split into: 9 undecided (one stem stump serves both corners, `HeadLinker.java:360-365`; the code that would resolve this is commented out at `StemsRetriever.java:336`), 7 linked then cut, 5 link failed.

### Interventions (setting 0, raw reading, 25 PDFs, 243 bars)

| Change | Bucket bars right, of 43 | Pitch in bucket, of 721 | All bars, of 243 |
|---|---:|---:|---:|
| Baseline | 0 | 624 | 121 |
| Ledger filter widened to +-3 sigma | 7 | 654 | 125 (+7, -3) |
| `HeadStemRelation.xInGapMax` 0.4 | 0 | 624 | 121 |
| `poorInputMode` on (option taking effect not confirmed) | 0 | 624 | 121 |
| Force a link on undecided heads | 0 | 625 | 121 (all-bar pitch -10) |
| Keep heads with no stem | 0 | 623 | 121 |
| Keep heads plus +-3 sigma | 7 | 653 | 125 |

Ink: cutting the through-stem beside the undecided heads on 3 PDFs brought back 5 of the 12 lost no-stem heads there (9 of the 12 were undecided). No bar came fully right. This supports the stem cause at head level only; it is not proven at bar level.

### Clean PDFs

- Ledger discards hit both: clean 792 of 12,178 ledgers (6.5%, 15 traced PDFs), scans 257 of 4,117 (6.2%). A discarded ledger costing a head on clean PDFs was not measured.
- No-stem removals: clean 39 in 15 PDFs (multi-page), scans 356 in 25. Not normalized per page or per head.
- +-3 sigma on clean PDFs, full reader pipeline, 48 of a 60-PDF hash sample from the 170: exact 1376 to 1380 of 1914; pitch 34033 to 34052; timing 32182 to 32208. 7 PDFs better, 5 worse by one bar each (not inspected).

### Crash

`Page.simpleDurationOf` (`Page.java:708`) computes `value.num * (divisor / value.den)` in integers. `computeDurationDivisor` (`:201`) returns the denominator of the common divisor in whole notes. On a page where every duration is a half or longer it is 1 or 2, so the quarter gives `2 / 4 = 0` and `<divisions>0</divisions>` is written. That flows through Verovio's `ppq` to `engine/score.py:139`. So the defect is in the reader, and our code only fails to catch it.

Corpus check (`heads/divcheck.py`): 14,018 cached raw readings, one with zero, this one. No reading has a truncated value (divisor 6, 10 and so on would give silently wrong durations). Excluded: bench-pitch, bench-octave, unseen half. 30 readings have duration mismatches at multiples of 4, a different defect, not traced.

Proposed fix, not applied: make `computeDurationDivisor` return the least common multiple of the denominator and 4. Tested in the temporary build only: divisions 1, whole note 4, `ScoreIndex` parses 4 measures, 10 of 20 pitches, 0 of 4 bars exact. Readings with a divisor already a multiple of 4 are unchanged by construction. Add this PDF to the test data.

### Gain

- Ledger filter: +4 net bars of 243 on the 25 PDFs, measured. About 1.2 points on inspect plus bench-real if other PDFs are unchanged, guessed. The earlier 5-10 points is not supported by this cause alone.
- Stem cause: not established; guessed small until the through-stem case is fixed.

### NOT RUN

- +-3 sigma on the whole inspect half through the full pipeline: stopped with no readings finished.
- Clean per-stage table: trace run stopped at 15 PDFs, so the stage split above is scans only.
- The 12 remaining clean sample PDFs.
- Why the delta statistic is off on these ledgers; a proper replacement for the +-1 sigma filter.
- Full test suite, `tests/test_awkward.py`, `tools/diff_check.py`: no reader change kept.

Process note: an early `grep -r` for `<divisions>0</divisions>` ran over all of `speed/cache`, including bench-pitch and the unseen half. It returned no files. A listing also showed the count of bench-pitch readings. No other data from them was seen.

## 2026-11-04, later: clefs traced

Temporary builds only: logging on branch `scan-heads` (worktree `scratchpad/heads/src`), candidate on new branch `scan-clefs` (worktree `scratchpad/clefs/src`); both uncommitted and disposable. `sma-pitch` and `reader-next` unchanged. Nothing released, pushed or deployed. Scripts and `candidate.diff`: `scan-diag/clefs/`. File:line refers to fork dbe09b8a6. The logging build's trace readings match cached marks1 on all 298 bars of the 38 PDFs that have a cached reading to compare. Crops of the clefs below were checked by eye.

**Corrections to earlier notes.** These also change the Q1 row "Reference error": up to 2 bars (about 1.2 points), not 5 (2.9 points).
- "5 of the 13 are the reference error" is wrong. On 6984553-p2-s1 only bars 0-1 are the reference fault. Bars 2-4 are a real lost bass clef: read treble, and on staff 2 moving the reading to bass matches 7 of 10 notes against 0 as read (bars 3-4: 2 of 2 and 4 of 4). On ink it is a clear printed F clef.
- 11 of the 27 bars are not reader clef errors at all. That leaves 16, not 22.

### Stage of each clef error (27 bars)

Test used: for each bar and staff, pitch match as read against match if the reading is moved to the other clef; then the clef checked on ink.

| Stage | Bars | Where | Evidence | Location |
|---|---:|---|---|---|
| First of system: printed F clef not recognized | 6 | 6481218-p5-s1, p7-s2 (3 staves) | Classifier saw the arc and dots only: top FLAG_1_DOWN 0.35-0.62, F_CLEF at most 0.06. The knob is a separate part (231 px) never joined: gap above the limit. With it joined, F_CLEF 0.96 | `ClefBuilder.java:719` (`maxPartGap` 0.75), `:240`, warning `:658` |
| Mid-staff: small F clef graded low, deleted | 4 | Beethoven 38-41 | 45x59 px, F_CLEF 0.18. Bonus for fitting the drawing refused: centre offset 0.67 above 0.5, because small clefs share the full-size centre pitch. Deleted as weak | `ClefInter.java:586`, `:833`; `SIGraph.java:384` |
| Mid-staff: below symbol minimum | 1 | Beethoven 31 | F_CLEF 0.14 under 0.15, no clef created | `Grades.java:141`; `SymbolsBuilder.java` evaluate |
| Mid-staff: knob taken for a note head | 3 | 6984553-p2-s1, bars 2-4 | Knob exported as WHOLE_NOTE 0.56 (an extra note in bar 1), its ink erased before symbols; F_CLEF is not among the top five grades of what remains. The existing clef check handles treble only | `NoteHeadsBuilder.java:683`, `:711` |
| Mid-staff: false F clef kept | 2 | 6570310-p2-s2 bar 2, Bach bar 19 (both upper staff) | Grades 0.70 and 0.66 on chords. Sizes 3.9x6.3 and 3.7x5.5 interlines, a real one 2.7x3.5. No size check | `ClefInter.createValid`; `SymbolsBuilder.java:221` |
| Not a clef error: reference or edition differs, reader right | 9 | Bach 0-6, 6984553 bars 0-1 | Bach prints bass, the reference has treble; notes as read match, 72 of 97, none moved. These bars fail on lost notes | |
| Not a clef error: clef at a barline counted in the neighbouring bar | 2 | 6570310 bar 1, Beethoven 34 | As read 36 of 36 and 9 of 9 | |
| Total | 27 | | | |

Split of the 16 real errors: first of system 6; mid-staff 10 (8 lost, 2 false). Classified as a wrong kind of clef while kept: none. Key knock-on: none (key right in all 27). Octave differences (16 in these bars) were not separated out. That the staff-line removal is what detaches the knob is inferred, not proven; the detachment and the gap are measured.

**Carrying clefs across systems.** The reader does not. `Measure.getClefBefore` (`Measure.java:752`, note at `:745`) stops at the system start, and no clef falls back to the default (`ClefInter.java:456`), read as treble. On this set the case does not arise: 3 of 132 header staves had no clef (39 PDFs that read), all three in the single-system 6481218 PDFs, none on the 3 real pages. So carrying would gain nothing measurable here. Measured for this set only; scans that omit clefs at line starts are not in it.

### Interventions

Inspect half plus bench-real: 43 PDFs, 326 bars. Baseline exact 128, pitch 3396, timing 2760, of 3897 notes. "Clef bars" are the 27 above: 0 exact, pitch 356 of 508.

| Change | Exact | Pitch | Timing | Clef bars exact | Clef bars pitch |
|---|---:|---:|---:|---:|---:|
| `maxPartGap` 1.5 everywhere | 130 | 3442 | 2802 | 2 | 384 |
| `maxLineOffset` 0.8 | 130 | 3409 | 2773 | 2 | 369 |
| Both of the above | 132 | 3455 | 2815 | 4 | 397 |
| Bass clef check on head candidates (rough version of the treble check) | 116 | 3258 | 2630 | 1 | 360 |
| Reject F clefs over 1.25 x normal height | 128 | 3410 | 2771 | 0 | 370 |
| Fall back to F when the drawing fits and no clef was found | 130 | 3442 | 2802 | 2 | 384 |

Each single change was re-read in the clean candidate build, on its affected PDFs through the full pipeline: the retry alone gives exactly the 6481218 changes below, `maxLineOffset` alone exactly the Beethoven ones. The other rows are from the logging build.

- First cause, the 2 PDFs: pitch 53 to 99 of 115 (painting a clef gave 101), exact 0 to 2 of 9. So this confirms the cause, and the bars are still mostly wrong.
- Second cause: Beethoven 62 to 64, pitch +13. Bars 38-39 come right; 40-41 reach every pitch but stay inexact; bar 31 is not recovered (its grade is below the minimum).
- Head check: fixes 6984553 (+1 bar, +7 pitch) but creates false clefs on chords. Grieg 41 to 32. Rejected as written.

### Rule for accepting a fix, set before reading the clean result

On clean PDFs in the tuning sets, against marks1: exact bars not down overall; no set down by more than 0.1 points; pitch and timing not down.

### Clean PDFs

Hash sample of 60 (53 from tuning sets `bench`, `bench-tune2`, `bench-oldly`; 7 from `bench-heldout*`), 2759 bars, full reader pipeline.

| Candidate | Exact | Pitch | Timing | PDFs lost |
|---|---:|---:|---:|---|
| `maxPartGap` 1.5 everywhere | failed | | | p-sq22948888--ms 18 to 16, p-sq26652775--ms 38 to 31 (pitch -52, -20), both `bench-tune2` |
| Retry at 1.5 only when a staff found no header clef, plus `maxLineOffset` 0.8 | 1480 to 1480 | 45981 to 45984 | 42942 to 42945 | none |

Per set, the second candidate: exact unchanged in all six; pitch and timing +3 on one PDF (ly-lvb-sonate-78-2--ly-old), all others identical. **It meets the rule on what was run**: 60 PDFs. Not run on the other clean PDFs, the unseen half, or bench-pitch. The retry fires only when a staff finds no header clef, which was 3 of 132 staves on scans and may be rarer on clean PDFs, so this pass mostly tests `maxLineOffset`. How often the retry fired on the clean sample was not counted.

The same candidate on the scan set, full pipeline: 128 to 132 of 326, pitch 3396 to 3455, timing 2760 to 2815; 3 PDFs changed, none worse.

Caution on the first clean figure: with the logging build, a first pass looked like 1480 to 1448, and a no-option control lost the same bars on two `--vr` PDFs (Haydn 23 to 0). Stock `aud-div1` and `aud-marks1` reproduced the baseline, so this was my logging: gating one log line cut the loss to 5 bars, the rest was not traced, and the build was dropped. The figures in the second row come from a build with only the candidate. Its `Page.java` carries the divisions fix behind a switch that was off, so that file behaves as in marks1, not div1; only one cached reading hits divisions=0, and it is not in the sample. `candidate.diff` holds the `ClefBuilder` retry; `maxLineOffset` is a runtime option, not in the diff. The two sq losses in the first row were measured in the logging build, where the retry alone did not lose them; they were not repeated in a clean build.

### Size

- Measured: inspect half 14.5 to 15.7 (+2 bars of 172), bench-real 66.9 to 68.2 (+2 of 154), together 39.3 to 40.5. 4 of the 16 real clef-error bars become exact; on 2 more every pitch is right.
- The values 1.5 and 0.8 were the first tried, on these same PDFs, so the gain may shrink on other data.
- Guess: fixing the remaining 3 lost clefs and the 2 false ones adds at most 3-5 bars here, since those bars have other errors too (the size check gave 0 exact).
- This replaces the earlier "perhaps 3-6 exact points" in Q5: clef work is worth about 1 point on these sets, at a small and so far clean cost. The pitch gain is real for a piece hit by it (pitch 46% to 86% on those 2 PDFs).

### Possible next steps (no decision taken)

1. Retry with a wider gap when no header clef is found: smallest so far, and clean on the sample with the limit above. Proper tests would be needed before it goes in the reader.
2. Small bass clefs: give them their own centre pitch rather than loosening `maxLineOffset`. Not tested; the effect of that exact form is unknown.
3. Bass knob taken for a head: needs a stricter check than the one tried. Open.

### NOT RUN

- Full test suite, `tests/test_awkward.py`, `tools/diff_check.py`: no reader change kept.
- Candidate on the unseen half, on the clean PDFs outside the 60, and on the Mozart and Chopin real scans in `bench`, which are outside the permitted scan data.
- Own centre pitch for small clefs; a stricter bass check; a size check on the clean sample.
- 5 inspect PDFs give no reading (4 tiny images, 1 crash), so their clefs are not counted.
- A count of how often the retry fired on the clean sample.
- Why the knob part is beyond the gap on these two PDFs in particular, and a proof that staff-line removal is what cuts it.
