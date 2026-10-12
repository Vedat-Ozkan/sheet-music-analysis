# Checking student analysis: input contract and MuseScore export

`engine.check_analysis.from_text` returns sorted `Label(measure, beat, key,
figure)` objects. `tests/data/check_analysis/typed_inputs.json` specifies 134
complete student answers and their exact expected labels or clarification.

Every answer needs a bar address. After `m1`, `bar 1` or `measure 1`,
unmarked successive labels use beats 1, 2, … within that bar; commas,
semicolons and newlines separate labels, not bars. Give explicit beats for
other rhythms (`m3 b2.5: V65`). A key alone (`G: I IV V`) leaves positions
unknown and asks for them. An optional `ScoreIndex` validates positions
against the actual score, including pickups and compound meter.

Keys use uppercase tonic for major and lowercase for minor; explicit
major/minor overrides tonic case. Only a key before the first numeral (`key: G major`,
`G:`, `in G major:`) is the starting key. A key between numerals applies from the
next numeral on (`bar 2 I V7 G: V7 I` changes key at the third label). A key
with no numeral after it (`m1 I; G:`) asks where the change occurs, since it
cannot be a starting key; put it before the first chord in the new key
(`m3 G: I`). Two starting keys also ask.
Roman-numeral case is preserved: `II` and `ii` name different chords, so a
student's case error belongs in comparison rather than being auto-corrected.
Mixed case within a numeral (`vIi`, including secondary targets) asks which
case was intended.

Figures normalize Unicode digits, accidentals, ° and /o; letter inversions
become figures (`Ib` → `I6`, `V7c` → `V43`). `It+6` becomes `It6`.
A space may separate a numeral from its inversion (`V 6`), but a comma
cannot (`V, 6`).

Convention: chords are separated by spaces or commas; a hyphen with a chord
on each side (`V - vi`) also separates, but never inside a figure (`V 4-3`).
A digit pair joined by a hyphen or en dash right after a chord (`V7 4-3`)
is a suspension: the label is the chord and the suspension is dropped.
`Cad 6-4` reads as `Cad64`.
A slash always means "of", spaced or not: `V7 / V` is `V7/V`, `ii / V` is
`ii/V`, `V 7 / V`, `V ⁶₅ / ii`, `vii° / V` likewise. A slash between figure
digits is a figure: `I6/4`, `V6/5`, `V4/2` read as `I64`, `V65`, `V42`, and
`V6/5/V` is `V65/V`. A joined chord that is implausible asks a question
instead of guessing: more than one applied target (`I / ii / V / I`,
`V / V / I`), a tonic as the applied chord (`I / V`), or a target that cannot
be tonicized (I, i, vii, a diminished target).
Parentheses, brackets, quotes, periods and exclamation marks around a label
are accepted.
`I64` stays literal second-inversion I: the parser does not infer a cadential
function. `V64-53` asks for the two onset beats rather than inventing them.

## How questions are surfaced

Ambiguous or unreadable answers raise `ClarificationNeeded`, a `ValueError`
subclass with a public `.question` string. The exception message also contains
the question for callers already handling `ValueError`. Parsing returns no
partial answer. A chat caller should show `.question`, obtain the revised
answer, and retry before comparison. Missing bar addresses, mixed numeral
case, conflicting positions/keys, invalid inversions and unplaced resolutions
are covered. Host chat integration is outside this input-only change; there
is no new deployed reply path.

## Actual MuseScore 4 export (2026-10-12)

Locally installed Linux MuseScore Studio **4.7.5** converted the authored
`tests/data/check_analysis/musescore-roman.mscx`, containing twelve native
`Harmony` elements with `harmonyType=1` and `harmonyInfo/name`, to the checked-in
`musescore-roman.musicxml`. Each label is at beat 1 of a 4/4 bar in G major.
This tests export from native Roman analysis, not import of prewritten XML.
The native-score PNG is in the task OUT folder (`musescore-roman-1.png`).

Reproduction from the repository root (set `XDG_DATA_HOME`,
`XDG_CONFIG_HOME`, and `XDG_CACHE_HOME` to writable task-output directories):

