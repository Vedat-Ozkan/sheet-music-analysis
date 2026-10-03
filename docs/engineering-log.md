# Engineering log

A record of the problems met while building this tool, what was done about each, and how the results were measured. Numbers come from runs kept in `out/` (not committed) and can be reproduced with the commands at the end.

**The tool:** a plugin for Claude and ChatGPT that reads a MusicXML score and returns the score engraved with a harmonic analysis drawn on it (Roman numerals, cadences, phrases, non-chord tones, voice leading) and a written commentary. A graph neural network (AnalysisGNN) drafts the analysis; the chat model reviews and corrects it; our engine places every label on the engraved page.

## At a glance

- **A two-stage analysis pipeline, measured against human experts.** A neural draft followed by a chat-model review, scored by duration against chord-by-chord readings by human analysts on 12 pieces from Bach to Grieg, and against published teacher and textbook analyses for the rest of a 23-piece set.
- **The review stage raises agreement with experts on every scored piece.** Weighted by length across 12 pieces (1,158 bars), the share of the music where key, chord and bass all match the human analyst rose from 0.53 to 0.66, and the share with the right chord root from 0.81 to 0.88. The largest gains were Schumann (0.61 to 0.92), Mozart K. 545 (0.65 to 0.88) and Haydn (0.43 to 0.66).
- **Checked against what teachers actually wrote.** Against published analyses of 19 pieces (textbook chapters, exam-board teaching notes, articles and dissertations), our analysis agrees with 52% of 402 checkable claims, partly agrees with 33%, and disagrees with 6%. Every disagreement was read by hand and sorted into four areas to improve.
- **Measured which chat model to use.** On the three pieces Sonnet handled worst, Opus 5.5 at medium effort raised agreement with the teachers' analyses from 29–40% of claims to 50–86%, and on Beethoven Op. 2 No. 1 raised full agreement with the expert labels from 0.56 to 0.73, at about 56% more cost.
- **Found and fixed a silent failure in the neural model's output.** The model names each key's tonic but not its mode, so every minor key was read as major. Recovering the mode from the chords lifted key accuracy on minor-key pieces from 0.00 to 0.92 (Chopin Prelude No. 20), 0.27 to 0.79 (Beethoven Op. 2 No. 1) and 0.20 to 0.85 (Tchaikovsky).
- **Robust across 31 scores and four centuries.** Monteverdi to Schoenberg, choirs, quartets, songs, piano, transposing instruments: every score passes reading, engraving, drafting and rendering.
- **Shipped around a platform limit instead of asking users to work around it.** Claude connectors cannot receive chat attachments. Rather than an upload page and a code to paste, the plugin runs the engine as a skill inside Claude's sandbox, where the file already is, and sends only a compact note list (about 1,300 characters for 8 bars) to the server for the neural draft.

## Results against human analysts

Score = share of the piece, by duration, where our reading agrees with a human analyst's chord-by-chord reading. *Full* means key, chord and bass all agree. *Fit* is the share of notes that belong to the human's chord: it checks that the reference lines up with the file, so a low value means the comparison itself is unreliable.

Run of 2026-10-02. Draft = AnalysisGNN plus our post-processing. Reviewed = after Claude Sonnet reviews the draft, given only what the skill gives it in real use (no reference analyses, no tools).

| Piece | Fit | Key: draft → reviewed | Root: draft → reviewed | Full: draft → reviewed |
|---|---|---|---|---|
| Bach, Prelude in C major, BWV 846 | 0.97 | 0.77 → 0.77 | 0.91 → 0.98 | 0.68 → 0.69 |
| Bach, chorale "Aus meines Herzens Grunde", BWV 269 | 0.93 | 1.00 → 1.00 | 0.98 → 0.94 | 0.89 → 0.90 |
| Mozart, Sonata K. 332, first movement | 0.88 | 0.82 → 0.79 | 0.84 → 0.91 | 0.60 → 0.64 |
| Mozart, Sonata K. 545, first movement | 0.90 | 0.89 → 0.98 | 0.88 → 0.96 | 0.65 → 0.88 |
| Chopin, Prelude Op. 28 No. 20 | 0.98 | 0.92 → 0.92 | 0.90 → 0.92 | 0.69 → 0.77 |
| Beethoven, Sonata Op. 13 "Pathétique", second movement | 0.95 | 0.78 → 0.77 | 0.85 → 0.93 | 0.63 → 0.69 |
| Beethoven, Sonata Op. 2 No. 1, first movement | 0.89 | 0.79 → 0.79 | 0.78 → 0.82 | 0.47 → 0.56 |
| Haydn, Symphony No. 104, first movement | 0.91 | 0.68 → 0.91 | 0.75 → 0.85 | 0.43 → 0.66 |
| Schubert, "Der Lindenbaum", Winterreise No. 5 | 0.95 | 0.81 → 0.87 | 0.87 → 0.86 | 0.59 → 0.66 |
| Schumann, Kinderszenen Op. 15 No. 1 | 0.96 | 1.00 → 1.00 | 0.96 → 0.96 | 0.61 → 0.92 |
| Tchaikovsky, "June: Barcarolle", Op. 37a No. 6 | 0.86 | 0.85 → 0.90 | 0.77 → 0.84 | 0.46 → 0.63 |
| Grieg, Notturno Op. 54 No. 4 | 0.97 | 0.84 → 0.77 | 0.73 → 0.81 | 0.32 → 0.48 |
<!-- results-table -->

