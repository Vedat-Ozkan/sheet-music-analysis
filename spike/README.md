# Experiments

Work that shaped the product but is not part of it. Nothing here runs on the server.

- `omr/`: PDF reading. `omr/bench*` are the reading benchmarks: scripts only; the PDFs, scores and readings are kept out of git. `omr/speed/` holds the reading harness: the bar-by-bar scorer, reader variants, scripts for running readings on spare machines, and the patches to our fork of the reader. `omr/truth/` holds reference scores some tests read; it is kept out of git, and test runs in a worktree borrow it from the main checkout.
- `export/`: writing Roman numerals into MusicXML.

The investigation scripts and notes of the 2026-11-04 reading review were removed from the tree on 2026-11-21. They are in git history up to commit 2953d5b (`git show 2953d5b:spike/omr/review-2026-11-04/...`).

What each experiment found is in `docs/engineering-log.md`.
