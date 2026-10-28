# Annotation list, version 1

The annotation list is the contract between the chat model and the renderer. The model says *what* to mark and *where in the music*; the renderer decides where that is on the page. Nothing in the list is a pixel coordinate.

The schema is defined in `engine/annotations.py`; a complete example is `examples/chopin_op9_no2_m1-8.json`.

```json
{
  "version": 1,
  "style": "current",
  "annotations": [
    {"type": "harmony", "at": {"measure": 3, "beat": 2}, "label": "V65/vi", "callout": 3},
    {"type": "cadence", "at": {"measure": 4, "beat": 3}, "label": "PAC"}
  ]
}
```

The optional top-level `style` selects notation for the whole list:

| Value | Drawn as |
|---|---|
| `current` (default) | Existing raised or stacked inversion figures; omitting `style` preserves the existing output. |
| `abrsm` | Inversion letters: `I6` → `Ib`, `V64` → `Vc`, `V65` → `V7b`. Root-position `a` is omitted; seventh-chord quality, secondary targets and text suffixes remain. `Cad64` is `Ic`, and the V that follows keeps its own numeral (`Ic V7`), as ABRSM teaching writes it. |
| `figured_bass` | Roman roots with a separate figure stack alongside them under the bottom bass staff (Piston style). Figures include accidentals relative to the active key; root-position 5/3 is omitted unless altered. |

For `figured_bass`, set `key` on the first harmony and at every key change. Keys carry forward in musical order, including from before a selected passage. A missing or invalid active key is an annotation error; the renderer does not infer major or minor from the signature. Bass accidentals belong on the score's notes, not in the figure stack. Chord symbols and unsupported Roman extensions retain their existing display. Text suffixes such as `4–3` remain free text beside the figures.

Double accidentals in figures use paired signs (`♭♭`, `♯♯`) supported by the bundled fonts.

The skill script accepts `--style current|abrsm|figured_bass` to override this field. Without the argument it uses the list's style. The ABRSM spellings follow the conversions in `engine/notation.py`; exam-board approval of these conventions is still pending.

In ABRSM style, the seventh is always raised, including before an inversion letter or secondary target (`V⁷b/vi`); inversion letters and slashes stay on the baseline.

## Positions

| Field | Meaning |
|---|---|
| `measure` | The printed measure number. A pickup measure is 0. |
| `beat` | 1-based, in the meter's beat unit: a quarter in 4/4, a dotted quarter in 6/8 or 12/8. Fractions are allowed (`2.67`). Defaults to 1. In a pickup measure, beat 1 is its first note. |
| `staff` | 1 is the top staff. Only needed to tell simultaneous notes apart. |
| `pitch` | `"Eb4"`, `"F#5"`, `"D2"` (middle C is C4), at sounding pitch: a note under an 8va line is named an octave above where it is written. music21 spelling (`"E-4"`) is accepted. |

A range has `start` (a position) and `end`. An `end` without `beat` runs to the end of that measure; with `beat` it stops just before that beat.

## Annotation types

