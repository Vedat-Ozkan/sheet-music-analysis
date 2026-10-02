# Annotation list, version 1

The annotation list is the contract between the chat model and the renderer. The model says *what* to mark and *where in the music*; the renderer decides where that is on the page. Nothing in the list is a pixel coordinate.

The schema is defined in `engine/annotations.py`; a complete example is `examples/chopin_op9_no2_m1-8.json`.

```json
{
  "version": 1,
  "annotations": [
    {"type": "harmony", "at": {"measure": 3, "beat": 2}, "label": "V65/vi", "callout": 3},
    {"type": "cadence", "at": {"measure": 4, "beat": 3}, "label": "PAC"}
  ]
}
```

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
| `harmony` | `at`, `label`, optional `function` (`T`, `PD`, `D`), optional `key` | Roman numeral on one row under the system. `key` (`"Eb"`, `"f"`) is set where the key starts or changes. Consecutive chords with the same `function` share one colour band behind the staves. |
| `cadence` | `at`, `label` (`PAC`, `IAC`, `HC`, `DC`) | Boxed label under the numerals. |
| `phrase` | `start`, `end`, `label` | Bracket above the system, continued across system breaks. |
| `nct` | `note`, `label` (`P`, `N`, `S`, `APP`, ...) | Circle around the note with the letter beside it. |
| `voice_leading` | `from_note`, `to_note`, optional `label` | Arrow from one note to the other. |
| `callout` | `at`, `number` | Numbered disc above the staff, matching a numbered paragraph of the written commentary. |

Roman numeral labels use RomanText spelling: `I`, `V7`, `V65/ii`, `viio7/V`, `ii/o65` (half-diminished), `bII6`, `Ger65`. One or two figures are raised or stacked. Text after a space is set small beside the numeral (`V7 4–3`).

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

Pedal-point shading, sequence boxes, form labels above phrases, key-area bands, and note colours.
