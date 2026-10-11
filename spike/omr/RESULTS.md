# OMR spike results (Phase 2, step 1), 2026-10-11

Local only (WSL2, 16 cores, CPU, 19 GB RAM). No cloud, no commits. Tools: homr 0.6.2 (pip), Audiveris 5.11.0 (Linux .deb unpacked with `dpkg-deb -x`, no sudo, bundled JRE).

## Inputs

Ground truth = MusicXML already in the repo's eval and engraving corpora, copied to `truth/`.

| Piece | Ground truth | Born-digital PDF (`pdf/`) | Scan (`scans/`) |
|---|---|---|---|
| Bach chorale BWV 269 | `bach-269.mxl` (24 bars in XML, 229 notes) | 1 page | none (see below) |
| Mozart K.545, 1st movement | `mozart-k545-1.mxl` (73 bars, 1281 notes) | 4 pages | Peters "Sonate facile", pp. 234-237 of an archive.org scan (4 pages, 73 bars) |
| Chopin Prelude Op.28 No.4 | `chopin-prelude-4.mxl` (26 bars, 606 notes) | 2 pages (page 2 is a 1-bar fragment) | G. Schirmer 1915 (Joseffy ed.), p. 15 of an archive.org scan (1 page, fingerings printed) |

- MuseScore is not installed, so the born-digital PDFs come from the repo's own Verovio path (`Engraving.pdf()`), via `make_pdfs.py`. They are cleaner than a typical MuseScore export (no fonts to embed, perfect geometry), so the born-digital numbers are an optimistic bound.
- IMSLP: the API answers, but file downloads return a bot-check (captcha) page to scripted requests. I did not try to get around it. The scans are public-domain archive.org items instead (`31761034110379` Mozart Peters; `chopinpreludes00unse` Chopin Schirmer). These are real printed scans, paper-toned, as IMSLP's would be. Only two scans (Mozart, Chopin); no Bach-chorale scan.
- PDFs were rasterised at 200 dpi (pypdfium2, `rasterize.py`) for homr, which takes images. Audiveris took the PDFs directly.

## Method (`compare.py`)

Every pitched note becomes a MIDI number (chord notes separate, all parts and staves pooled per bar). Bars are aligned in order, and also by dynamic programming that allows skipped bars (same numbers in every case below). Pitch agreement = notes shared (multiset overlap, per bar) / notes in the ground truth, summed over the piece. It ignores rhythm, voices, ties, key and meter. `scoreindex_check.py` loads each file through the engine's `load_toolkit` + `ScoreIndex`.

## Results

| Tool | File | Bars (truth/OMR) | Notes (truth/OMR) | Pitch agreement | ScoreIndex |
|---|---|---|---|---|---|
| homr | Bach chorale PDF | 24/24 | 229/229 | **100.0%** | loads |
| homr | Mozart K.545 PDF | 73/73 | 1281/1280 | 89.1% | loads per page (4 files, each page is its own MusicXML, not merged) |
| homr | Chopin Prelude 4 PDF | 26/26 | 606/606 | **99.8%** | loads per page |
| homr | Mozart K.545 scan | 73/73 | 1281/1283 | 97.3% | pages 1-2 load, **pages 3 and 4 crash Verovio (segfault, exit 139)**; key/meter read wrong on some pages (3/4 instead of 4/4) |
| homr | Chopin Prelude 4 scan | 26/26 | 606/601 | 93.9% | loads |
| Audiveris | Bach chorale PDF | 24/24 | 229/228 | **99.6%** | loads |
| Audiveris | Mozart K.545 PDF | 73/73 | 1281/1266 | **97.1%** | loads |
| Audiveris | Chopin Prelude 4 PDF | default run: **FAILED** ("No system found" on the 1-bar page 2, no MusicXML written). With `-sheets 1`: 25/26 | 606/597 | 97.5% (page 1 only, last bar lost) | loads (25 bars) |
| Audiveris | Mozart K.545 scan | 73/73 | 1281/1235 | 84.8% | loads, but key read as 1 flat (piece is C major) |
| Audiveris | Chopin Prelude 4 scan | 26/25 | 606/596 | 95.5% | loads |