**Across the 12 pieces**, weighted by length:

| | Key | Root | Chord | Chord and bass | Full |
|---|---|---|---|---|---|
| Draft | 0.79 | 0.81 | 0.73 | 0.64 | 0.53 |
| Reviewed | 0.85 | 0.88 | 0.82 | 0.77 | 0.66 |

*Full* improved on all 12 pieces. The review made some things worse:
- **Key:** Grieg (0.84 to 0.77), Mozart K. 332 (0.82 to 0.79) and the Pathétique (0.78 to 0.77).
- **Root:** the Bach chorale (0.98 to 0.94) and Schubert (0.87 to 0.86).

The remaining gap is largely key: on the Bach prelude the root is right 98% of the time after review, but key agreement stays at 0.77, so *full* stays at 0.69.

Pieces without a row have no chord-by-chord human reading; they are checked against prose analyses instead (see "Checking against teachers' prose").

## Which model should review: Sonnet or Opus

All the results above use Claude Sonnet 5.5 as the reviewer. On 2026-10-02 the three pieces where Sonnet matched the teachers' analyses least well were reviewed again by Claude Opus 5.5 at medium effort, with the same prompt, the same draft and the same judge.

| Piece | Teacher claims agreed: Sonnet → Opus | Agreed or partly: Sonnet → Opus | Full (labels): Sonnet → Opus |
|---|---|---|---|
| Bach, Fugue in C minor, BWV 847 | 29% → 50% | 67% → 75% | no labels |
| Beethoven, Sonata Op. 2 No. 1, i | 40% → 86% | 80% → 95% | 0.56 → 0.73 |
| Rachmaninoff, Prelude Op. 23 No. 5 | 29% → 69% | 79% → 100% | no labels |

On Beethoven, where both checks apply, the label scores rose on every measure: key 0.79 → 0.91, root 0.82 → 0.92, full 0.56 → 0.73. Opus also left fewer teacher claims unaddressed (11 of 55 with Sonnet, 5 of 61 with Opus). It cost about 56% more for these passages ($7.70 against $4.94 at list prices) but took less time in total (45 minutes of model time against 54).

**Caveats.**
- Three pieces, one run each.
- The pieces were chosen because Sonnet did worst on them, so some of the gain may be regression to the mean.
- The judge extracts its list of claims afresh on each run (21 against 24 claims for the fugue), so the shares above compare similar but not identical lists.

**Decision (owner, 2026-10-02):** Opus 5.5 at medium effort is the reviewer from now on, without a full re-run on Sonnet's stronger pieces. The tables earlier in this log remain Sonnet results until the next full run.

## Challenges and what we did

### 1. The neural model never says "minor"

**Problem.** On the first evaluation run, Chopin's Prelude No. 20 in C minor scored 0.00 on key: the draft called it C major from start to finish. The AnalysisGNN checkpoint outputs the tonic of each local key but drops its mode, while still counting scale degrees in the right scale. Every minor-key passage was mislabelled, and every chord label inherited the error.

**What we did.** `engine/draft.py` now reads the mode back from the chords: a raised leading tone, a minor or major tonic triad, and whether the third, sixth and seventh degrees sound minor or major. To keep one borrowed chord from flipping the mode, it changes only on clear evidence from the chords around it.

**Result.**

| Piece | Key before | Key after | Full before | Full after |
|---|---|---|---|---|
| Chopin, Prelude Op. 28 No. 20 (C minor) | 0.00 | 0.92 | 0.00 | 0.69 |
| Beethoven, Sonata Op. 2 No. 1, i (F minor) | 0.27 | 0.79 | 0.06 | 0.47 |
| Tchaikovsky, "June" | 0.20 | 0.85 | 0.07 | 0.46 |
| Schubert, "Der Lindenbaum" | 0.76 | 0.81 | 0.52 | 0.59 |
| Mozart, K. 545, i | 0.82 | 0.89 | 0.60 | 0.65 |
| Mozart, K. 332, i | 0.93 | 0.83 | 0.68 | 0.60 |

