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
