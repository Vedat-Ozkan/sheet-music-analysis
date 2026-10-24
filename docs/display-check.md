# Display rules check

`tools/display_check.py` draws every page in a fixed corpus through the real entry points and fails on any break of
the display rules below. Nobody has to find these defects by eye. Run it before handing over any change that can
move a mark on the page.

## Running it

```
.venv/bin/python -m tools.display_check                  # this checkout; about 20 s on 16 cores
.venv/bin/python -m tools.display_check --only bwv404 pdf/joplin
.venv/bin/python -m tools.display_check --root ../other-worktree   # another checkout, read only
.venv/bin/python -m pytest tests/test_display_rules.py   # the same, one test per corpus item (marked slow)
```

The CLI prints one line per violation: rule, item, entry point, page, bar, and what touched what. It also writes a
crop of each violation, framed in blue, to `out/display-check/<commit>/`. It exits 1 if anything is found.
`-m 'not slow'` leaves the pytest version out of a quick run.

The PDF readings come from the benchmark's cached Audiveris output (`spike/omr/bench/cache/raw` in the main
checkout, git-ignored). They go through `engine.read_pdf.read_pdf`, so the reading is cleaned exactly as in
production. Audiveris is never run. A reading missing from the cache is an error in the CLI and a skip in pytest.

## Corpus

- The 20 part-writing chorales (`tests/data/part_writing_*.musicxml`), whole piece, with the draft's own marks and
  one callout per numbered spot. Each is drawn again one bar at a time, for every bar with a mark, as a user asking
  for those bars gets it. The draft text is turned into annotations as the chat model is told to
  (`draft_marks`, which `tests/test_overlay_marks.py` also uses).
- The 9 engraving passages (`examples/engraving`) and the Chopin example, each in all 3 notation styles.
- The two check-page samples (Bach, Chopin).
- 12 PDF readings: the 4 review PDFs (Chopin prelude ms, Joplin ly, K.545 scan, Schubert Die Stadt ly), and the 8
  whose plain layout ends on a page of one or two bars. Each is drawn through the server's `preview()` (tall card
  and ordinary pages) and the skill's `pages()`.

## Rules

Everything is measured from the final SVG. The music comes from Verovio's bounding boxes, beam polygons, and staff and
ledger line paths. Text is measured by its glyph ink, plus its white knockout where it has one. Nothing reuses the
placers' own tests (`_on_staff`, `_touching`, `own()`, `system.content`), so the check can disagree with them.

| Rule | Fails when | Source |
|---|---|---|
| `staff-line` | analysis text (codes, numerals, figures, R, bar numbers, callout numbers) crosses a staff or ledger line | Gould: text goes outside the staff |
| `collision` | analysis text, with its knockout, touches a notehead, accidental, stem, beam, dot, rest, flag, fermata, dynamic, lyric, slur, tie, other score text or sign, or another analysis text or mark. Also when a tendency arrow, callout disc or cadence box touches the music, and when a ring comes within 40 units (about 5 px on a full-size page) of a dot, accidental, fermata, articulation, ornament, flag, rest, dynamic, lyric, tie, slur or another notehead | owner: labels never cramped |
| `ring-own` | a ring comes within 40 units of its own note's accidental or dot | owner question (enclose them or not) |
| `ring-code` | a ring's code is not clearly nearer its own ring than every other ring and every other notehead: each of those must be at least 1.5 times as far as the ring (the placer's own margin). Rings under the same callout with no code of their own count as its own | decision R |
| `dropped` | a mark the draft lists is not drawn where it should be: a ring on its note, its code, a line from its note, a tendency arrow and its R, a bracket, a callout number, or a line's word on its system | review §5 (the vanished R) |
| `excerpt-edge` | in a one-bar drawing, a line, bracket or arrow the draft lists runs to a note outside the bars, or marks are drawn whose callout is outside them (a tendency arrow needs only its own note) | owner question |
| `arrow-staff` | a tendency arrow or its R crosses a staff line | decision S |
| `pages` | a reading's page count or the bars on its last page differ from `tests/golden/display_check_pages.json` | review §F (the last-page pull-in) |
| `bar-number` | a bar number at an ending is not above the ending's bracket | review §3 item 3 |
| `top-margin` | a reading's page starts its ink less than 2.5% of the page width below the top | review §3 item 2 |

There is no allowlist. A rule that disagrees with an owner decision fails, and the conflict goes to the owner.

## Re-pinning page counts

The baseline was pinned from `visual-revision` (29cbdfe). When a change to the page count is intended, run
`--repin` (with `--root` if needed). It prints each changed entry as `old -> new`. Commit the new
`tests/golden/display_check_pages.json` together with that list.

## Known limits

- Two labels drawn one after another in black, starting inside each other's run and within a line of each other,
  are taken as chunks of one numeral, so a collision between them is not reported.
- A halo that only cuts a staff line (the white stub beside a code) is not a rule. The full-size review still
  catches it.
