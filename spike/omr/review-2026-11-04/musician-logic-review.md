# Review of the "think like a musician" plan for the PDF reader

Written 2026-11-04. Reader sma.6 (benchmark variant `pitch39`). Read-only: nothing in the repo or the fork was changed. Scripts and raw outputs are in the scratchpad folder `mlr/` (full path in the appendix).

How to read the evidence labels:
- **Measured**: I ran it on cached sma.6 readings, or on new readings where stated.
- **Code**: I read it in the fork or the engine.
- **Read**: from a published source (links at the end).
- **Guess**: my judgement, with no test behind it.

Tests with a stop rule written first are marked **pre-registered** (`mlr/NOTES.md`). All others are **exploratory**: treat them as leads.

Two scorers appear below:
- The benchmark scorer gives the 95.6% and 88.8%. It counts the two PDFs that fail outright as zero.
- My scorer (`mlr/mx.py`) parses MusicXML directly. It covers 181 PDFs and 144,670 notes, excludes those two PDFs, and gives pitch 97.8% and pitch+onset 91.0%.

Gains from my scorer have NOT been re-run through the benchmark.

## 1. Verdict on the plan

**The repair half fails its own kind of test. The clues half is partly right, but only as a way to detect errors and read time from alignment.** I ran your cheap test on the cached readings (pre-registered, using MusicXML only: types, dots, beams, voices, `default-x`). I allowed one edit per voice that does not add up: change a value, add or drop a dot, add or drop a rest, move a note to another voice, or make a triplet.

| Result on bars flagged in the reading but not in the reference | Count |
|---|---|
| Bars flagged | 1,007 |
| Already exactly right | 89 |
| Wrong | 918 |
| Have a candidate edit that gives the right onsets (coverage) | 97, about 11% (my stop line was 35%) |
| Have exactly one edit that makes the bar add up | 47 |
| Of those 47, edits that were right | **0** |
| Median candidates per bar | 10 (90th percentile 115) |

- **The ranking works only when the right answer is on the list.** On those 97 bars the top choice is right 91% of the time (two-fold by piece). Over all 395 ranked bars it is right 22% of the time.
- **Confidence runs the wrong way.** Top choices above 0.9 confidence were right only 14% of the time. The ranker was trained only on bars that had a right candidate, so it never learned to abstain. That is a limit of this prototype, but gates on absolute alignment do not rescue the idea either. The best ones, chosen after seeing the data, repaired about 100 bars at 61-63% (exploratory).
- **Why coverage is so low.** One misread symbol derails several voices at once (`SlotMapper` is greedy), and 322 bars have a failing voice that no single edit can fix. The error is not local in the reader's voice structure. This agrees with entry 90: 44 of 49 "voice-only" bars also missed symbols.

**Strongest argument against the plan.** "Makes the bar add up" is not evidence. The test above shows that directly, and the published attempt says the same.
- Church & Cuthbert (2014) did this on SmartScore output, using repetition, other parts and edit priors. They corrected 18.8% of flagged measures (range 2.1-36.1%) and report "metrically plausible but incorrect emendations". They also assumed a flagged measure is never right, and about 9% of ours are.
- A repair by expectation also copies a known human weakness. In the Brahms Op. 76/2 story, skilled readers missed a misprint even when told it existed, and a weak sight-reader found it (Wolf 1976, retold by Sloboda). Editors deal with this by flagging doubts for a person (Henle), not by correcting from expectation.

**What is right in the plan**
- Vertical alignment is by far the strongest clue. Alone it picks the right candidate 85% of the time on the 97 bars.
- Keeping repaired bars marked is right, and should be stricter (section 3).
- The target is right at note level. Timing errors in flagged bars are the largest loss (table below).
- The crop test was worth running: Claude got 9 of 24 flagged bars exactly right, which lands between my GO and STOP lines (section 5).

**What is wrong**
- **Spacing is not proportional to duration.** LilyPond's manual says doubling a duration *adds a fixed amount* of space. Measured on bars read right, each doubling widens the median gap by only 1.02 to 1.53 times, and a shorter gap is as wide as one twice as long 6-22% of the time on MuseScore and Verovio, and 17-42% on LilyPond. Alone it picks the right candidate 54% of the time, repetition 56%, beam grouping 46%. Gaps also measure the time between columns across all staves, not a note's own value.
- **Your flag estimate is too low.** The subtraction is invalid because flags in the reading and in the reference barely overlap. Counted bar by bar (8,073 paired bars):

| | Bars | Share | Read exactly right |
|---|---|---|---|
| Flagged in both | 126 | 1.6% | 9 |
| Flagged in reading only | 1,028 | **12.7%** | 93 |
| Flagged in reference only | 380 | 4.7% | 255 |
| Flagged in neither | 6,539 | 81.0% | 5,341 |