| `type` | Fields | Drawn as |
|---|---|---|
| `harmony` | `at`, `label`, optional `function` (`T`, `PD`, `D`), optional `key` | Roman numeral on one row under the system. `key` (`"Eb"`, `"f"`) is set where the key starts or changes. Consecutive chords with the same `function` share one labelled black bracket (MT21C style) under the numeral row: it spans the run's music, from the first numeral to just before the next one (or the line's end), with the full word ("tonic", "pre-dom.", "dominant") centred beneath, and "(pre-dom.)" on a continuation onto the next line. A line whose pieces cannot all hold their words uses T, PD, D throughout; words and abbreviations are never mixed. No `function`, no bracket. |
| `cadence` | `at`, `label` (`PAC`, `IAC`, `HC`, `DC`) | Boxed label under the numerals. |
| `phrase` | `start`, `end`, `label` | Bracket above the system, continued across system breaks. |
| `region` | `start`, `end`, `label` | Dashed bracket above the system, for a stretch named by what it is built on: `whole-tone`, `E Dorian`, `pentatonic`, `parallel 9th chords`, `pedal on G`. |
| `alternative` | `start`, `end`, `label` | Another reading a teacher would accept for the same bars, in numerals: one chord for each of your harmony labels in the bars, in order, `-` where it stays the same, with an optional key first (`F#: V7 I`, `- V43/vi vi6`). Dotted bracket under the numeral row, with each chord printed under the one it replaces; shown in the harmony view. It never replaces the `harmony` labels and is ignored by the exports and by scoring. Mark it with a `callout` disc and explain it in that numbered paragraph of the commentary. |
| `nct` | `note`, `label` (`P`, `N`, `S`, `APP`, ...) | Circle around the note with the letter beside it. |
| `voice_leading` | `kind`, `from_note`, `to_note` (not for a ring), optional `label` | Red means a fault. Every `line`, `ring` and `bracket` is a fault; an `arrow` is red only when its label is Kelley's improper-resolution code `R` (`engine.annotations.FAULT_ARROW_LABELS`, what `part_writing` emits for an unresolved seventh or leading tone). Any other arrow (a resolution or suspension the model draws, label "4–3", "7→3" or none) is a magenta analysis mark. `arrow` (default): a tendency tone to the note that follows, label right of the source note. A red `R` arrow is Kelley's improper-resolution mark instead: a small vertical arrow beside the note (on the side away from the stem, off the staff where there is room) pointing the way it should have resolved, `direction` `up` for a leading tone and `down` (the default) for a chordal seventh, with the `R` at its tail. `line`: one voice of a parallel or direct interval, no arrowhead; the two lines of a pair share one code, set beside the lower line (label either line; identical marks on the same notes are drawn once). `ring`: circle one note; the codes of rings on one chord are set together beside them, and an overlap rings both notes with one code. `bracket`: square bracket spanning two notes of one chord. Fault labels are Robert Kelley's part-writing codes (robertkelleyphd.com/home/partwritingnotations.htm): `P5`, `P8` (parallels), `H5`, `H8` (direct), `VC` (crossing), `VO` (overlap), `S` (spacing), `r` (range), `D` (doubled leading tone), `R` (unresolved seventh or leading tone); the plain-words sentence naming the voices stays in the callout's note. |
| `callout` | `at`, `number` | Numbered disc above the staff, matching a numbered paragraph of the written commentary. |

A `harmony` label that is not a Roman numeral is drawn as written, so chord symbols work too: `Gmaj7`, `Em9`, `C7(#11)`, `D9/A`.

Roman numeral labels use RomanText spelling (`Cad64` is drawn as V with 6–4 stacked, and a V or V7 that follows it in the same key as the continuation figures, ⁵₃ or ⁷₃ joined by dashes): `I`, `V7`, `V65/ii`, `viio7/V`, `ii/o65` (half-diminished), `bII6`, `Ger65`. One or two figures are raised or stacked. Text after a space is set small beside the numeral (`V7 4–3`).

## Fields every annotation accepts

| Field | Meaning |
|---|---|
| `views` | Which views show it: `harmony`, `voice_leading`, `form`. Each type has a default (`DEFAULT_VIEWS`). |
| `role` | `student` or `composer` to show it only for that role; omitted means both. |
| `callout` | The number of the commentary paragraph that discusses this annotation. |

## Errors

`engine.annotate.check` resolves every position before anything is drawn and reports all problems together, in words the model can act on:

```
annotations[2] (nct): No note matches staff=2 pitch=C2 at measure 1 beat 4.0; notes there: Eb5 (staff 1), D2 (staff 2)
```

Unknown fields are rejected, so a misspelled field name fails instead of being ignored.

## Not in version 1 yet

Pedal-point shading, sequence boxes, form labels above phrases, key-area bands, and note colours. (A pedal or a sequence can be named with a `region` meanwhile.)
