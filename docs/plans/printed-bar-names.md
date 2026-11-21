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
- Not changed, for the owner: the RomanText download still numbers bars by our count (RomanText files are read by programs that count bars); `comparison.from_romantext` (the evaluation's expert analyses, not a server path) keeps RomanText's own rule that "m16a"/"m16b" are two endings; draft.py's table (the parked model draft) prints internal numbers; a piano reduction page probably draws our count, not the printed names (piano.py numbers its bars by our count; read from the code, not checked on a page).