The real rate is about **13% overall and 16% on the main sets** (not 8% and 13%). 91% of reading-only flags are real errors. The 380 reference-only bars are a checker question I did not investigate.

- **The target population is too small.** Of 2,375 wrong bars in that count, only 1,052 (44%) are shaded. Repairing flagged bars leaves 56% of wrong bars untouched and unwarned.
- **Alignment is not a new clue.** `SlotsRetriever` already builds time slots from horizontal position. What is unused is the *disagreement* between that grouping and the computed times.

**What is missing: three things bigger than most of your list.**

1. **Two PDFs fail completely, and they are 1.7 points of both headline numbers.** `p-29-3--vr` and `ly-tschaikowsky-op37.1--ly-old` give "No music could be read". I reproduced both through `read_pdf` with the sma.6 install.
   - Causes: a null `rect` in `MetronomeInter.getNoteGlyph` at TEXTS (only with OCR on), and `Denominator is zero` in `AbstractChordInter.getDurationSansDotOrTuplet`.
   - One failed system loses the whole book, in both settings.
   - They hold 2,601 of 148,731 notes. At set-average accuracy the headline becomes about 97.3% and 90.3%. Read with OCR off, `p-29-3--vr` scores 98.4% and 82.1%.
2. **Parts are split across systems in 33 of 181 PDFs** (Verovio 21, old LilyPond 6, MuseScore 4, LilyPond 2). The Bach chorale reads as 8 parts: "Soprano" on the first system, "S." after. A voice becomes "V0." and "Voice". `PartCollation` uses part names, and its own comment calls that "questionable for lack of OCR reliability". The pitch score pools parts, so it cannot see this, but the engraved copy can. All-rest part-bars: 4,870 read against 1,107 in the references.
3. **Grace notes: 39% found** (581 of 1,424 by my count). Log 98 has a 1-2 day fix that was never scheduled.

Where the notes go (my scorer, percent of 144,670 notes):

| | In shaded bars | In unshaded bars |
|---|---|---|
| Right | 10.91 | 80.06 |
| Right pitch, wrong time | **5.49** | 1.32 |
| Wrong pitch | 0.46 | 0.93 |
| Missing | 0.22 | 0.39 |

Bars not paired with a reference bar hold another 0.22.

Wrong bars by kind (my scorer pairs bars slightly differently: 2,101 wrong, plus 25 unpaired):

| | Shaded | Unshaded |
|---|---|---|
| Timing only | 573 | 256 |
| Wrong pitch | 198 | 522 (294 of them in the old LilyPond set, where the reference is another edition) |
| Notes missing only | 148 | 230 |
| Extra notes only | 93 | 81 |

**What replaces the repair.** Read time from alignment, flag disagreements, and leave the shading on.
- *Flag (exploratory):* two chords in different voices at the same x but different times, or the same time more than 2.5 spaces apart. On 5,907 unshaded bars it fires on 206. 188 are timing errors (91%), which is 24% of silent timing errors, with 18 false flags among 5,139 right bars. It fires on 615 of 1,007 shaded bars. This is a few lines of Python on data the MusicXML already has.
- *Retiming (exploratory):* take a voice that fills the bar and re-time other voices' chords that line up with it. 488 bars change, net +1,032 notes (about +0.7 point of pitch+onset). 366 bars get better, 45 worse, 87 become exact. This handles several errors in one bar because it does not search edits.

## 2. Each problem

### Key signature losing its last flat
- **Musician:** reads the signature as a unit. The order is fixed, it repeats on every staff and system, and a natural on a note that is already natural means the signature must hold one more flat.
- **Clues:** compare the last flat with earlier flats in the same signature instead of the fixed `minFlatTrail` of 0.7 spaces. **Code:** `KeyColumn` replicates only within a part, and HEADERS runs before any note exists. **Measured (exploratory):** printed naturals that change nothing, on the next step in the flat order, give 50 and 10 on the two wrong PDFs. Among PDFs with the right key only Berg (7) and atonal key-0 pieces (6-14) reach 5 or more. N=2, so weak.
- **Where:** reader for the fix, post-processing for the alarm.
- **Payoff:** all notes on that step in those files. Key errors are 174 bars and 360 notes in 5 pieces, not all this cause. High confidence, small reach. This is the same root cause as log 102: fixed constants judged against one font.

### Octave lines
- **Musician:** the dashed line with its hook is the evidence; the letters only confirm it.
- **Where:** reader, already committed (`4742281f2`; the worktree also has an uncommitted change in `LinksStep` and `OctaveShiftInter`).
- **Payoff:** release it, then stop. `pitch42` is unchanged on the main sets I checked (for example main 0.9771, 0.9125, 318 flags). Remaining class: 14 bars plus 77 "an octave off, no line in the reference". Look at those 77 before more line work; some may be false lines or edition differences. Medium confidence.

