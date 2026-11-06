# Stop rules written before running (2026-11-03)

t4, one-edit repair ranked by clues, on cached sma.6 readings, flagged-in-reading-only bars:
- Coverage = share of flagged-only wrong bars where some one-edit-per-bad-voice candidate gives right note onsets.
- Top-1 precision = on bars where a candidate is applied, share whose onsets then match truth. Two-fold by piece.
- GO for this plan: coverage >= 50% AND top-1 precision >= 80% at a confidence level that still repairs >= 25% of flagged-only wrong bars.
- STOP: coverage < 35% OR best precision < 60% on the held-out fold.
- Between: owner decides.

t8, "look again" probe for lost rests (self-templates from the same book, staff lines kept, same line phase), setting-0 books of 15 PDFs:
- GO for the look-again design on rests: at one threshold, recall >= 60% of lost rests that have a template AND false hits <= 1 per 3 true hits.
- STOP: recall < 30% at false hits <= true hits.
- Between: owner decides.

t12, unexplained ink (every mark must be explained): on 15 setting-0 books, per bar. Useful as a silent-error flag if AUC wrong-vs-right >= 0.70, or if a threshold catches >= 25% of silent wrong bars at <= 3% false flags on right bars. Otherwise drop.

Vision crops (written 2026-11-04 before scoring answers.json, answers not yet seen): 24 flagged, wrong bars from the 15 worst-for-rests PDFs, drawn by hash, max 3 per PDF. One Sonnet subagent, blind to truth, given the reader's draft. Exact = (midi, onset) multiset of the whole bar equals truth.
- GO: at least 70% of bars exact, or at least 80% exact among bars it marks confidence >= 0.8 (with at least 8 such bars).
- STOP: under 30% exact, or at least 20% of bars worse than the draft in notes right.
- Between: owner decides.

Vision crops, rerun (2026-11-04, owner allowed). The first helper wrote no answers, so its rule was never scored. Rule above unchanged. Same 24 crops and drafts. New: a fresh Sonnet helper writes crops/answers/NN.json after each bar. Trial on crops 00-04 first; if no new file appears for 10 minutes, stop and mark NOT RUN. Blindness is checked afterwards from its transcript's tool calls.

Vision crops, remaining 19 (owner approved, 2026-11-04): a new Sonnet helper at low effort, same brief, crops 05-23, written before any scoring. Rule above unchanged, applied to all 24. The 5-bar and 19-bar groups are also reported separately. Stop if cost is clearly over about US$3.
