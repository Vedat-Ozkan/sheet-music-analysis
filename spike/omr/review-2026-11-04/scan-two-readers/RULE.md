# Two readers on scans: acceptance rule, written 2026-11-04 before any combined result was seen

Goal: 65% of the way from 55.7% to the owner's 75%, so at least 173 of 253 bars (68.2%).
Measure: strict exact bars (`whole_bars.py`, per part and staff).
Set: the five real full-page scans (tuning data): bench-real (3) and the two real scans in bench.

A combination counts as meeting the goal today only if:
1. It chooses without looking at the reference.
2. It reaches at least 173 of 253 bars.
3. Removing any one piece, the gain over the current reader stays positive, and no piece supplies more than half of the gain.
4. No piece loses more than 1 exact bar.
5. It also gains on the bench-olimpic inspect half.
6. Clean PDFs are not touched: it runs only on PDFs the existing rule calls scans; check that rule on the clean benchmark PDFs.

Any result today is a tuning result. The fair measure is the unseen half of bench-scan, not yet downloaded. Each threshold tried is logged here with its result, and no thresholds are fitted bar by bar.

## Tried, in order (five full pages, of 253 / inspect half, of 172). Baseline 141 / 25.
- homr alone at 200 dpi: 130 / 85.
- Whole bar, homr when pitches differ and its bar adds up: 162 / not run.
- Per staff, same: 162 / 27. No time signature on inspect excerpts, so nothing could add up there.
- Plus homr when only homr's staff adds up: 169 / 27.
- Plus ties copied from the current reader: 169 / 27 (no effect, dropped).
- Plus current rhythm with homr's pitches: 169 (no effect, dropped).
- Plus usual bar length when no signature was read: 169 / 71.
- Plus homr's whole reading when the current reader gives none: 169 / 85.
- Plus homr when neither staff adds up: 170 / 86.
- homr alone at 300 dpi: 143 of 253.
- Same combination at 300 dpi, analysis objects: 173.

## Result on real merged MusicXML, scored with score_pdf (`two300d`, 300 dpi)
Per staff: same notes keep the current reader, unless only homr's staff adds up; different notes take homr, unless only the current reader's staff adds up. No current reading: homr whole.
- Five pages: 141 to 173 of 253 (55.7 to 68.4). Pitch 89.2 to 95.6, timing 80.1 to 92.5. Bach 0 to 1, Beethoven 62 to 65, Grieg 41 to 47, Chopin 12 to 16, Mozart 26 to 44. Wrong and unwarned 64 of 108 to 48 of 75.
- Inspect half: 25 to 85 of 172 (14.5 to 49.4), pitch 77.3 to 96.5.
- Unseen half, one look, aggregates: 18 to 74 of 161 (11.2 to 46.0), pitch 68.9 to 94.3, timing 49.7 to 83.7. No crash.

## Against the rule
1 pass. 2 pass (173). 3 FAIL: Mozart gives 18 of 32 gained bars, over half; removing any one piece the gain stays positive. 4 pass. 5 pass. 6 pass on benchmarks: 170 of 170 clean named not scan, 93 of 93 scans named scan.

## Verovio crash, three causes in homr's output, all fixed in clean.py
A rest followed by a note marked chord; repeated key/clef/time when pages are joined; no staves declared in the first bar. Before 33 of 45 loaded, after all. A fourth was my merge splitting cross-staff chords.

## Cloud Run, job homr-timing, gen2, 4 vCPU, 4 GiB, 2026-11-04 (job and image deleted)
Per page at 4 threads, process start included: Chopin 46.1 s, Mozart 25.3 s, Beethoven 14.3 s, Grieg 20.9 s, mean 26.6 s, peak 0.9-1.2 GB. 2 threads: 43.9, 28.5, 15.6, 24.6 s. Image size not captured.
Compute 26.6 s x 0.000106 USD/s = 0.0028 USD a page, list rates from entry 32's formula; production may be slower.

## Seen on the page, Mozart p1 against the print
Most bars right. Bars 1-4 left hand lose the printed treble clef, so 2 and 4 are low; bars 14-16 right hand look too high; bar 15 is not the printed music; rests lost in bar 8.

NOT RUN: voice-and-piano scans on real prints; both readers in the real server path; Claude sandbox; test suite; diff_check; test_awkward.

## Clean PDFs, same 60 as the clef check, 2,759 bars, 300 dpi
Current reader 1480 (53.6%), pitch 98.5, timing 92.0. homr alone 587 (21.3%), pitch 92.6, timing 74.0. Merge rule if it ran on them 1346 (48.8%), pitch 93.2, timing 88.3. Per PDF: current better 54, homr better 2, tie 4. One page failed in homr. So homr does not replace the current reader, and the merge must stay scans only.

## After the Opus review (opus-review.md), corrected merge `m4*` (merge2.py, clean2.py)
Changes: accidentals written from pitch and key; ties copied from the current reader; rests no longer deleted; repeated key/clef no longer deleted; markings keep their place in the bar; "neither staff adds up" branch removed; several-part readings left to the current reader.
The review's check was also corrected: a key for both staves now replaces an earlier one-staff key. Baselines rescored the same way.
- Five pieces (11 pages): exact 141 to 174 of 253 (55.7 to 68.8). With drawn signs right 140 to 174. Also tie stops right 139 to 173 (68.4). Also grace-note count right 127 to 161 (63.6). Pitch 94.9, timing 93.0. Wrong and unwarned 48 of 74.
- Inspect: 25 to 85 of 172; with ties 23 to 83.
- Unseen, second look, aggregates: 18 to 76 of 161 (47.2); with ties 18 to 70 (43.5).
- Crashes 0 of 85 files.
The signs level now passes by construction, since signs are written from the pitch. It shows consistency, not that the key is right.
Rule: 1 pass. 2 pass. 3 FAIL, Mozart gives 18 of 34. 4 no piece down overall; bars lost inside pieces not recounted for m4. 5 pass, gain is mostly homr's. 6 pass on benchmarks.
Seen on the page, Bach p1: signature changes at bars 9 and 11 that the print does not have (the current reader's key misread), flags instead of beams in homr's bars, fingering read as a large 8 in bar 6.
Licence: homr code and weights AGPL-3.0; its LICENSE_FAQ says all released transformer checkpoints include Camera-PrIMuS (CC BY-NC 4.0 on the Hugging Face copy), and whether that carries to the weights is an open question. No commercial licence on offer.