### Split bars and a repeat in mid-bar
- **Musician:** adds the two halves. A repeat sign does not end a bar if both sides sum to one bar.
- **Code:** `MeasureFixer` (lines 301-312) already sets pickup and first and second half, but only from durations, so wrong rhythm defeats it.
- **Where:** reader, using times from columns.
- **Payoff (measured):** 32 read bars have no reference bar. 29 PDFs have the wrong bar count, 10 bars too many and 24 too few, so merged bars are more common than split ones. Few notes, but every later bar number shifts in chat. Medium.

### "sf" read as text
- **Musician:** small vocabulary, dynamic font, no lyrics on a piano staff.
- **Where:** post-processing. **Code:** `canHide` erases the ink, but the letters survive as a lyric, so converting them needs no image work. Part of `text_meaning`.
- **Payoff (measured):** 208 dynamic-looking lyric items, 101 of them in parts with few real lyrics. Dynamics are 78.9% found and 77.1% right overall. Visible on the copy, no effect on harmony. Cheap, high confidence.

### False marks on digits, "Ped." and "va"
- **Musician:** a mark has a place, centred on a head, and a digit is not a mark.
- **Clues:** PDF text glyphs say "this ink is text". This differs from entries 93-94, which looked for music in font characters; here the font only rules ink out. **Guess:** most text-bearing PDFs have this; log 97 measured music fonts (80%), not words. Scans still need OCR.
- **Where:** reader, masking before SYMBOLS.
- **Payoff (measured, some "false" marks sit on notes with wrong onsets):** staccato 2,361 false of 9,791 read, tenuto 431 of 1,020, fermata 137 of 357. Precision perhaps 75% to 85-90% (guess). No harmony effect.

### Fingering clutter
- Reader exports no `<fingering>` (0 against 130). Digits reach us as words or false marks. Drop digit-only words (branch `text-meaning` does) and mask the ink with the step above. Recovering fingerings: nowhere, as the owner asked.

### Timing in Chopin bar 16 (`SlotsRetriever.areAdjacent`)
- **Musician:** a second between voices is printed with heads touching. The next event has a gap.
- **Code:** a stemless head within 2 steps of another chord, and close enough in x, counts as simultaneous. That is too loose for whole notes.
- **Where:** reader.
- **Lead (measured, exploratory, not tied to this rule alone):** the same-time-far-apart check fires on 427 of 1,007 shaded bars and 145 unshaded ones, so slot merging may be a large root cause. Tightening it is NOT RUN.