**Still open.** Mozart K. 332 got worse: some major-key passages are now read as minor. The evidence threshold needs tuning on more pieces before it is final.

### 2. What counts as "correct"?

**Problem.** There is no single right analysis of a piece, and comparing with other AI tools only measures agreement between machines. The owner's call: measure against what a teacher or textbook would write.

**What we did.**
- Surveyed published analyses for 23 slots from Bach to Ravel and paired each with a downloadable score (`reports/Scores with published analyses.md`). 11 pairings were clean, 9 had a named weakness, and 3 had no thorough free analysis at all (Liszt, Grieg, one Rachmaninoff). One pattern stood out: free chord-by-chord analyses exist only for short pieces, so long sonata movements are checked with a prose analysis for form and keys plus an expert label file for the chords.
- Built two checks. Where a human reading is chord by chord, a script scores it by duration (`eval/compare.py`). Where it is prose, a second model lists the checkable claims (keys, cadences, form, notable chords) and marks each as agreed or not (`eval/judge.py`); its verdicts are kept with the claims so a person can audit them.
- Guarded the comparison itself:
  - Some score files have the experts' chord labels printed inside them, so the model under test would see the answer. These are stripped before the run (3 pieces).
  - Bar numbers in analyses and files often disagree (pickups, written-out repeats). The *fit* column catches a misaligned reference before its score is believed.

### 3. Getting the score from the chat to the engine

**Problem.** In testing on claude.ai, a `.mxl` attached to the chat never reached the server: Claude connectors cannot receive attachments, and a compressed `.mxl` is not readable as text. A first fix (an upload page that gave the user a code to paste back) worked technically, but the owner rejected it as a workaround. A second (a file button inside the chat) made users pick a file they had already attached: "i already uploaded the file to the chat, why do i have to redo it like this again?"

**What we did.** Followed the pattern Anthropic's own document skills use: a skill runs the engine inside Claude's sandbox on the attached file, and only a compact note list goes to the server for the neural draft. The model's predictions from the note list matched its predictions from the file on every note of the test nocturne. ChatGPT passes attachments to the server directly, so it keeps the server route.

**Result.** Owner's verdict on the installed plugin: "that's more like it". One upload, an answer in about a minute.

### 4. Real-world MusicXML is messy

**Problem.** The first scores outside Bach chorales broke the reader in different ways.

**What we did** (tested on 31 scores, `tools/robustness.py`):
- Read each staff's durations in its own units; multi-instrument scores were misread when staves used different divisions.
- Joined bars that a file splits in two around a repeat or fermata, and counted bars in order when the file's bar numbers repeat.
- Used sounding pitch for transposing instruments (clarinet, horn).
- Matched the model's notes to the nearest real onset, for files whose tuplets are rounded.
- Accepted files that begin with a byte-order mark or are encoded in Latin-1, as older notation programs write them.

**Result.** All 31 pass every stage, from Monteverdi to Schoenberg.

### 5. Labels that read like a textbook

**Problem.** The first annotated pages had labels touching circles, beams and slurs. Owner: "text like this shouldn't be smushed, it should be clear and be spaced accordingly."

**What we did.** Every label is placed with padded clear space, and that space is reserved; anything drawn later (callouts, brackets, arrows) has to stay outside it (`engine/overlay.py`).

### 6. Evaluation infrastructure failures

**Problem.** Partway through the first review run, 39 of 85 passages failed at once. The error kept only the last 300 characters of the reply, which were usage statistics, so the cause was lost.

**What we did.** The error now carries the reason from the reply. Finished passages are cached, so the run resumed where it stopped instead of starting over.

### 7. The judge could not read its sources

**Problem.** The first prose comparison gave Claude only the addresses of the published analyses and let its web tool read them. That tool cannot read most PDFs, and one site reset the connection. Nine of 20 pieces lost at least one source; Mendelssohn and both Ravel pieces lost their only one, so the comparison silently had nothing to compare.

**What we did.** The script now downloads each analysis and extracts its text itself (PDFs with `pypdf`), and gives the text to the model. Short pages, which are contents pages linking to the real analysis (teoria.com splits each analysis into linked pages), still go to the web tool, which follows links. The first results are kept for comparison.

**Result.** Sources read went from 11 of 20 pieces in full to 19 of 20; the one left is behind a site that refuses downloads (HTTP 403). Checkable claims found went from 332 to 402.

