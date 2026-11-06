# False articulation marks: decision rule, written 2026-11-04 before any code change

Baseline: variant tie2 (fork 7b4503617), cache/runs/tie2, 183 PDFs in bench, bench-heldout, bench-heldout2, bench-heldout3, bench-real, bench-tune2, bench-oldly.

Measure: marks_measure2.py. False mark = a read mark on a note whose onset and pitch match truth at that onset, where truth has no mark of that kind at that onset. All `<notations>` blocks are read (barparse.py reads only the first, which hides real truth marks).
The three PDFs printed from another edition than their truth (mozart-k545-1 lilypond-mutopia, real-scan-peters, chopin real-scan-schirmer) are reported apart and left out of the percentages.

GO, all of:
- measured false marks down 30% or more overall
- true marks found down no more than 1%
- exact bars (whole_bars.py) not down overall
- no set's exact bars down by more than 0.1
- pitch and timing not down
- no PDF newly failing
- read time up no more than 5%

STOP: false marks down under 15%.
BETWEEN: anything else. Report it; the owner decides.

One fix only, general, no font or PDF special case. If the first fix is not enough, report; do not patch the same code twice.
CPU budget: at most two full 183-PDF runs on this PC, --only subsets first.

## The one fix, chosen before building (from the 33-PDF diagnostic)
Cause: ArticulationInter.lookupLink accepts a mark up to 5.0 interlines from the chord under the STANDARD profile (ChordArticulationRelation.yGapMax_p1), so stray dots and dashes anywhere near a chord become marks.
Fix: hard reject in lookupLink when a STACCATO or TENUTO center is more than 2.0 interlines from the chord. No change to relation grades or to other shapes. Applies to every profile.
Prediction from the sample (598 false, 1,307 true, same-source PDFs): false -38%, true -0.3%.
A dy cap cannot reach real printed marks or fermata dots (about 25% of labelled false marks).
Subset first, then one full run. Subset check includes dotted notes and exact bars against tie2.
