# Pre-scan research report (2026-11-04)

Written by an Opus max-effort research agent. Saved here by the main session because the agent was not allowed to write this file. Scripts and data are in this folder. Readings are in `/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/prescan/runs` (temporary).

Checked by the main session against source: `engine/read_pdf.py` keeps `scores[0]`; the log records 8 GB, 2 CPUs and 784 MB in the sandbox; `du` of the homr venv is 728M; Parratt 6679725 is in the tuning half. Everything else is the agent's report, not independently reproduced. `merge3.py` is an unreviewed prototype.

## Bottom line
- The merge as written does nothing on the fair test: it would only measure the current reader.
- A corrected per-staff prototype (`merge3.py`) works mechanically. Its bar-level gain on real voice-and-piano scans is untested, because none exist on disk.
- 68.2% is not a realistic target for these songs. Rough estimates (inference) stay below it.
- New defect: `engine/read_pdf.py:505-512` silently keeps only the first "movement" file. It returned 5 of 71 bars with outcome "done".
- 728 MB is not the sandbox's memory.

## Corrections to earlier numbers
| Earlier | Measured |
|---|---|
| Mozart 18 of 34 | 18 of 33 net (54.5%), or 21 of 39 gross. Rule 3 still fails. |
| 60 pieces | 60 PDFs, 52 pieces. |
| Merge 48.8 / 62.9 / 44.4 | Older `mergexml.py`. `merge2` gives 53.8 / 63.2 / 50.8 (the 50.8 is the guard, identical to the current reader). |
| homr several-part 14.4 | Partly a scoring artefact: 16 of 46 PDFs can never score under part-and-staff labels. By staff position 41.7%. Voice and piano alone 30.0%. |
| Claude sandbox 728 MB | 728M is the homr venv on disk. The log records 8 GB and 2 CPUs, and Audiveris peaked at 784 MB there. |
| Rule 4 passed | Only as a net reading. Literally ("no piece loses more than 1 bar") it fails: Mozart 3, Beethoven 2. |
| bench-scan is voice and piano | 59 of 60. Parratt, the only PDF on disk, is choir plus piano. |

The same artefact hits the current reader: clean is 53.6 strict but 72.4 by staff position. The unseen 76 and 70 are a second look, so that half is no longer a first look.

Confirmed: 141 to 174, 139 to 173, 25 to 85, 18 to 76, 70, 68.2, and clean current/homr 53.6, 21.3, 62.7, 43.4, 50.8. The merge rule wording matches the code; its "unless" clause never changes the outcome.

## Q1. Can the merge help the fair test?
Not as written. A corrected per-staff design probably can, unproven on real songs. Confidence: high for "as written does nothing" and the bug breakdown, medium for the design on real voice-and-piano.

Measured:
- References: 59 of 60 have shape (1,2) (`truth_shapes.py`).
- Current reader: 70 of 70 clean voice-and-piano PDFs came out as several parts, 3 simulated scans among them (`census_parts.py`). So `merge2.py:118` returns them unchanged.

Why several-part merging scored lower on clean PDFs (`several_decomp.py`, strict exact bars):
| Version | All 46 PDFs (2,104 bars) | Voice+piano (1,010) | Four single staves (440) |
|---|---:|---:|---:|
| Current reader | 1069 | 700 | 345 |
| Old merge | 934 | 645 | 275 |
| New rule, first-part bug kept | 937 | 647 | 276 |
| New rule, staff by position (`merge3`) | 1009 | 705 | 289 |
| homr only when current's staff is short | 1112 | 730 | 358 |

- Voice and piano: the loss was the `phs[0]` bug, which writes homr's voice part into the piano staves. Fixed, it becomes +5 bars.
- Quartets: the loss is real. homr reads them as two pairs, and in "notes differ, both add up" it was right 11 times against the current reader's 147.
- Per staff, clean voice+piano (current / homr / either): voice 89.8 / 68.4 / 94.0, piano upper 81.1 / 53.1 / 84.8, piano lower 84.3 / 61.5 / 88.0.
- Bars, clean voice+piano: current 700, homr 324, perfect chooser 768.
- 8 of 30 homr readings have parts of different lengths, so bars must be paired per homr part.