Reading of the numbers: pitch agreement is a floor on usability, not a measure of it. A bar with one wrong note counts as nearly right here, but a wrong key signature or meter (seen in both tools) makes every note in the analysis wrong downstream. I did not check key and meter against truth beyond the observations in the table.

## Timings and sizes

| | homr | Audiveris |
|---|---|---|
| Install | `pip install homr` into a venv: 20 s, 545 MB venv (onnxruntime, opencv, rapidocr) | .deb download 78 MB, unpacked 188 MB (JRE bundled; system Java 11 not used), seconds |
| Model download | `homr --init`: 8 s, three ONNX models 157 MB on disk (57 + 47 + 53 MB) | none (in the package) |
| Seconds per page, CPU | 11-12 s for a normal page, 17.5 s for a dense Chopin page, 2.5 s for a 1-bar page; includes model load each run (one process per page) | 10.5 s (1 page); 8 s/page on 4 pages (31.9 s); 13-19 s for the 1-2 page Chopin runs; includes JVM start, uses about 2.3 cores |
| Peak RAM | 0.91-1.24 GB | 0.84-1.52 GB |
| Output | one MusicXML per image; multi-page needs merging | one `.mxl` per PDF, all pages merged |
| Failure modes seen | wrong meter/key on scan pages; two outputs that crash Verovio natively | whole-book failure when one page has no staff system; wrong key on the Mozart scan; no OCR languages installed (titles and lyrics not read; not needed here) |

Both are under the plan's 30 s a page on this 16-core machine. Cloud Run's 1-2 vCPU would be slower; NOT RUN, step 2 of the plan measures it.

## Recommendation (the plan's rule: about 95% pitch agreement on clean PDFs, pick one or none)

- Clean (born-digital) PDFs, 3 pieces: Audiveris 99.6 / 97.1 / 97.5 (mean 98.1%, one default-run failure on a 1-bar trailing page). homr 100 / 89.1 / 99.8 (mean 96.3%, but 89% on the Mozart sonata).
- Audiveris clears 95% on all three clean files; homr misses it on Mozart. The clean-PDF sample is small (3 files, one engraver), so this is a pointer, not a proof.
- On scans (out of Phase 2's scope) both are marginal: homr 97.3 / 93.9, Audiveris 84.8 / 95.5.

Recommendation: **Audiveris**, for born-digital PDFs only, with two conditions found here. Process pages so a page with no staff does not fail the book (try the whole file, then fall back to per-page `-sheets`, or drop pages with no staves). The confirm-the-score step is mandatory, because wrong key or meter does not show in pitch agreement. Costs: a JVM and a 188 MB install on the server, about 1.5 GB RAM; in the Claude sandbox it is a 78 MB download plus the bundled JRE (not measured there). homr is the lighter install (pip) and is faster on dense pages, but it was worse on the largest clean file and produced files that crash Verovio, which is a native segfault, not a catchable error. The Phase 2 owner decision on tool stays open.

## Not run

- Sandbox (Claude host) install and memory; Cloud Run time and memory per page; cost quote.
- MuseScore-made PDFs (MuseScore not installed); real-world PDFs (engraved by other programs, with fonts and layout differences).
- A scanned Bach chorale; IMSLP files (blocked by bot check).
- Rhythm, key, meter, voice and tie comparison against truth.

## Files

`make_pdfs.py`, `rasterize.py`, `extract_pages.py`, `compare.py`, `scoreindex_check.py` (scripts). `homr-venv/`, `tools/` (Audiveris unpack), `imslp/` (the two downloaded full-volume PDFs), `scans/` (page cuts), `out/` (OMR outputs and logs). Download directories are untracked and large; none were committed.

---

# Round 2 (same day): realistic PDFs, key/meter/rhythm, the short-last-page failure

Round 1's born-digital PDFs came from our own Verovio engine, so they stand in poorly for uploads. Round 2 uses MuseScore 4 and Mutopia (LilyPond) PDFs.

## New inputs

| PDF | Source | Pages |
|---|---|---|
| `r2/pdf/{bach-269,mozart-k545-1,chopin-prelude-4}.pdf` | MuseScore Studio 4.7.4 (Windows install, run from WSL) from the same three ground-truth files. The truth files carry Roman-numeral analysis text, which MuseScore prints, so the pages have extra text in the way, like a student's marked-up score | 2 / 5 / 2 |
| `r2/pdf/chopin-28-4-mutopia.pdf` | Mutopia, Chopin Op.28 No.4 (LilyPond engraving, A4), matched to `chopin-prelude-4.mxl` | 1 |
| `r2/pdf/mozart-k545-1-mutopia.pdf` | Mutopia, Mozart K.545 mvt 1 (LilyPond), matched to `mozart-k545-1.mxl` | 5 |

- The Linux AppImage (MuseScore 4.7.5, unpacked with `--appimage-extract`, 566 MB, runs headless in under 2 s a score) also worked; its PDFs are in `r2/pdf-linux/` and were not used for the numbers. The first Audiveris run on them gave similar output.
- The Mutopia and ground-truth files are different editions of the same music (bar counts match for Chopin, but the Mozart edition differs somewhere: homr returned 71 aligned bars against 73). Pitch agreement against a different edition understates the tool a little.
- No Bach chorale from Mutopia: not looked for.

## compare.py now also reports (see its docstring)

- **Rhythm**: of the pitches that matched, the share whose duration (in quarter notes) also matches.
- **Key / meter**: share of aligned bars whose key signature (fifths) or time signature equals the truth's, with the state carried over bars and pages (so homr's per-page files are joined correctly). A missing `<key>` counts as C major, because Audiveris omits it for C major (before this fix its Mozart key score was wrongly 0).

