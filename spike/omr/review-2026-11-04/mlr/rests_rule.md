# Stop rule: lost rests fix (written 2026-11-04, before any fix was measured)

Diagnosed on: tests/data/beethoven-op18-4-iii (old LilyPond). The only PDFs used to design or tune the fix are that one and bench-oldly/ly-quartetopus18-no4-3.

Set: mlr/rd/rests_set.json, made by mlr/rd/pick.py before any fix reading. PDFs in bench, bench-heldout, heldout2, heldout3, bench-real; not in mlr/probe_set.json (worst for rests); at most 10 pages; at least 20 printed rests in the truth (truth only, no reading used); first 20 by sha256 of the stem. Not used: bench-tune2, bench-oldly (exposed), bench-pitch, bench-octave.

Runs: variants.py production path, base = aud-pitch51 install, fix = same install with only the fix jar. Same settings. Each design gets one run on the set. At most two designs.

Measures, pooled over the 20, per bar aligned to the truth, key (part, onset, type), printed rests only:
- lost = truth minus base.
- found = lost in base and present in fix.
- false = in fix, not in truth, not in base.
- flagged = bar_duration_errors in the bench score, summed.

PASS, all of: found >= 30% of lost; false <= found / 5; flagged down >= 10%; pitch and pitch+timing totals not down; no new crash.
Also report: exact-bar score (whole_bars.py), and found without the single largest PDF. If one PDF supplies over half of found and the rest fall under 20% recall, call that NOT general.
STOP (no further design): recall under 20%.
Anything else: FAIL, revert, say so.

## Result (2026-11-04)
Design 1 (restore rest tips erased with a staff line, SymbolsBuilder): lost 119, found 1 (0.8%), false 7, flagged 123 to 131. STOP. Not applied to the fork. Patch script: mlr/rd/apply_fix.py.