Real multi-staff scans, Parratt's book: 13 choir-and-piano pieces, 113 pages, 1,068 bars, references from that edition. One piece in the tuning half, none in unseen, 12 in neither. Whole bars are useless here (6-9 staves): current 1, homr 7, merged 3. Staves right, on the 7 pieces with matching staff counts (`book_branch.py`):
| | Current | homr | Merged |
|---|---:|---:|---:|
| Voice staves | 38.7% | 53.4% | 52.0% |
| Piano staves | 29.9% | 51.9% | 51.0% |

Each branch of the rule (staves where only homr was right / only current was right):
| Branch | Five real | Inspect | Book | Clean V+P |
|---|---:|---:|---:|---:|
| Differ, both add up (takes homr) | 27/7 | 36/2 | 209/27 | 23/57 |
| Differ, only homr adds up (takes homr) | 16/0 | 25/0 | 169/1 | 16/0 |
| Same notes, only homr adds up (takes homr) | 12/0 | 26/2 | 169/7 | 45/0 |
| Differ, only current adds up (keeps) | 0/4 | 0/1 | 15/11 | 0/57 |
| Differ, neither adds up (keeps) | 1/0 | 1/0 | 56/7 | 0/0 |
| Same notes, other (keeps) | 9/74 | 10/14 | 123/152 | 21/578 |

`merge3.py` checks: matches `merge2` on one-part readings (3, 65, 47, 15, 44 = 174). It drew all 13 book pieces, Mozart, and 3 simulated voice-and-piano scans (plumbing only). Kinkel page 1 compared by eye with its source: voice and piano land on the right staves. That check found lyrics lost in swapped bars; copying them restored 2,579 of 2,601, exact bars unchanged.

Inference, rough and wide. Piano-bar rate times a voice factor of 0.75-0.9 (about 0.5 for the book row):
| If songs behave like | Current (= merge as written) | `merge3` |
|---|---:|---:|
| OLiMPiC | 10-18% | 35-44% |
| Five piano scans | 42-50% | 52-62% |
| Choir book | about 5% | about 18% |

homr's training: its code lists 7 excluded scores, none among our 60. `memory_test.py` on 8 tuning pieces with 273 altered notes, clean renders only: altered notes read as printed 78.8%, as the original 1.5%; unaltered read right 75.7%, a step off 1.9%. No sign of note memory; familiarity with the style not ruled out.

NOT RUN: any real voice-and-piano scan.

## Q2. Why Mozart failed rule 3
The kinds of cause are general; the share is specific to this piece and set. No chooser fix is justified. Confidence high, on tuning data. Bars count from 0 (`ledger.py`).
| Piece | Wrong at baseline | Perfect-chooser gain | Gained | Lost (bars) | Net |
|---|---:|---:|---:|---:|---:|
| Bach | 24 | 3 | 3 | 0 | +3 |
| Beethoven | 15 | 7 | 5 | 2 (47, 48) | +3 |
| Grieg | 12 | 7 | 6 | 0 | +6 |
| Chopin | 14 | 9 | 4 | 1 (2) | +3 |
| Mozart | 47 | 25 | 21 | 3 (14, 15, 53) | +18 |
| Total | 112 | 51 | 39 | 6 | +33 |

- Mozart holds 42% of the wrong bars. A perfect chooser would still get 49% of its gain there.
- Mozart's 21 gained bars: 6 a left hand off by a clef, 12 with 1-4 notes lost or extra, 2 rests, 1 accidental.
- Specific to it: 20.5% of its bars have a clef change, against 6.3% in the Lieder tuning references. Interline 19, 29% of all bars.
- The 6 lost bars are all "differ, both add up" with homr wrong, from mixed causes.
- Gross elsewhere: inspect 62 gained, 2 lost; unseen totals 59 gained, 1 lost.

Variants (exact bars):
| Variant | Five | Inspect | Clean V+P | Five, gained-lost |
|---|---:|---:|---:|---:|
| As written | 174 | 85 | 705 | 39-6 |
| Keep current unless short | 157 | 60 | 730 | 16-0 |
| Veto if homr has more out-of-key notes | 169 | 72 | 704 | 33-5 |
| Veto if homr jumps more from neighbouring bars | 166 | 77 | 718 | 27-2 |
| Veto if same note names, different octave | 177 | 84 | 714 | 40-4 |

The octave veto was found by tracing Mozart's losses and pushes Mozart's share to 21 of 36; leave it out. Reader agreement (`agree_gate.py`) did not separate good swaps from bad. Rule 3 is not fixable through the chooser, only by a larger set.