## Checking against teachers' prose

For each piece, a second Claude model reads the published analysis (a textbook chapter, teaching notes, an article or a dissertation), lists up to 25 checkable claims it makes (keys, modulations, cadences, phrase and form boundaries, notable chords, modes), and marks whether our reviewed analysis agrees. This is a model's judgement, not a measurement: every claim and verdict is kept with what our analysis says, for a person to audit (`out/eval/judged/sonnet/`).

Run of 2026-10-02, 19 pieces with a readable source, 402 claims:

| | Claims | Share |
|---|---|---|
| Agree | 210 | 52% |
| Partly agree | 133 | 33% |
| Disagree | 24 | 6% |
| Not addressed | 35 | 9% |

| Piece | Claims | Agree | Partly | Disagree | Not addressed |
|---|---|---|---|---|---|
| Bach, Prelude in C major, BWV 846 | 19 | 10 | 5 | 1 | 3 |
| Bach, chorale 'Aus meines Herzens Grunde', BWV 269 | 25 | 11 | 5 | 2 | 7 |
| Bach, Fugue in C minor, BWV 847 | 21 | 6 | 8 | 3 | 4 |
| Mozart, Sonata K. 332, first movement | 25 | 13 | 10 | 2 | 0 |
| Mozart, Sonata K. 545, first movement | 25 | 17 | 6 | 2 | 0 |
| Chopin, Prelude Op. 28 No. 20 | 18 | 12 | 3 | 3 | 0 |
| Chopin, Prelude Op. 28 No. 4 | 20 | 10 | 7 | 1 | 2 |
| Beethoven, Sonata Op. 13 'Pathétique', second movement | 16 | 11 | 5 | 0 | 0 |
| Beethoven, Sonata Op. 2 No. 1, first movement | 20 | 8 | 8 | 0 | 4 |
| Haydn, Symphony No. 104, first movement | 25 | 16 | 9 | 0 | 0 |
| Schumann, Kinderszenen Op. 15 No. 1 | 14 | 7 | 4 | 1 | 2 |
| Mendelssohn, Song Without Words Op. 19 No. 1 | 17 | 9 | 6 | 2 | 0 |
| Brahms, Intermezzo Op. 118 No. 2 | 25 | 17 | 7 | 1 | 0 |
| Tchaikovsky, 'June: Barcarolle', Op. 37a No. 6 | 24 | 14 | 10 | 0 | 0 |
| Ravel, Sonatine, first movement | – | – | – | – | – (source blocked, HTTP 403) |
| Ravel, Jeux d'eau | 22 | 10 | 8 | 2 | 2 |
| Rachmaninoff, Prelude in B minor Op. 32 No. 10 | 22 | 9 | 9 | 1 | 3 |
| Rachmaninoff, Prelude in G minor Op. 23 No. 5 | 14 | 4 | 7 | 0 | 3 |
| Debussy, 'La fille aux cheveux de lin' | 25 | 12 | 11 | 1 | 1 |
| Debussy, 'Des pas sur la neige' | 25 | 14 | 5 | 2 | 4 |

**Where we disagree with the teachers** (all 24 disagreements read by hand):
- **Modulation or tonicization.** The analyst hears a real modulation; we keep the home key with applied chords. Examples: Bach Prelude in C, bars 5–11 (G major); Brahms Op. 118 No. 2, bar 16 (perfect cadence in E, where we mark a half cadence in A).
- **Cadences at phrase ends.** Mozart K. 332 bars 4 and 12–16, Mendelssohn bar 45: the analyst names a cadence we leave out or label differently.
- **Chromatic chords.** Chopin Prelude No. 20, bar 5: the analyst names a passing diminished seventh; we read V6 with a suspension.
- **Modal and colouristic music.** Debussy, Ravel and Rachmaninoff: whole-tone and modal readings (B♭ Lydian, a whole-tone opening, B Aeolian) that our analysis reads diatonically.

These are the areas to work on next. Some are also points where analysts disagree with each other (the cadential 6/3 in the Bach chorale, the pivot chord in Mozart K. 545).

## Reproducing

```bash
.venv/bin/python -m eval.run                                       # draft alone, scored against expert chord labels
.venv/bin/python -m eval.review                                    # Opus 5.5 at medium effort reviews each passage
.venv/bin/python -m eval.review --model sonnet --effort none       # the Sonnet runs in this log
.venv/bin/python -m eval.run --reviewed out/eval/reviewed/opus-medium   # score the reviewed readings
.venv/bin/python -m eval.judge                                     # compare with published prose analyses
.venv/bin/python tools/robustness.py                               # 31-score robustness run
```
