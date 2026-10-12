# Phase 6, step 1: Roman numeral import spike

Tested on Windows MuseScore Studio 4.7.4, build `7688c00`, via WSL on
2026-10-11. This is an isolated compatibility experiment, not an engine export.

The source is `out/engraving/scores/bach-269.mxl`; the existing reviewed
annotations are `examples/engraving/bach-269.json`. Eight complete 3/4 bars
(1–8) are retained. The pickup is omitted, source fragments 7 and 7a are
joined, repeats and fixed layout coordinates are removed, and the initial
attributes are carried forward. Pitches and durations are retained. Both
variants place the same 21 labels at bass note onsets, including beat 2.5
in bar 3. Soprano song lyrics remain.

`a-harmony.musicxml` uses numeric numeral roots with Roman `text`, explicit
zero alteration, G-major numeral-key, chord kind and numeric inversion.
The kind text supplies diminished/seventh suffixes; inversion figures must
be interpreted by the importer. `b-lyrics.musicxml` writes the complete
annotation text in bass lyric line 1.

Rebuild and validate against the official W3C MusicXML 4.0 XSD:

```sh
.venv/bin/python spike/export/make_fixtures.py
```

Schema files are fetched from
<https://raw.githubusercontent.com/w3c/musicxml/v4.0/schema/>;
the resolver maps the two imported schemas locally without modifying them.

For each variant and output extension `mscx` and `pdf`, run:

```sh
variant=a-harmony
extension=mscx
"/mnt/c/Program Files/MuseScore 4/bin/MuseScore4.exe" \
  -o "$(wslpath -w "$PWD/spike/export/$variant.$extension")" \
  "$(wslpath -w "$PWD/spike/export/$variant.musicxml")"
```

All four conversion logs record successful exit codes. MuseScore also
generated small native-score sidecar files in this directory.

```sh
.venv/bin/python spike/export/check_results.py
spike/omr/homr-venv/bin/python - <<'PY'
from pathlib import Path
import pypdfium2 as pdfium
p = Path('spike/export')
for variant in ('a-harmony', 'b-lyrics'):
    doc = pdfium.PdfDocument(p / (variant + '.pdf'))
    for i in range(len(doc)):
        doc[i].render(scale=1.4).to_pil().save(p / f'{variant}-page-{i+1}.png')
PY
```

`results.json` verifies every label's measure and beat, including the sole
harmony text mismatch (`ii65` → `ii76` at bar 6, beat 2). Both PNGs were
visually inspected: the numerals appear beneath the bass; lyric figures
are ordinary inline text. The harmony rendering crowds adjacent labels
in bars 5–6. Each PDF has one page.

The source excerpts identify exact upstream URLs and line numbers at the
tested build. Import selects `HarmonyType::ROMAN` when numeral-root's
`text` starts with a Roman letter; MSCX writes this as `harmonyType=1`.
The import concatenates function text, kind text and triad inversion
figures, explaining the seventh-inversion error. The export's ROMAN
branch emits `<numeral>` and infers only major/minor and `6`/`64`
inversions; richer qualities and seventh figures are not faithfully encoded
by that branch. This export finding is source inspection, not a GUI-created
analysis round-trip. Dorico is not installed and was NOT RUN.