## Q3. Proposed freeze and pass mark (owner decides)
Frozen definition:
- Code: `merge3.merge` default call (rule "as_written", no veto, under-half fallback, lyric copy), `homrjoin.py`, `lib.py`, `levels2_lite.py`, `fair_run.py`, plus `clean2.py` and `merge2.py` helpers. Committed somewhere tracked first.
- Readers: `speed/launchers/marks1` (fork dbe09b8a6; the build lives in /tmp and must be copied somewhere durable) and homr 0.6.2 with `homr_safe.py` at 300 dpi.
- Steps: run only on PDFs `is_scan` calls scans; map staves by position, and leave the current reading unchanged if staff counts differ; drop homr pages whose staff shape differs from the commonest; pair bars per homr part; apply the rule per staff; if there is no current reading, or under half of homr's bars, use homr whole. The under-half fallback was added after seeing Parratt and does the job of a reader fix.

Measure: bars exact by staff position, including tie stops. Beside it: strict, pitch, timing, wrong and unwarned, each reader alone.

Halves:
- Tuning: hand-fetch 5 voice-and-piano pieces, inspect freely, fix only general mechanical faults, log each change, then freeze.
- Unseen: hand-fetch; log drops and check print against reference by eye before any reader runs; start from an empty output folder because `fair_run.py` reuses files; aggregates only, one look, one written top-up allowed.

Pass requires all (paired gain over the current reader, same pages):
1. At least 15 pieces and 400 bars; otherwise no verdict.
2. The merge ran on at least 80% of pieces; otherwise a design fail.
3. Gain at least +5 points, and the lower end of the 90% by-piece range at least +2.
4. Removing any one piece leaves at least +2; no piece over half of gross gains.
5. Bars lost at most a quarter of bars gained; no piece down by more than 2 bars or 5%, whichever is larger.
6. Every merged file draws, no crashes, pitch and timing not lower, wrong-and-unwarned count not higher.
7. Merged not more than 2 points below homr alone.

Fail: upper end of the range below +5, or a harm rule (5 or 6) breaks. Otherwise inconclusive: use the top-up once. 68.2% and 75% are reported separately and don't decide this.

Evidence: the five pieces under these marks give +13.0 points (range 6.6 to 20.3), leave-one-out +8.3, failing only on too few pieces and Mozart's share (`five_verdict.py`). Simulated at 15 pieces with spread from those five (inference):
| True gain (points) | 0 | 3 | 5 | 8 | 10 |
|---|---:|---:|---:|---:|---:|
| Chance of passing | 0% | 13% | 41% | 91% | 99% |

`fair_run.py` codes rules 1-5 and the drawing check, not the pitch, timing and unwarned checks, rule 7, or the fail/inconclusive labels.

## Q4. Pipeline rehearsal
`fair_run.py` ran from nothing on one 4-page book piece (87 s) and on all 13 pieces reusing readings; piece 1 went through the real `read_pdf`. Extraction, truth, both readers, merge, scoring and drawing all ran.

What broke:
1. Parratt is choir plus piano, so the main case stays untested.
2. First-movement loss: 4 of 13 pieces kept 5 of 71, 27 of 63, 3 of 38 and 11 of 95 bars, with no warning. Chain on piece 1, from its log: a false one-staff system, the next system counts as indented, a new movement, then `scores[0]`. 0 of 160 tuning-set readings are this short.
3. `ProcessingSwitches.indentations=false` removes the split with no code. Pitch on the four: 0.6 to 66.3, 31.1 to 80.6, 0.8 to 73.1, 2.3 to 73.3. Not applied, not run on clean PDFs.
4. Staff grouping on real pages: 16 of 113 pages have uneven systems, 5 of 8 on piece 1, which then reads 143-148 bars for 71. Flattening did not fix it. Cause not traced. Whether songs trigger this is the biggest unknown.
5. Staff counts disagree: on the 13 pieces the merge ran on 5, the fallback on 4, 4 stayed unchanged.
6. Strict scoring gives homr's pairs, such as (2,2,2) for (1,1,1,1,2), zero by construction. Scoring needs staff position.
7. homr page shapes vary: 7 of 105 pages differed from the commonest. The old `zip` join in `run3.py` would mix them in; `homrjoin.py` drops them.
8. Page ranges: contents page numbers don't match the PDF and the detector missed a music page (p.17). Only piece 1 was checked by eye.
9. OpenScore `.mxl` has no page or system marks, so the print-against-reference check must be by eye.
10. `SELECTION.md` says "keep 2-8 pages" but allows dropping only "over 12". One-page songs and 9-12 pages are undefined. The server reads 8 pages; the runner reads all.