### Ties
- **Musician:** a tie joins adjacent notes of one pitch; each note of a chord has its own.
- **Measured:** ties 73.0% found, 76.7% right. Of 416 chords with 2+ ties, 292 are right, 90 read only some, 34 none. **The tempting rule fails:** tying every shared pitch adds 99 right ties and 402 wrong ones, because partial ties are normal (Wikipedia's tie article says so too).
- **Where:** reader, re-checking after RHYTHMS with arc ink. **Code:** the tie decision (`isSpaceClear`, 25% invasion) runs before time exists.
- **Payoff:** playback and copy only, not harmony (guess, not tested). Medium-low.

### Lost rests
- **Musician:** a gap in time raises the question; a rest sits at a fixed height, so the eye finds it.
- **Measured (pre-registered, "look again"):** templates cut from rests the reader found in the same file, searched at the same height against ink nothing else explains. On 14 PDFs chosen as worst for lost rests, 338 lost rests: 136 found with 23 false at the strict setting, 159 with 96 at the looser one.
- **Read that with care.** 78 of the 136 come from one PDF (Op. 18/4 i, old LilyPond). Without it, recall is 23%, under my 30% stop line. Hits are counted per staff, bar and shape, not by position, so this is an upper bound. Some "lost" rests may not be printed (entry 93). Scans: 10 of 38. It tests finding only, not inserting rests or the timing gain.
- **What differs from entries 90 and 93:** those looked for rejected candidates and font characters. This looks in the ink using the file's own shapes.
- **Where:** reader, at RHYTHMS. **Payoff:** strong on old fonts, uncertain elsewhere. Pitch+onset gain NOT RUN; perhaps +0.2 to +0.5 point (guess).

### Silent wrong pitches
- **Musician:** the ear helps less than people think; plausible wrong notes are exactly what experts miss.
- **Measured (exploratory):** causes across all sets, shaded or not: accidental 190 bars, key 174, other 121, step off 116, octave with no line 77, clef 36, octave line 14, grace accidental 11.
- **Harmony checks do not work.** Rare chord types, local pitch rarity and cross-relations give AUC 0.50 to 0.62. The best is two spellings of one note at the same moment: 43 of 121 accidental bars, overall precision 45%, 1.9% false on right bars. This is a simple statistical model; a stronger one is NOT RUN.
- **A second reader does better.** homr on 12 PDFs picked by hash: it disagrees on 20 of 36 wrong bars and on 39 of 398 right bars (precision 34%), and its set of pitches matches the reference on 12 of the 36. Small sample, mostly accurate PDFs. Bugge et al. found voting only modestly better than single readers.
- **"Explain every mark" fails as a flag.** Unexplained ink has AUC 0.72-0.75 but catches 7 of 223 at 3% false flags (pre-registered; passes one half of an either/or rule, not usable).
- **Where:** flags in post-processing; fixes in the reader. Expect flags on a quarter to a third, not fixes (guess).

### Two real voices on one staff
- **Musician:** stems. In one voice, direction follows the middle line; a stem against that rule means a second voice.
- **Measured (exploratory, on reference files, unbeamed notes):** 1.8% of one-voice staff-bars break the rule, 76.5% of two-voice ones do; adding "two stems at one start" reaches 95.6%. Entry 95's "mixed stems" fires on 21% of one-voice bars. This is a real difference from entry 95, and it only detects voices. Assembly with it is NOT RUN, and old editions may vary.
- **Where:** reader, in voice mapping. **Payoff:** these are 9% of bars and 44% right in entry 95; 60-70% is a guess.

### Unmarked triplets
- **Musician:** three equal notes between two beats of another staff.
- **Clue:** count events between beat columns. Entries 90 and 95 inferred from durations or beam groups; this uses another staff as the clock. It does not help a solo line. NOT RUN.
- **Where:** reader or `triplets.py`. **Payoff:** 3% of bars, low confidence.

### Text meaning
- Keep it table-driven and small. `_repaired` with `_MISREAD_CRESC` is a per-case patch on OCR garble, the kind the owner rejects. Reading the PDF text layer removes the need on born-digital files. Post-processing. Low risk, visible, no harmony effect.

## 3. One shared design?

**Partly. There is one layer for a class of these, and it is not a "semantic" layer.** My data supports checks against conventions that almost never vary. It does not support reasoning about what music is likely.

| What was tried | Result |
|---|---|
| Same column means same time | 91% of flags right |
| Stem against the middle line | 1.8% of one-voice staff-bars break it |
| A natural must change something | separates both lost-flat PDFs from tonal right-key PDFs (N=2) |
| Harmony and pitch rarity | AUC 0.50-0.62 |
| The one edit that adds up | 0 of 47 when unique |

**The design: check, doubt, look again, decide.**

```
BarTable, one per bar
  columns:  x -> time, and where the time came from (complete voice, or reader)
  events:   part, staff, voice, x, stem, beam group, type, dots, rest, pitches,
            printed accidentals, ties, and for book-level checks: inter id, grade, bounds
  fill:     per staff, how much of the bar is accounted for
FontProfile, one per file
  per shape: templates and typical size, taken from that file's confident symbols
Doubt
  kind, bar, staff, x range, y range, shapes wanted, which check raised it
Decision
  doubt, ink score, action: shade | retime and keep shade | add symbol
```

- **Checks** are small pure functions, BarTable to Doubts, each one stated convention: same column same time; a staff fills its bar; stem against the middle line; a printed accidental changes something; the key order is canonical and agrees across staves and systems; two short neighbouring bars sum to one; a part continues across systems when its staff layout does.
- **Look again** is one function: find this shape in this region of unexplained ink, using this file's own templates.
- **Decide** is one rule. A symbol is added only if the check needs it and ink confirms it. "No ink, no symbol" stays. Time may be re-read from columns without ink, but that bar keeps its shade. A bar loses its shade only if every check passes and every added symbol has ink. Expectation (harmony, repetition) may raise a doubt or break a tie, never justify a change.

**What the reader has at each step (Code)**

| Step | Available | Lost or missing |
|---|---|---|
| HEADERS | staff projections | no notes; key cut by fixed constants; replicated within a part only |
| TEXTS | OCR words | runs before chords; the metronome crash is here |
| CURVES, LINKS | heads, arcs, geometry | no time yet, so ties are decided without it |
| SYMBOLS | glyphs left after erasing | classifier keeps its top 2; weak items deleted (design doc L1-L10) |
| RHYTHMS (0.3 s on a timed page) | all surviving symbols with bounds and grades | rejected candidates are gone; the time signature gives bar length, and beats appear only in `TupletGenerator` |
| PAGE | `PartCollation`, `MeasureFixer`, export (PAGE 3.8 s on that page) | |
| MusicXML in `read_pdf` | types, dots, beams, stems, voices, `default-x`, accidentals, `<print>` | no grades, no page coordinates |
| `.omr` in the temp folder (`audiveris_read`) | every kept symbol with bounds and grade, staff lines, stacks, `BINARY.png` | discarded today, no fork change needed to read it |

**Where it runs**
1. Checks and retiming: Python after `clean()`, on MusicXML. No reader change.
2. Look-again prototype: Python on the `.omr`, offline.
3. Whatever passes its stop rule moves into Java at RHYTHMS, so voices can be re-mapped without a second JVM. `sma-solver1` has replay hooks. I have not checked how much is reusable.
4. Font-relative tests replace fixed constants where they are read (`refineSignature`, the alter size rule).

**Why this would not become a pile of special cases**
- Knowledge sits in a short list of stated conventions, none naming a piece, font or engraver.
- Every check gets a free false-alarm test: **run it on the reference files.** A convention check must stay quiet on correct music.
- There is one probe and one decision rule. A check that needs an exception is removed, not patched, which matches the owner's "second patch round means stop".

**What does not belong in it.** Be plain about this, because the approved "logic layer" bundles them: the crash and book isolation, part joining by layout (though the check can raise the doubt), `sf` and text meaning, and masking text ink. Those are ordinary fixes. Voices and triplets depend on the BarTable but are an assembly problem, and they stayed hard even with exact symbols.

## 4. What it takes

Working days are my estimates, excluding benchmark waiting. Each reader change also needs a fresh unseen set (about 1 day), because `bench-tune2` and `bench-oldly` have now been examined bar by bar, here and before.

| Piece | Days | Unknowns |
|---|---|---|
| Crash fixes, one failed system or sheet skips that page instead of the book | 0.5-1 | other crash sites |
| Scorer v2 (section 6) | 1.5-2 | reference quirks |
| Lost last flat | 1 | earlier `bth/` probe changed no key on 201 files with a lower trail value; not re-verified |
| Part joining by layout, not name | 2-3 | real-world names; instrument changes |
| Column-time flag, redundant-accidental alarm | 0.5-1 | wording for users |
| Real-scan set from OLiMPiC | 1-2 | system-level pairing |
| Retiming from a complete voice, in the reader | 3-5 | MusicXML rewrite against Java; flagged bars stay shaded |
| `areAdjacent` and slot merging | 1-2 | size of the class |
| `sf` conversion and text meaning | 1-2 | |
| Masking text ink (false marks, digits) | 2-3 | PDFs with no text layer |
| Look again: font profile, probe, rests | 4-6 | insertion and re-mapping; position accuracy |
| Then dots, flags, beams | 1-2 each | beams are drawn shapes |
| Split and merged bars | 1-2 | depends on rhythm |
| Ties by arc check | 3-4 | |
| Grace notes (log 98) | 1-2 | |
| Voices by stems; triplets by columns | 1 to test, then 3-5 each | may not pass |
| Second reader as witness | 3-6 | speed on 4 vCPU; image size |

**Cost and Cloud Run**
- *Latency is the limit, not money.* A 5-page PDF took 132 s on production against a cut-off of about 125 s (log 101; the cut-off is likely Cloudflare, not confirmed).
- *Python checks:* negligible.
- *Look again on flagged bars only:* my unoptimised probe took about 25 s per PDF for every bar under load, so 3-4 s for the roughly 14% flagged (estimate). No meaningful memory. It must skip when the deadline is near.
- *Money (from memory, not re-checked):* Cloud Run lists about $0.000024 per vCPU-second and $0.0000025 per GiB-second, about $0.0001 per second for 4 vCPU and 4 GiB. So +5 s is about $0.0005 per read, nothing at 3 production reads a month.
- *Second reader:* homr took 11-18 s per page on 16 cores (`spike/omr/RESULTS.md`), so likely more on 4 vCPU (guess). About 1.2 GB RAM and 700 MB on disk. AGPL-3.0, same as Audiveris. Not in the request path; at most for doubted pages or after replying.
- *Claude on crops (from the test in section 5):* about $0.30 per bar and 92 s at normal effort, $0.09 and 22 s at low effort. These are estimates from token counts at Sonnet's $3 and $15 per million (Alicante poster), with cache rates from memory, and the helpers kept every earlier bar in context. A separate call per bar should cost less: low effort used about 2,700 output tokens per bar, so about $0.05 (estimate, NOT RUN). A PDF with 10 to 30 flagged bars would then cost $0.50 to $1.50, which is 40 to 125 times the read's own compute at the rate above, and $5 a month would cover only 3 to 10 such reads. In the Claude plugin the user's own Claude could look at crops with no server cost (not tested).
- *Bigger models:* LEGATO has an 836M-parameter frozen encoder, far past 4 GiB on CPU (my judgement), its GitHub licence reads NOASSERTION, and 10.2% of its outputs could not be converted. Zeus (repo MIT) is the only one worth a look as a witness, for piano only, speed NOT RUN.

**Recommended order, and how it changes the approved one**

Approved: lost last flat; logic layer with split bars and sf; bar 16 and ties; rests.

1. **New: crashes and book isolation.** The largest single gain for the least work.
2. **New: scorer v2.** Otherwise nothing below can be judged.
3. Lost last flat, as approved.
4. **New: part joining.** 18% of PDFs, invisible to today's score.
5. **New: column-time flag.** More honest warnings before any repair.
6. **New: a real-scan set.** Production read 2 scans in 3 PDFs last month (log 97), against 3 scans in this benchmark.
7. Bar 16, with slot merging and retiming, replacing the "logic layer" as a project.
8. Rests, ahead of ties (changed): timing is the largest loss and ties do not affect the score or, I expect, harmony. Run the insertion test first.
9. Split bars and `sf` as separate small fixes.
10. Ties, then voices and triplets if their tests pass.

## 5. Experiments

**Already run here**

| Test | Rule set first? | Result | Decision |
|---|---|---|---|
| One edit ranked by clues | yes | 11% coverage | **STOP** |
| Look again for rests | yes | 40% recall at 0.17 false per true; 23% without one PDF | between on paper; treat as unproven outside old fonts |
| Unexplained ink | yes | AUC passes, 7 of 223 at 3% false | not usable as a flag |
| Claude on crops (24 bars) | yes | 9 of 24 bars exact (38%; the reader's draft had 0), 3 bars worse than the draft (12%) | **between the lines: owner decides** (detail below) |
| Column flag, retiming, stem rule, harmony checks, second reader, tie rule | no | above | leads only |

**Crop test detail.** The rule was written before scoring and did not change.
- GO: 70% of bars exact, or 80% exact among at least 8 bars at 0.8+ confidence.
- STOP: under 30% exact, or 20% or more of bars worse than the draft.
- Exact means the whole bar's pitches and onsets match the reference.

| Group | Bars | Exact | Better / worse / same as draft | Notes right, draft to Claude | Invented notes, draft to Claude | Estimated cost |
|---|---|---|---|---|---|---|
| Normal effort | 5 | 3 | 5 / 0 / 0 | 38 to 72 of 78 | 43 to 6 | $1.51 |
| Low effort | 19 | 6 | 12 / 3 / 4 | 178 to 295 of 415 | 235 to 117 | $1.77 |
| Total | 24 | 9 | 17 / 3 / 4 | 216 to 367 of 493 | 278 to 123 | $3.28 |

- **Strong on notes, not safe alone.** Notes right rise from 44% to 74%, but 15 of 24 bars stay wrong, so a bar it edits must keep its shade.
- **Its confidence cannot act as a gate.** Only 2 bars reached 0.8, and 1 of those was exact, so the 8-bar GO route does not apply.
- **Better than the rule-based repairs here.** Retiming and one-edit each made about 10% of wrong flagged bars exact, against 38%. The samples differ, so this is only a pointer.
- **Limits of the test.** It is small. The bars come from 15 PDFs chosen as worst for lost rests. Claude had the reader's draft, so the published no-draft results are not directly comparable. The two groups differ in bars as well as effort, so the gap between 60% and 32% does not show that effort is the cause.
- **Blindness and process.** The tool-call logs show both helpers opened only crops and their own answer files. Against the brief, the low-effort helper edited 2 answer files (`11.json`, `12.json`); I checked that each edit only added a missing closing brace. By its own report it also spent well over a minute on several bars.
- **My recommendation to the owner.** Keep it off the server path because of cost and time (section 4). If wanted, offer it as a suggestion in the Claude plugin, with the shade kept and the user checking the result.

**Next, cheapest first (rules to freeze before running)**

| # | Test | Days | GO | STOP | Decides |
|---|---|---|---|---|---|
| 1 | Run every check on the reference files | 0.25 | fires on 0.5% of bars or fewer | over 2% | which checks may exist |
| 2 | Column flag on a fresh set | 0.25 | 1% false or fewer, 20%+ of silent timing errors | over 3% false, or under 10% | ship the flag |
| 3 | Published baseline: music21 `omr.correctors` on cached readings (licence and current availability unchecked) | 0.5 | 15%+ of wrong flagged bars fixed, 10% or fewer worse | under 8% | does repetition earn a place |
| 4 | Stem rule in entry 95's assembler (`vector_ceiling`) | 0.5 | two-voice bars from 44% to 70%+ | under 55% | build voice work |
| 5 | Triplets from beat columns, same assembler | 0.5 | triplet bars from 27.5% to 60%+ | under 40% | build triplet work |
| 6 | Retiming through the benchmark scorer | 1 | +0.5 point pitch+onset, no set down | under +0.2 | build retiming |
| 7 | Tighten slot merging | 1 | same-time-far-apart bars halve, no pitch loss on any set | no change or any set worse | fix at the root instead of retiming |
| 8 | Rest insertion on 20 PDFs **not** chosen as worst | 2 | 30%+ found by position, 1 false per 5 or fewer, flagged bars down 10%+ | recall under 20% | build look again |
| 9 | Real scans from OLiMPiC | 1-2 | decides priority, no pass line | | if whole-bar right is under 40%, scan work outranks the rest |
| 10 | Second reader on 30 fresh PDFs | 1 | 40%+ of silent wrong pitches at 5% false or fewer | under 25%, or over 10% false | build a witness |

## 6. How to score it

**Baseline from my scorer (181 PDFs, 8,130 reference bars, a first cut, not reviewed against the benchmark's):**

| Bars fully right on | Share |
|---|---|
| Pitch | 84.0% |
| Pitch and onset | 73.8% |
| + note lengths | 72.4% |
| Printed rests alone | 73.4% |
| Ties alone | 88.3% |
| **All of those together** | **55.0%** |

By source, all together: MuseScore 63.9, LilyPond 58.0, old LilyPond 56.5, Verovio 34.7 (hit hard by split parts), PDFs labelled scan 63.1 (at least some are our own degraded renderings, from `bench/scanify.py`; not checked one by one), Peters scan 38.4, Schirmer scan 46.2.

| Item | Found | Of those read, right |
|---|---|---|
| Rests (inflated false count from split parts) | 74.0% | 61.3% |
| Ties | 73.0% | 76.7% |
| Marks | 76.7% | 74.6% |
| Dynamics | 78.9% | 77.1% |
| Repeats | 89.5% | 95.8% |
| Grace notes | 38.6% | not scored |

Tremolo: 0 of 409. Arpeggio: 273 of 1,080.

**Headline: bars exactly right, across all bars of all PDFs.** A failed PDF counts all its bars as wrong. Exactly right means: pitch, onset, printed value, printed rests and ties, per part and staff.

Report beside it, never instead:
1. **Wrong bars with no warning** (now 56%). This is the honest safety number, and a repair must not raise it.
2. **Bars that lost their shade and are still wrong.** The gate from the design doc stays: 10% or less, and I would tighten it to 5%.
3. **PDFs that fail, and PDFs with the wrong part or staff count.**
4. **Note-level pitch and pitch+onset**, so history stays comparable.
5. **Marks, dynamics, text, repeats** as found and right, outside the headline, since the owner cares but harmony does not depend on them.

Rules:
- Keep scans and old fonts as separate rows, never pooled.
- Old LilyPond references are other editions, so mark those differences or exclude them from pitch.
- Run checks on references as a negative control.
- To compare with published work, add TEDn (the Zeus paper computes it on MusicXML; I did not check that its MIT repo includes the tool) and borrow OMR-NED's per-category breakdown. TEDn on real scans: Zeus 18.4%.
- **Not measured by anyone yet: what each error class does to the analysis.** Comparing draft chord labels on reference against reading would rank these problems by what users actually receive. I suspect it would move key, clef, octave and accidentals up and within-bar timing down. NOT RUN.

## Research notes

**Reading and proofreading**
- Skilled readers overlook plausible misprints; a weak reader found the Brahms one (Wolf 1976, retold; I read only a secondary account, and Sloboda's 1976 study only as cited elsewhere).
- Henle uses at least six proofreadings by different people, compares parallel passages, flags doubtful spots for the editor, and has musicians play through.
- My inference: musicians combine firm notation rules, expectation and a second look. Software should copy the first and third and treat the second only as a source of doubt.

**Engraving rules**
- LilyPond: doubling a duration adds a fixed increment, and the most common shortest note sets the basis. Its essay warns against mathematical precision and adjusts for stem direction.
- Wikipedia on stems and ties: the middle-line rule, opposite stems for two voices, one tie per note of a chord, partial ties allowed.
- I found beaming and half-bar rules only in search snippets (Dorico glossary, Wikipedia). **I did not read Gould, Ross or Stone**; no text was available.

**Music recognition**
- Church & Cuthbert 2014: as above, on 29,728 measures with a 24.2% flag rate. Released in music21.
- Rossant & Bloch 2007: fuzzy fusion of symbols and musical rules with error flags, monophonic typeset only. 98.55% was reported for their 2005 version; I did not confirm the 2007 figures.
- Bugge et al. 2011: voting across 4 commercial readers beat only 2 of the 4 significantly.
- Zeus: TEDn 18.4% on real scans with augmentation. OLiMPiC: 1,493 test and 1,438 dev real-scan piano systems with MusicXML references, CC BY-SA.
- LEGATO 2025: TEDn 29.7 against SMT++ 97.7 on 32 IMSLP piano pages. No music constraints; it confuses 16th and 8th rests.
- de Lambertye & Pacha 2024: GNN and grammar rules for notation graphs (results not read).
- homr: AGPL-3.0; pitch and rhythm only.

**Vision models**
- Calvo-Zaragoza et al. 2024: "the models are not equipped to read music" (qualitative, 5 models, 3 crops).
- MusiXQA 2025: GPT-4o 4% on its reading task; it "merely mimics the answer format".
- Alicante poster 2026 (includes Claude Sonnet 4.6): "not yet ready", degrading with precise spatial reasoning. It gives no per-model figures I could read.
- Our own test (section 5) did better than these suggest, but it gave the model the reader's draft and asked only for one bar at a time.

## Appendix: what was and was not done

- **Ran:** cached-reading analyses on 181 PDFs; 2 failing PDFs read through `read_pdf`; 15 new setting-0 readings on this PC (at most 4 at once); homr on 12 PDFs.
- **Crop test, three helpers:**
  - *First helper, 0 answers in 51 minutes:* my brief allowed one write at the end. It used about 408,000 output tokens, its context compacted at minute 38, and it reached the last crop at minute 50.7, just before my stop message arrived. No tool or API failed. `TaskStop` was refused, but it ended when asked by message. Estimated cost about $9.50.
  - *Fresh helper, 5-crop trial:* 5 valid answers in `crops/answers/`, 7.7 minutes, no other files opened, about 12,500 output tokens per bar, estimated $1.51.
  - *Low-effort helper, other 19 bars (owner approved):* 19 valid answers, 7.1 minutes, no other files opened, about 2,700 output tokens per bar, estimated $1.77.
  - *Total spend, all estimates with no meter:* crop helpers about $12.80, me roughly $7-9, so about $20-22. That is well over the $10 limit, and the first helper caused most of the overrun.
- **Not reviewed:** the planned final second-model check of this report was skipped to stay within the spend limit. One earlier review shaped the labels and caveats, before the report was written.
- **Not used:** pc1 and pc2. All readings ran on this PC. The owner's latest instruction is to start nothing new on either PC for the rest of 2026-11-04, and further readings run on this PC only.
- **Respected:** `bench-pitch` and the unseen half of `bench-octave` were not touched.
- **Exposed:** `bench-tune2` and `bench-oldly` were used bar by bar here, so they are no longer clean for testing.
- **NOT RUN:** any fix through the reader or benchmark, all of section 5's next tests, and the harmonic-impact measure.
- **Scripts:** `/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/mlr/` (`t1` flags, `t2` score, `t4` one edit, `t5` retiming and column flag, `t6` note budget, `t7` and `t10` key and stems, `t8` rest probe, `t9` harmony checks, `t11` marks, `t12` ink, `t13` ties, `h_cmp` second reader, `v_crops` and `v_final` crop test, `NOTES.md` stop rules).

## Sources

- Church & Cuthbert 2014: https://archives.ismir.net/ismir2014/paper/000357.pdf
- Rossant & Bloch 2007: https://asp-eurasipjournals.springeropen.com/articles/10.1155/2007/81541 and 2005: https://hal.archives-ouvertes.fr/hal-02882947
- Bugge et al. 2011: https://archives.ismir.net/ismir2011/paper/000093.pdf
- Mayer et al. 2024 (Zeus, OLiMPiC): https://arxiv.org/abs/2403.13763 and code https://github.com/ufal/olimpic-icdar24
- LEGATO: https://arxiv.org/html/2506.19065v1 and code https://github.com/guang-yng/legato
- homr: https://github.com/liebharc/homr
- Sheet Music Benchmark, OMR-NED: https://arxiv.org/abs/2506.10488v1
- Reading Music Systems 2024 (Calvo-Zaragoza et al.; de Lambertye & Pacha): https://repositum.tuwien.at/bitstream/20.500.12708/208033/1/Pacha-2024-Proceedings%20of%20the%206th%20International%20Workshop%20on%20Reading%20Music...-vor.pdf
- MusiXQA: https://arxiv.org/html/2506.23009v3
- Alicante poster: https://web.ua.es/de/phdinf/documentos/jdi-2026/noelialunabarahona.pdf
- Brahms story: https://futilitycloset.com/2014/12/13/a-natural-mistake
- Henle proofreading: https://blog.henle.de/en/2018/03/12/no-error-in-the-system-in-praise-of-our-proofreaders
- LilyPond spacing: https://lilypond.org/doc/v2.24/Documentation/notation/horizontal-spacing-overview and essay https://lilypond.org/doc/v2.24/Documentation/essay/engraving-details
- Stems: https://en.wikipedia.org/wiki/Stem_(music). Ties: https://en.wikipedia.org/wiki/Tie_(music). Beams: https://en.wikipedia.org/wiki/Beam_(music). Half bar: https://www.steinberg.help/dorico/v1/en/dorico/topics/glossary/half_bar_g.html
- Behind Bars (entry only, not the book): https://en.wikipedia.org/wiki/Behind_Bars_(book)
