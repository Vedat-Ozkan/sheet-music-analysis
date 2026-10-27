# Chord labels shared with Cadence Finder

In one chat, Claude can take labels from an analysis here and search Cadence Finder for passages like them. Cadence Finder searches the DCML corpora, which spell some chords differently. Cadence Finder's query parser (`corpus-core`, `Query.corpusSpelling`) rewrites this tool's spellings to the corpus's, so a label can be passed as it is.

| Here | In the corpus | Rewritten by Cadence Finder |
|---|---|---|
| `Cad64` | `V` (the cadential six-four is part of the dominant) | yes |
| `Ger6`, `Ger65` | `Ger6` | `Ger65` → `Ger6` |
| `Fr6`, `Fr43` | `Fr6` | `Fr43` → `Fr6` |
| `It6` | `It6` | same |
| `N`, `N6` | `bII`, `bII6` | yes |
| `ø`, `/o`, `%` (half-diminished) | `%` | yes |
| `o`, `°` (diminished) | `o` | `°` → `o` |
| `viio7` in a minor key | `#viio7` | no: the query has no key, so the tool description tells Claude to add the sharp in minor |

Two things no rewrite fixes:

- **Figures.** If any chord in a Cadence Finder query has an inversion figure, every chord must match exactly as written. Labels copied with figures (`iiø65 V`) often find nothing; drop the figures first.
- **Disagreements about the chord.** Where this tool's analysis and the expert annotation hear a different chord (a half-diminished seventh against a diminished triad, say), an exact search misses the passage. Search the cadence with fewer chords before it.

`tests/test_labels.py` fails when this tool's special labels or quality symbols change, as a reminder to update this table and Cadence Finder's rewrite.