```sh
/home/kema/projects/sheet-music-plugin/spike/omr/tools/musescore/squashfs-root/AppRun \
  tests/data/check_analysis/musescore-roman.mscx \
  -platform offscreen -platformtheme generic \
  -o tests/data/check_analysis/musescore-roman.musicxml
```

The offscreen platform plus generic theme avoids the local X11/GTK launch
failure. This build warns about multiple input files because it treats
`generic` as another input; the real source is deliberately first, is the
one processed, and conversion exits 0. Logs are retained in OUT.

MuseScore writes nine `<harmony><numeral>` elements, three fallback
`<harmony><root><root-step text="">C</root-step></root><kind text="…">none</kind>`
elements, and **zero lyrics**. The parser reads those text fallbacks when
their text is a supported Roman numeral. Ordinary chord text shares this XML
shape: a fresh headless export of `musescore-mixed.mscx` writes `N.C.`,
`Cmaj7`, `Am`, `H7`, `C(add9)`, `C7sus4` and `Verse` this way. Unreadable
fallback text is ignored, so it cannot abort import of valid analysis.
MusicXML cannot distinguish an invalid Roman text fallback from ordinary
chord text; use typed labels for clarification of such inputs. Explicit
`<numeral>` and analysis lyrics still report invalid input. The placeholder
C is not treated as the chord root. The exact harmony
content follows (whitespace condensed only):

| Bar | Native student label | MuseScore MusicXML harmony |
| --- | --- | --- |
| 1 | `I` | `<harmony print-frame="no"><numeral><numeral-root text="I">1</numeral-root></numeral><kind>major</kind></harmony>` |
| 2 | `V6` | `<harmony print-frame="no"><numeral><numeral-root text="V">5</numeral-root></numeral><kind>major</kind><inversion>1</inversion></harmony>` |
| 3 | `ii65` | `<harmony print-frame="no"><numeral><numeral-root text="ii">2</numeral-root></numeral><kind>minor</kind></harmony>` |
| 4 | `V7/V` | `<harmony print-frame="no"><numeral><numeral-root text="V">5</numeral-root></numeral><kind>major</kind></harmony>` |
| 5 | `viio7/ii` | `<harmony print-frame="no"><numeral><numeral-root text="vii">7</numeral-root></numeral><kind>minor</kind></harmony>` |
| 6 | `viiø7` | `<harmony print-frame="no"><numeral><numeral-root text="vii">7</numeral-root></numeral><kind>minor</kind></harmony>` |
| 7 | `bII6` | `<harmony print-frame="no"><numeral><numeral-root text="II">2</numeral-root><numeral-alter>-1</numeral-alter></numeral><kind>major</kind><inversion>1</inversion></harmony>` |
| 8 | `N6` | `<harmony print-frame="no"><root><root-step text="">C</root-step></root><kind text="N6">none</kind></harmony>` |
| 9 | `It+6` | `<harmony print-frame="no"><numeral><numeral-root text="I">1</numeral-root></numeral><kind>major</kind><inversion>1</inversion></harmony>` |
| 10 | `Ger65` | `<harmony print-frame="no"><root><root-step text="">C</root-step></root><kind text="Ger65">none</kind></harmony>` |
| 11 | `Fr43` | `<harmony print-frame="no"><root><root-step text="">C</root-step></root><kind text="Fr43">none</kind></harmony>` |
| 12 | `I64` | `<harmony print-frame="no"><numeral><numeral-root text="I">1</numeral-root></numeral><kind>major</kind><inversion>2</inversion></harmony>` |

Five original labels lose meaning: ii65 → ii, V7/V → V, viio7/ii → vii,
viiø7 → vii, and It+6 → I6. MuseScore keeps only the root's Roman case,
leading b/# alteration, and final 6/64 inversion in its numeral branch.
The exported XML cannot reveal that these labels were richer originally.
**Do not promise faithful checking of complex MuseScore analysis via this
export.** Ask the student to supply typed labels or preserve them as lyrics
when those distinctions matter. The parser reads what XML actually states;
it cannot reconstruct erased information. `test_musescore_native_roman_export`
checks all twelve positions, the five losses and their comparison errors.
The existing Bach harmony/lyric real-file test remains passing.

NOT RUN: manual GUI entry (native MSCX authoring and headless export were
used), other MuseScore versions, or a deployed Claude/ChatGPT question flow.