Confidence high on what happened, low on how often it happens on songs.

## Q5. Memory and time
PSS summed across the process tree, `server.app` imported except in the 2-CPU run. Seconds approximate: load reached about 42 on 20 logical CPUs. No memory cap was possible.
| Run | read_pdf | homr | Total | Peak PSS |
|---|---:|---:|---:|---:|
| Mozart 4 pp, 4 CPUs, homr after | 48.5 s | 96.6 s | 151 s | 2,372 MB |
| Same, homr alongside | 136.6 s | 27-32 s/page | 142 s | 2,777 MB |
| Mozart, 2 CPUs, homr after | 93.8 s | 107.3 s | 206 s | 1,891 MB |
| Parratt 8 pp, 4 CPUs, homr after | 63.4 s | 129.5 s | 194 s | 2,305 MB |

- homr stage peak: 1,031-1,132 MB.
- homr alone, one page: 840 MB by default; 634 MB with 2 threads, no arena, no spinning. Same time, same notes (`homr_lean.py`).
- Merge plus preview: about 5 s, at most 296 MB (partial render only).
- `OMP_NUM_THREADS` does not limit homr; 56 threads per process seen.

Cloud Run (inference): two JVMs already peak near 2.3 GB, so homr after the read adds no peak, but total time is about 3×. Alongside costs about 400 MB more and saves almost no time.

Sandbox: at 8 GB memory fits. The blocker is that homr 0.6.2 and rapidocr-onnxruntime 1.4.4 require Python below 3.13, and the sandbox runs 3.13 (pip dry run). homr 0.7.0 appears available for 3.13 but is a different, untested release. Adds about 27 s a page on 2 CPUs.

NOT RUN: real sandbox; Cloud Run; production speed; draft model on the same instance; full card render; a hard memory cap.

## Also NOT RUN or open
Test suite, `test_awkward`, `diff_check` (no engine change). Independent review of `merge3.py`. `indentations=false` on clean PDFs. Choosing among current-reader builds.

## Limits kept
No imslp.org. GitHub and PyPI only, for homr's code and a pip dry run. No home PCs, cloud, commits or deploys. No source files changed; first runs may have refreshed `__pycache__`. Process count stayed within 10, but homr's own thread pools ran well above that. Touched on unseen halves: OLiMPiC totals from `levels2.py` and `wb.py`, gained and lost totals, bar-ratio counts including min and max over PDFs (no references used); bench-scan reference shape counts and total bars only. bench-pitch and bench-octave not opened.

## Reproduce
Run with `/home/kema/projects/sheet-music-plugin/.venv/bin/python` from this folder. Per-run data is in `results/`.
- Q1: `census_parts.py`, `truth_shapes.py`, `clean_rescore.py`, `several_decomp.py`, `vp_clean.py`, `branch_value.py`, `book_batch.py`, `book_score.py`, `book_branch.py`, `memory_test.py`
- Q2: `ledger.py`, `rule_variants.py`, `octave_veto.py`, `five_gross.py`, `clef_rates.py`, `agree_gate.py`, `lost_gross.py`
- Q3: `fair_run.py`, `five_verdict.py`, `power.py`, `share_sim.py`
- Q4: `pipeline.py`, `noindent.py`, `noindent_score.py`, `short_readings.py`, `flatten.py`
- Q5: `memwatch.py`, `memruns.sh`, `homr_lean.py`

## Decisions for the owner
1. Run the test on today's merge, or change it first? Recommended: staff-by-staff version first.
2. Fix the "first section only" fault before the test? Recommended: yes, with a check on clean PDFs.
3. What counts as passing? Recommended: at least 5 points of improvement on the same pages, with 68.2% and 75% reported beside it.
4. How many hand downloads? Proposed: 5 practice and 15 test songs, about 20 files, after the ban ends.
5. Loosen "no piece loses more than 1 bar"? Proposed: bars lost at most a quarter of bars gained, and no piece down by more than 2 bars or 5%.
6. Accept that homr may have trained on these songs? Recommended: accept and state it with the result.
7. Which current reader is the baseline? Recommended: reader-next build (marks1).
8. A pass would not ship anything by itself; licence, reading time and a Claude version with homr 0.7.0 stay open.
