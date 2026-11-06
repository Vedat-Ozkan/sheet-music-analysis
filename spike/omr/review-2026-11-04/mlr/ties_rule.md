# Tie fix: stop rule, written before any code change (2026-11-04)

Baseline: pitch51, 183 PDFs, 8273 truth bars (8246 paired). whole_bars.py exact 55.2 overall.
By set: bench 67.0, heldout 62.5, heldout2 47.9, heldout3 53.4, real 63.6, tune2 59.2, oldly 39.0.

Candidate (one change, general): a curve is a tie only if each end sits within 0.9 interline, vertically, of the head it is linked to. Applied where a same-staff tie is decided (SlurInter.checkStaffTie, ClumpPruner.prune). Otherwise it stays a slur. Cross-system ties are left alone: too few samples to set a limit.

Evidence before coding, 11 PDFs read with their books (5 engravers), 436 tie curves linked at both ends:
- Vertical gap, tie matching truth: 289 curves, max 0.8, none at 0.9 or more.
- Vertical gap, tie not in truth: 116 curves, 89 at 0.9 or more (portato slurs over staccato dots, pieces of "Ped." and tuplet brackets).
Corpus ceiling, cached readings, all 183: 151 bars are wrong only by extra ties, so at most +1.8 points if every one were cured.

GO: exact bars overall up at least 0.5 (55.7 or more), no set down by more than 0.1, pitch and timing not down (98.0 / 91.1 overall), bars flagged not up by more than the gain.
STOP: overall gain below +0.2.
Between: report; owner decides.

Subset first: the 11 evidence PDFs plus any others with --only. Then at most two full 183-PDF runs on this PC. One patch only: if inadequate, report, do not patch the same code again.

## Result (2026-11-04), one full run: tie2, commit 7b4503617 on tie-try
Exact 55.20 -> 56.53 (+1.33). Every set up; no PDF's exact count down. 84 of the 110 bars gained are in PDFs not used for the evidence. Pitch 98.02 same, timing 91.09 -> 91.13. Flagged bars 1461 -> 1453.
Set-level dip: bench-heldout timing 94.86 -> 94.79. Pitch-and-timing bars there 80.68 -> 80.23. Removing a false tie can move notes, because the tie fed time and voice linking: Erlkonig bar 12 went from 9 of 9 notes timed right to 5 of 9, bar 30 from 17 to 13 of 17, Kinkel bar 1 from 37 to 32 of 39.
