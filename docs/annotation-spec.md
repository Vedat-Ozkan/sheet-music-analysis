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
| `abrsm` | Inversion letters: `I6` → `Ib`, `V64` → `Vc`, `V65` → `V7b`. Root-position `a` is omitted; seventh-chord quality, secondary targets and text suffixes remain. |
| `figured_bass` | Roman roots with a separate figure stack alongside them under the bottom bass staff (Piston style). Figures include accidentals relative to the active key; root-position 5/3 is omitted unless altered. |

For `figured_bass`, set `key` on the first harmony and at every key change. Keys carry forward in musical order, including from before a selected passage. A missing or invalid active key is an annotation error; the renderer does not infer major or minor from the signature. Bass accidentals belong on the score's notes, not in the figure stack. Chord symbols and unsupported Roman extensions retain their existing display. Text suffixes such as `4–3` remain free text beside the figures.

Double accidentals in figures use paired signs (`♭♭`, `♯♯`) supported by the bundled fonts.

The skill script accepts `--style current|abrsm|figured_bass` to override this field. Without the argument it uses the list's style. The ABRSM spellings follow the conversions in `engine/notation.py`; exam-board approval of these conventions is still pending.

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
| `region` | `start`, `end`, `label` | Dashed bracket above the system, for a stretch named by what it is built on: `whole-tone`, `E Dorian`, `pentatonic`, `parallel 9th chords`, `pedal on G`. |
| `nct` | `note`, `label` (`P`, `N`, `S`, `APP`, ...) | Circle around the note with the letter beside it. |
| `voice_leading` | `from_note`, `to_note`, optional `label` | Arrow from one note to the other. |
| `callout` | `at`, `number` | Numbered disc above the staff, matching a numbered paragraph of the written commentary. |

A `harmony` label that is not a Roman numeral is drawn as written, so chord symbols work too: `Gmaj7`, `Em9`, `C7(#11)`, `D9/A`.

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

Pedal-point shading, sequence boxes, form labels above phrases, key-area bands, and note colours. (A pedal or a sequence can be named with a `region` meanwhile.)