## Round 2 results (pitch / rhythm / key bars / meter bars; all in %)

| Tool | PDF | Bars truth/OMR | Pitch | Rhythm | Key | Meter | ScoreIndex |
|---|---|---|---|---|---|---|---|
| homr | MuseScore Bach | 24/24 | **100.0** | 100.0 | 100 | 100 | loads (2 page files) |
| homr | MuseScore Mozart | 73/73 | 97.7 | 99.2 | 100 | 100 | page 2 of 5 crashes Verovio (segfault) |
| homr | MuseScore Chopin | 26/26 | **99.7** | 99.5 | 100 | 100 | loads |
| homr | Mutopia Chopin | 26/26 | **99.3** | 99.0 | 100 | 100 | loads |
| homr | Mutopia Mozart | 71 aligned of 73 | 89.9 (74.3 bar-by-bar) | 93.8 | 100 | 100 | pages 2-5 all crash Verovio |
| Audiveris | MuseScore Bach | 24/24 | **99.6** | 100.0 | 100 | 100 | loads |
| Audiveris | MuseScore Mozart | 73/73 | 91.2 | 98.9 | 100 | 100 | loads |
| Audiveris | MuseScore Chopin | 26/25 (last bar lost, 2nd page) | 98.7 | 99.0 | 100 | 100 | loads |
| Audiveris | Mutopia Chopin | 26/26 | 98.7 | 98.8 | 100 | 100 | loads |
| Audiveris | Mutopia Mozart | 73/73 | 96.5 | 98.9 | 100 | 100 | loads |

Round 1 re-scored with the new columns (pitch / rhythm / key / meter, %): homr Verovio Bach 100/100/100/100, Mozart 89.1/99.1/100/100, Chopin 99.8/99.2/100/100; homr scans Mozart 97.3/83.1/100/**39.7** (meter read as 3/4 in most bars), Chopin 93.9/87.3/100/100; Audiveris Verovio Bach 99.6/100/100/100, Mozart 97.1/99.8/100/100, Chopin (page 1 only) 97.5/95.3/100/100; Audiveris scans Mozart 84.8/98.7/**95.8**/100 (key wrong in 3 bars; the earlier "1 flat" remark was a partial misreading), Chopin 95.5/98.1/100/100.

Means over the five round-2 clean PDFs: homr pitch 97.3%, Audiveris 96.9%. Both clear about 95% on the mean; they split on which files they miss (homr: the Mutopia Mozart edition mismatch; Audiveris: MuseScore Mozart, with the analysis text on the page).

