# Printed bar names

Owner's decision, 2026-11-21: bars are named as in the user's printed copy. A bar the print does not number gets the name of the bar before it plus a letter ("16a"). This ships with the next release, not before it: it changes `render_analysis`'s input schema, so ChatGPT needs OpenAI's approval of the update, and Claude needs a plugin release (Claude releases are paused).

## Names

`Measure.number` stays the engine's own count: the index key that every module uses. `Measure.name` (text) is what the chat and the page see.

- When the file's bar numbers are whole numbers that only go up, the name is the file's number, so nothing changes for most scores.
- A bar whose number is not a whole number ("X1", "3a"), or repeats the number before it, is named after the last numbered bar plus a, b, c… This covers a second-time ending left uncounted, a bar split by a repeat sign, and a reader that gives two bars one number.
- When the file's numbers go back (a second movement starting again at 1), names would repeat. In that case the whole score is named by the count, as today.
- Both halves of a joined bar share their owner's name.

## Where the names cross the boundary

Inputs (a name or a bare number is accepted; a number means the bar printed with that number):
- `render_analysis` annotations: `measure` becomes `int | str`. This is the schema change.
- `measure_range` in `render_analysis`, `draft_analysis` and `play`: already text; `parse_measures` resolves names.
- `correct_bars` `replacement_bars`: "m16a".
- `student_analysis` (RomanText "m16a").

Outputs:
- The note list (`m16a`), the draft table, the reduce header, part-writing findings, the student-check messages, correction messages, PositionError, captions, and ranges given back.
- The drawn page: MEI `n` = name. Verovio draws `n`.
- The PDF preview: `read_pdf.number_bars`.

## Checks

- Across the corpus: every bar has a unique name; names equal the file's numbers wherever the file's numbers only go up; the drawn page's numbers equal the names.
- Round trip: a draft names "16a", and render_analysis given "16a" draws in that bar.
- Old clients: an integer `measure` still works and means the printed number.

## Status

- Step 1 (cfe7865) is done: `Measure.label` holds the file's number and `Measure.name` the printed name; `ScoreIndex.bar(name)` looks a bar up by name; `render._name_drawn_bars` writes the names into MEI `n`, so the page draws them (Chopin Mazurka BI 16 No. 2: the second ending is "16a" and the next bar is drawn 17, as printed).
- Steps 2 and 3 (branch `printed-bar-names`, log 189) are done. Every bar number the chat or a page sees is the name (note list, NOTES table, part-writing, ledger, student check, corrections, tempo question, captions, ranges, PDF preview and notice, shaded bars, play range). Inputs take names: `Position.measure` and `RangeEnd.measure` are `int | str`, resolved by `annotate.by_number` at the server before drawing; `parse_measures` returns names and `ScoreIndex.numbers` resolves them; correct_bars and note lists read "m16a"; typed student numerals read "m16a". `ScoreIndex` reads the file's number from MEI `label` when the page renamed the bar, so every MEI the engine reads gives the same internal numbers; a multi-bar rest is split by internal number after the pickup is numbered.
- Not changed, for the owner: the RomanText download still numbers bars by our count (RomanText files are read by programs that count bars); `comparison.from_romantext` (the evaluation's expert analyses, not a server path) keeps RomanText's own rule that "m16a"/"m16b" are two endings; draft.py's table (the parked model draft) prints internal numbers. Piano reductions now choose and number bars by our count, join split bars and draw the source's names (log 189).

## Review of 2026-11-21 (Opus, cold): fix before merging

1. **A pickup the file numbers "1" is named "1" when the score also has an uncounted or repeated bar** (engine/render.py `_number_unmarked_pickup` sees the renumbered index, so the shift to 0 is skipped). Every bar then reads one above print. Real file: out/eval/ceiling/Variations_and_Grounds__Beethoven,_Ludwig_van_____WoO_68.xml. Decide from the file's labels; add a corpus check that internal 0 is always named "0".
2. **A measure_range past the end, or into a gap in the file's numbers, now fails** ("Measure 140 does not exist"). It worked on engine-identity. Clamp whole numbers to the nearest bar as before; only an unknown lettered name is an error.
3. **ChatGPT between the deploy and OpenAI's approval** keeps the held schema `measure: integer`, so a "16a" bar cannot be annotated. Owner's call: deploy when approval is close, or hold the "16a" guide text back for ChatGPT until approval.
4. Bars before the first whole-numbered label are named by count and can clash with a later label (no real file has this). Name them "0" plus a letter, or count from 0.
5. Minor: `current_bars` adds 3 to an internal number (count by position instead); `leave_out_rejected`'s two retry rounds are now shared with name resolution; a piano render reads the score three times (pass the ScoreIndex down, saves about 0.9 s on a quartet movement).

Full suite at daf6f15: 1600 passed, 1 failed (the proxy-key server test, a flake under load that passes alone), 11 skipped.
