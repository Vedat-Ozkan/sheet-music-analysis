# Voices and triplets: stop rule (written 2026-11-04, before any run of the new rules)

Baseline: `assembly.py --one-voice-first` reproduced before writing this: all 2586/2902, one voice 2474/2650, two voices 112/252, triplets 25/91. No failure bar has been looked at.

Buckets are frozen from the baseline in the same run. "One voice" and "two voices" are the baseline assembler's own decision, so each is pinned by key (pdf, staff, truth bar) and new rules are scored on those exact keys. The triplet bucket comes from truth durations (a length whose denominator divides by 3).

## Test 4, voices
Rule fires on a bar when either holds:
- Against the middle line: an unbeamed stemmed note whose head farthest from the middle line is more than 0.25 space off it, on the same side as its stem. Heads on the middle line, and chords with heads equally far on both sides, never fire. Beamed notes are not judged (the review's 1.8% / 76.5% was measured on unbeamed notes).
- Two stems at one start: two stems pointing opposite ways with head x within 1.3 spaces (compared by head, not stem).

Integration, one attempt: if the rule fires, split by stem direction exactly as entry 95 does. If silent, entry 95's diagnostic runs unchanged. Bars with one stem direction stay one voice.

Prediction written before running: the 252 stay at exactly 112/252 = 44.4%, a STOP by construction. Every one of those bars already had mixed stems and failed to fill as one voice, so firing and staying silent both reach the same stem split. The rule can only change bars one-voice-first had filled. If the 252 move, the code is not what is frozen here.

GO 70%+. STOP under 55%. Between: owner decides. Also reported: frozen 2,650 and overall, firing counts on both buckets, matched-to-unmatched and unmatched-to-matched, a secondary table by true voice count (MusicXML `<voice>` per staff-bar), and the baseline failures grouped by cause (exploratory, names what a different design needs).

## Test 5, triplets
Run against the baseline, not on top of test 4.

Clock: another staff of the same system, same truth bar, whose symbols matched exactly and whose bar, assembled by the baseline assembler, fills exactly in every voice (never its truth timing). Columns are its onsets, notes and rests, at head x; time 0 is the bar's left edge and the bar length its right edge. Several usable staves are unioned.

Group: a clock column pair with times t and t+D, t a multiple of D, and a voice with exactly three events at head x in [column1 - 1 space, column2 - 1 space), all notes, equal value and dots, with 2L == D where L is the printed length. Rests disqualify.

Integration, one attempt: groups are applied as if they were printed marks (2/3 factor before the fill check). The rest of `place()` is unchanged, including the beam-group fallback.

GO 60%+. STOP under 40%. Between: owner decides. Also reported: overall, non-triplet bars receiving a clock group, how many go matched to unmatched, non-triplet bars reading any triplet length, and the 91 split into solo line, clock unusable, clock usable. Bars with no other staff are counted overall too.

## Limits fixed in advance
Exact symbols, engraved PDFs we made. A pass means "worth building", not an accuracy gain for today's reader. One attempt per rule, no tuning on these bars.

# Results (one run of each rule; rules above unchanged)

Code: `spike/omr/speed/vector_ceiling/voices_triplets.py` (new), small edits to `ceiling.py` (`middle`, `space` on events) and `assembly.py` (`known_triplets` on `place`). Uncommitted. Baseline rerun after the edits and printed in the same run: unchanged.

These use exact symbols from PDFs we engraved. A pass means "worth building", not an accuracy gain for today's reader.

| Frozen set | Baseline | Test 4 stem rule | Test 5 clock |
|---|---|---|---|
| Overall (2,902) | 2586 = 89.1% | 2579 = 88.9% | 2588 = 89.2% |
| One voice (2,650) | 2474 = 93.4% | 2467 = 93.1% | 2473 = 93.3% |
| Two voices (252) | 112 = 44.4% | 112 = 44.4% | 115 = 45.6% |
| Triplets (91) | 25 = 27.5% | 25 = 27.5% | 40 = 44.0% |
| Non-triplet (2,811) | 2561 = 91.1% | 2554 = 90.9% | 2548 = 90.6% |

Secondary, by true voice count from MusicXML `<voice>`: one voice 2474/2636 (93.9%) at baseline, 2465 (93.5%) with the rule. Two or more 112/266 (42.1%) at baseline, 114 (42.9%) with the rule.

## Test 4: STOP, 44.4% against STOP under 55%
Exactly as predicted before the run, and by construction: this was never a fair chance for the rule to raise the number. All 252 bars take the same path (252 unchanged).
- Detection separates well. It fires on 27 of 2,636 true one-voice bars (1.0%) and 220 of 266 true multi-voice bars (82.7%). That recall is below the review's 95.6%, which was measured differently (reference files, unbeamed notes). 1.0% is not like-for-like with the review's 1.8%, which was the middle-line rule alone. On the frozen buckets: 197 of 252 and 50 of 2,650.
- Detection was not the failing step. The review's 60-70% guess assumed it was.
- Side effect: on the 2,650, 2 bars gain and 9 lose, net -7.
- Causes of the 140 baseline failures in the 252 (exploratory, each bar counted once): same note counts but starts wrong, a voice entering late or with gaps, 60; triplets in the bar 36; stem directions do not partition the true voices 35; truth is one voice 5; three or more voices 4.
- A different design needs note timing, not detection: placing each voice's notes by the columns they line up with, and voices that are not one stem direction. That is a new test on fresh bars. This result says nothing about it.

## Test 5: between the lines, owner decides: 44.0% (STOP under 40%, GO 60%+)
- Situations in the 91: solo line 0, clock unusable 6 (2/6, unchanged), clock usable 85 (23 to 38). Over all 2,902 tested bars: no other staff 0, clock unusable 247. The main set has no solo line, so solo lines are untested here, and the rule cannot help them.
- A clock group fired on 71 of 91 triplet bars, yet 51 stay wrong: 43 with a group fired (31 of those with mixed stems, so voices still block them), 8 with none.
- False triplets: 27 non-triplet bars receive a clock group, 13 go matched to unmatched, 0 improve. Non-triplet bars reading any triplet length: 2 at baseline, 29 with the rule.
- Exploratory, after the run; does not reduce the 13: all 13 losses have a chord with a displaced head (a second) in the bar or the clock. Traced on Joplin bar 14 (truth index 13): a chord's second sits one head width (6 pt, 1.2 spaces) left of the stem line, `min` head x takes that head, and that exceeds the frozen 1.0 space tolerance, so a beat's note falls before its column and three notes look like a group. Traced on two bars, counted on 13; not rescored.
- Exploratory, after the run: of the other 14 bars that received a group, 10 are in `cpe-bach-h186`, whose truth durations are rounded tuplets (171/1024). They do not divide by 3, so the frozen bucket calls them non-triplet though at least some are real tuplets, and they could not match anyway.
- A different design would need: columns taken from the chord's main stem line, not its leftmost head; three per beat under longer clock notes (a half note over six eighths does not qualify); unequal triplet rhythms; rests inside groups. How much these would add is NOT RUN, as re-scoring on these bars would be tuning.

## NOT RUN
`spike/omr/bench-pitch` and the unseen half of `bench-octave` not used. Real exports, scans and other editions not tested. No re-score of either rule. Home PCs not used.