## Timings and memory, round 2

| | homr | Audiveris |
|---|---|---|
| Per page | 6-17.5 s (8 s Bach page 1, 6 s the small second page, 10-11 s Mozart pages, 17.5 s dense Mutopia Chopin) | 12 s (1 page), 11.8 s (2 pages), 16 s (2), 36 s (5 pages MuseScore Mozart, 7 s/page), 40 s (5 pages Mutopia), JVM start included |
| Peak RAM | 0.92-1.37 GB | 0.83-1.16 GB |
| MuseScore PDF step | not part of either tool; 0.4-1.6 s a file | |

## ScoreIndex and homr

homr's files make Verovio crash natively (segfault, not catchable in Python) on 7 of the 27 page files in rounds 1 and 2 (all Mozart: scan p3-p4, MuseScore p2, Mutopia p2-p5). I did not find why. A server would need to load every homr result in a throwaway subprocess. homr also writes one file per page with key and meter only where it saw them, so merging pages needs carry-over logic; Audiveris returns one merged file, and all its outputs load.

## The Audiveris failure on a short last page (item 4)

Cause: the 1-bar last page (2481x640 px) of the Verovio Chopin PDF gives "No system found", Audiveris flags that sheet invalid, and the one-shot `-batch -export` exits 1 with "Error in export" and writes no MusicXML, although page 1 was transcribed and saved in the `.omr`.
- **Works (fix 1)**: do not stop at the failure. The `.omr` is saved anyway. Run `Audiveris -batch -export -output <dir> <book>.omr` on it (2 s): it exports the valid sheets only. Result: 25 of 26 bars; the invalid page's bar is lost. The same effect comes from `-sheets 1`.
- **Does not work (fix 2)**: white-padding the page to full size (`pad_pages.py`, 300 dpi) gives the same error.
- **Does not apply**: the MuseScore 2-page Chopin PDF has a real second page and converted without error.
- Remaining gap: the last bar on such a page is lost (the confirm-the-score step would show it). Not tried: stitching short last pages onto the previous page, or an Audiveris constant for the minimum system size.
- Practical rule for `read_pdf`: run the one-step command; if it exits non-zero but wrote an `.omr`, export from the `.omr`; accept that pages with no system are skipped, and tell the user which pages were skipped.

## Revised recommendation

Still **Audiveris**, born-digital PDFs only, but the numbers no longer separate the tools on accuracy; the decision is now on robustness:
- Accuracy on realistic clean PDFs is a tie (means 96.9% vs 97.3%, both with a weak file). Neither is at 99% across the board; the confirm-the-score step stays mandatory.
- Key, meter and rhythm: both are good on clean PDFs (key and meter 100% for every clean file, rhythm 93.8-100%). The only key or meter errors seen were on scans (homr meter on the Mozart scan, Audiveris key in 3 bars).
- Audiveris: no crashes in the engine, one merged file, bars preserved, with a known workaround for a failed short last page (above). Cost: JVM, 188 MB install, about 1.2 GB RAM, 7-8 s a page.
- homr: lighter install and as accurate, but 7 of 27 page files crash Verovio and its pages need merging. Picking homr would mean also writing a repair or isolation step first.
- Sample size is small (3 pieces, 5 clean PDFs, 2 engravers beyond Verovio); the owner decision on the tool stays open.

## Round 2 not run

Cloud Run and Claude-sandbox install/time/RAM; PDFs from other engravers (Finale, Sibelius, Dorico) or scanned-then-exported PDFs; a Mutopia Bach chorale; LilyPond (not needed, MuseScore ran); why homr output crashes Verovio.

## Files added

`r2/pdf/` (inputs used), `r2/pdf-win/`, `r2/pdf-linux/` (MuseScore outputs), `mutopia/` (downloads), `tools/musescore/` (AppImage unpack), `r2/homr/`, `r2/aud/` (outputs), `r2/fix1/`, `r2/fix2/` (short-page experiments), `pad_pages.py`. `.gitignore` in `spike/omr` ignores everything except `RESULTS.md`, `*.py` and itself.
