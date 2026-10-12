Cached production evaluation (no recognition reruns):

```bash
.venv/bin/python spike/omr/bench/triplet-evaluation/evaluate.py spike/omr/bench spike/omr/bench/results-prod2.json spike/omr/bench/triplet-evaluation/main.json
.venv/bin/python spike/omr/bench/triplet-evaluation/evaluate.py spike/omr/bench-heldout spike/omr/bench-heldout/results-prod2.json spike/omr/bench/triplet-evaluation/heldout.json
.venv/bin/python spike/omr/bench/triplet-evaluation/evaluate.py spike/omr/bench-heldout2 spike/omr/bench-heldout2/results-prod2.json spike/omr/bench/triplet-evaluation/heldout2.json
```

Each before/after metric comes from the official `bench/score_one.py`, in a
separate process. Gains and losses are changes to truth-overlap multisets after
Verovio/ScoreIndex import, on the original pitch-aligned bar pairs. They include
notes downstream of an edit; edited symbols that remain wrong count in neither
column. Pitch+onset totals also recompute the official alignment. Every saved
production baseline is asserted against its original result row. Raw XML
prototype counts can differ from these engine counters.

The six fresh CC0 OpenScore songs in `bench-heldout2/build.py` were fixed from
truth triplet counts and composer diversity before reading them. Engraving uses
the original builder's MuseScore 4 exporter. `bench-heldout2/read.py` calls
production `read_pdf` on one PDF at a time with the specified sma.1 Audiveris.
It wraps only the final post-fix to capture its input, returning the normal fixed
production result. Cache `.musicxml` files contain pre-fix input;
`.after.musicxml` files contain returned production output. Rules were frozen
before these recognition runs and were not tuned on heldout2.
