# Engineering log

A record of the problems met while building this tool, what was done about each, and how the results were measured. Numbers come from runs kept in `out/` (not committed) and can be reproduced with the commands at the end.

**The tool:** a plugin for Claude and ChatGPT that reads a MusicXML score and returns the score engraved with a harmonic analysis drawn on it (Roman numerals, cadences, phrases, non-chord tones, voice leading) and a written commentary. A graph neural network (AnalysisGNN) drafts the analysis; the chat model reviews and corrects it; our engine places every label on the engraved page.

## At a glance

- **A two-stage analysis pipeline, measured against human experts.** A neural draft followed by a chat-model review, scored by duration against chord-by-chord readings by human analysts on 12 pieces from Bach to Grieg, and against published teacher and textbook analyses for the rest of a 23-piece set.
- **The review stage raises agreement with experts on 11 of 12 scored pieces.** Weighted by length across 12 pieces (1,158 bars), the share of the music where key, chord and bass all match the human analyst rose from 0.54 to 0.71, and the share with the right key from 0.81 to 0.89. The largest gains were Schumann (0.61 to 0.92), Haydn (0.42 to 0.72) and Beethoven Op. 2 No. 1 (0.47 to 0.73).
- **Checked against what teachers actually wrote.** Against published analyses of 19 pieces (textbook chapters, exam-board teaching notes, articles and dissertations), our analysis agrees with 63% of 431 checkable claims, partly agrees with 26%, and disagrees with 4%. Every disagreement was read by hand and sorted into areas to improve.
- **Measured which chat model to use.** Over the full 23-piece set, Opus 5.5 at medium effort beat Sonnet 5.5 as the reviewer: full agreement with expert labels 0.66 → 0.71, agreement with teachers' claims 52% → 63%, at 36% more cost and 25% less model time.
- **Found and fixed a silent failure in the neural model's output.** The model names each key's tonic but not its mode, so every minor key was read as major. Recovering the mode from the chords lifted key accuracy on minor-key pieces from 0.00 to 0.92 (Chopin Prelude No. 20), 0.27 to 0.79 (Beethoven Op. 2 No. 1) and 0.20 to 0.89 (Tchaikovsky).
- **Robust across 31 scores and four centuries.** Monteverdi to Schoenberg, choirs, quartets, songs, piano, transposing instruments: every score passes reading, engraving, drafting and rendering.
- **Shipped around a platform limit instead of asking users to work around it.** Claude connectors cannot receive chat attachments. Rather than an upload page and a code to paste, the plugin runs the engine as a skill inside Claude's sandbox, where the file already is, and sends only a compact note list (about 1,300 characters for 8 bars) to the server for the neural draft.

## Results against human analysts

Score = share of the piece, by duration, where our reading agrees with a human analyst's chord-by-chord reading. *Full* means key, chord and bass all agree. *Fit* is the share of notes that belong to the human's chord: it checks that the reference lines up with the file, so a low value means the comparison itself is unreliable.

Run of 2026-10-03. Draft = AnalysisGNN plus our post-processing (with the mode fix of that day, challenge 1). Reviewed = after Claude Opus 5.5 at medium effort reviews the draft, given only what the skill gives it in real use (no reference analyses, no tools). The last column is the Sonnet 5.5 review of 2026-10-02, for comparison.

| Piece | Fit | Key: draft → reviewed | Root: draft → reviewed | Full: draft → reviewed | Full, Sonnet |
|---|---|---|---|---|---|
| Bach, Prelude in C major, BWV 846 | 0.97 | 0.77 → 0.89 | 0.91 → 0.97 | 0.68 → 0.80 | 0.69 |
| Bach, chorale "Aus meines Herzens Grunde", BWV 269 | 0.93 | 1.00 → 1.00 | 0.98 → 0.98 | 0.89 → 0.91 | 0.90 |
| Mozart, Sonata K. 332, first movement | 0.88 | 0.87 → 0.77 | 0.85 → 0.89 | 0.63 → 0.62 | 0.64 |
| Mozart, Sonata K. 545, first movement | 0.90 | 0.89 → 0.97 | 0.88 → 0.98 | 0.65 → 0.85 | 0.88 |
| Chopin, Prelude Op. 28 No. 20 | 0.98 | 0.92 → 0.92 | 0.90 → 0.96 | 0.69 → 0.85 | 0.77 |
| Beethoven, Sonata Op. 13 "Pathétique", second movement | 0.95 | 0.78 → 0.91 | 0.85 → 0.95 | 0.63 → 0.81 | 0.69 |
| Beethoven, Sonata Op. 2 No. 1, first movement | 0.89 | 0.79 → 0.91 | 0.78 → 0.92 | 0.47 → 0.73 | 0.56 |
| Haydn, Symphony No. 104, first movement | 0.91 | 0.68 → 0.94 | 0.75 → 0.87 | 0.42 → 0.72 | 0.66 |
| Schubert, "Der Lindenbaum", Winterreise No. 5 | 0.95 | 0.89 → 0.92 | 0.88 → 0.85 | 0.64 → 0.67 | 0.66 |
| Schumann, Kinderszenen Op. 15 No. 1 | 0.96 | 1.00 → 1.00 | 0.96 → 0.96 | 0.61 → 0.92 | 0.92 |
| Tchaikovsky, "June: Barcarolle", Op. 37a No. 6 | 0.86 | 0.89 → 0.94 | 0.77 → 0.87 | 0.47 → 0.68 | 0.63 |
| Grieg, Notturno Op. 54 No. 4 | 0.97 | 0.84 → 0.75 | 0.73 → 0.84 | 0.32 → 0.50 | 0.48 |
<!-- results-table -->

**Across the 12 pieces**, weighted by length:

| | Key | Root | Chord | Chord and bass | Full |
|---|---|---|---|---|---|
| Draft | 0.81 | 0.81 | 0.73 | 0.64 | 0.54 |
| Reviewed by Sonnet (2026-10-02) | 0.85 | 0.88 | 0.82 | 0.77 | 0.66 |
| Reviewed by Opus (2026-10-03) | 0.89 | 0.90 | 0.84 | 0.80 | 0.71 |

*Full* improved on 11 of 12 pieces. The review made some things worse:
- **Key:** Mozart K. 332 (0.87 to 0.77) and Grieg (0.84 to 0.75). In K. 332 every remaining mode error is a passage Opus calls C minor or F minor (bars 29–40, 58–69, 193–205) where the expert writes the major key with borrowed chords: the chords agree, the key name does not. This is why K. 332's *full* stays at 0.62 while its root rises to 0.89.
- **Root:** Schubert (0.88 to 0.85).

Pieces without a row have no chord-by-chord human reading; they are checked against prose analyses instead (see "Checking against teachers' prose").

## Which model should review: Sonnet or Opus

**First test (2026-10-02).** The three pieces where Sonnet matched the teachers' analyses least well were reviewed again by Opus 5.5 at medium effort, with the same prompt, the same draft and the same judge.

| Piece | Teacher claims agreed: Sonnet → Opus | Agreed or partly: Sonnet → Opus | Full (labels): Sonnet → Opus |
|---|---|---|---|
| Bach, Fugue in C minor, BWV 847 | 29% → 50% | 67% → 75% | no labels |
| Beethoven, Sonata Op. 2 No. 1, i | 40% → 86% | 80% → 95% | 0.56 → 0.73 |
| Rachmaninoff, Prelude Op. 23 No. 5 | 29% → 69% | 79% → 100% | no labels |

Three pieces chosen because Sonnet did worst on them, so some of the gain could be regression to the mean. **Decision (owner, 2026-10-02):** Opus 5.5 at medium effort is the reviewer from now on.

**Full run (2026-10-03).** All 23 pieces, 85 passages, reviewed by Opus:

| | Sonnet 5.5 | Opus 5.5, medium effort |
|---|---|---|
| Full, 12 pieces with expert labels | 0.66 | 0.71 |
| Teacher claims agreed, 19 pieces | 52% of 402 | 63% of 431 |
| Teacher claims disagreed | 6% | 4% |
| Pieces where Opus did better / same / worse on *full* | | 9 / 1 / 2 |
| Pieces where Opus agreed with more teacher claims / same / fewer | | 16 / 1 / 2 |
| Cost at list prices | $30.04 | $40.73 |
| Model time | 318 min | 239 min |

Opus's two lower *full* scores are small (Mozart K. 545 0.88 → 0.85, K. 332 0.64 → 0.62), and so are its two lower teacher scores (Bach chorale 44% → 42%, Debussy "Des pas sur la neige" 56% → 52%).

**Caveats.** One run each. Sonnet reviewed the drafts from before the 2026-10-03 mode fix; that fix moved the draft's own *full* by only 0.01. The judge extracts its list of claims afresh on each run, so the shares compare similar but not identical lists.

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

**Follow-up (2026-10-03): K. 332 got worse.** Some major-key passages were now read as minor. Splitting the draft's key errors into *right tonic, wrong mode* and *wrong tonic* across the 12 pieces showed the mode rule was not the main problem: wrong mode covered 4.4% of the music and wrong tonic 16.7%. Printing the evidence chord by chord found the cause in K. 332, bars 24–28. The model labels viio65/vi, whose C♯ leads to D minor, as a raised leading tone, and the rule counted every such chord as strong proof that the home key, F, had turned minor. Leading tones inside applied chords are now ignored. (A second idea, judging the tonic chord by its sounding third instead of the model's quality, made no difference and was dropped.)

| Draft, 12 pieces | Before | After |
|---|---|---|
| Wrong mode, share of the music | 4.4% | 2.8% |
| Key, weighted | 0.794 | 0.811 |
| Full, weighted | 0.526 | 0.535 |
| Mozart K. 332 key | 0.82 | 0.87 |
| Schubert "Der Lindenbaum" key | 0.81 | 0.89 |
| Tchaikovsky "June" key | 0.85 | 0.89 |

No other piece changed except Haydn, whose *full* fell from 0.43 to 0.42.

**Still open.** Most of K. 332's remaining mode error (bars 29–40, 58–69) is a difference of convention: the expert labels the C minor passages as C major with borrowed chords (i6, ♭VI, ♭III), while we write C minor, with the same chords. The scorer counts these as key errors. Wrong tonic, at 16.7%, is now the bigger target.

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

For each piece, a second Claude model reads the published analysis (a textbook chapter, teaching notes, an article or a dissertation), lists up to 25 checkable claims it makes (keys, modulations, cadences, phrase and form boundaries, notable chords, modes), and marks whether our reviewed analysis agrees. This is a model's judgement, not a measurement: every claim and verdict is kept with what our analysis says, for a person to audit (`out/eval/judged/opus-medium/`; the Sonnet run is in `out/eval/judged/sonnet/`).

Run of 2026-10-03, Opus review, 19 pieces with a readable source, 431 claims:

| | Claims | Share | Sonnet (2026-10-02) |
|---|---|---|---|
| Agree | 273 | 63% | 52% |
| Partly agree | 112 | 26% | 33% |
| Disagree | 18 | 4% | 6% |
| Not addressed | 28 | 6% | 9% |

| Piece | Claims | Agree | Partly | Disagree | Not addressed | Agreed: Sonnet → Opus |
|---|---|---|---|---|---|---|
| Bach, Prelude in C major, BWV 846 | 18 | 13 | 3 | 0 | 2 | 53% → 72% |
| Bach, chorale "Aus meines Herzens Grunde", BWV 269 | 24 | 10 | 8 | 1 | 5 | 44% → 42% |
| Bach, Fugue in C minor, BWV 847 | 24 | 12 | 6 | 2 | 4 | 29% → 50% |
| Mozart, Sonata K. 332, first movement | 25 | 14 | 7 | 2 | 2 | 52% → 56% |
| Mozart, Sonata K. 545, first movement | 25 | 18 | 7 | 0 | 0 | 68% → 72% |
| Chopin, Prelude Op. 28 No. 20 | 19 | 13 | 4 | 1 | 1 | 67% → 68% |
| Chopin, Prelude Op. 28 No. 4 | 25 | 15 | 7 | 1 | 2 | 50% → 60% |
| Beethoven, Sonata Op. 13 "Pathétique", second movement | 19 | 16 | 2 | 0 | 1 | 69% → 84% |
| Beethoven, Sonata Op. 2 No. 1, first movement | 21 | 18 | 2 | 0 | 1 | 40% → 86% |
| Haydn, Symphony No. 104, first movement | 31 | 25 | 5 | 1 | 0 | 64% → 81% |
| Schumann, Kinderszenen Op. 15 No. 1 | 17 | 10 | 5 | 0 | 2 | 50% → 59% |
| Mendelssohn, Song Without Words Op. 19 No. 1 | 22 | 14 | 7 | 1 | 0 | 53% → 64% |
| Brahms, Intermezzo Op. 118 No. 2 | 25 | 18 | 4 | 2 | 1 | 68% → 72% |
| Tchaikovsky, "June: Barcarolle", Op. 37a No. 6 | 24 | 18 | 5 | 0 | 1 | 58% → 75% |
| Ravel, Sonatine, first movement | – | – | – | – | – | – (source blocked, HTTP 403) |
| Ravel, Jeux d"eau | 22 | 10 | 7 | 4 | 1 | 45% → 45% |
| Rachmaninoff, Prelude in B minor Op. 32 No. 10 | 25 | 12 | 11 | 0 | 2 | 41% → 48% |
| Rachmaninoff, Prelude in G minor Op. 23 No. 5 | 16 | 11 | 5 | 0 | 0 | 29% → 69% |
| Debussy, "La fille aux cheveux de lin" | 24 | 13 | 9 | 1 | 1 | 48% → 54% |
| Debussy, "Des pas sur la neige" | 25 | 13 | 8 | 2 | 2 | 56% → 52% |

**Where we disagree with the teachers** (all 18 disagreements read by hand):
- **Modal, whole-tone and colouristic music (7).** Ravel's *Jeux d'eau* (a whole-tone opening read as Emaj9, polytonality at bar 26, the whole-tone root motion at bars 68–69, a decorated V/V–V–I at bars 51–59 heard as a pedal with no cadence) and Debussy (bar 8 of *Des pas*: F♯ and D read as chord tones of a whole-tone chord, not appoggiaturas; bar 34 of *La fille* read as V42 where the analyst hears VII).
- **Modulation or tonicization (3).** Brahms Op. 118 No. 2 bars 1–16: the analyst hears a move to E with a perfect cadence at bar 16; we stay in A and mark half cadences. In the Bach fugue we go the other way, adding a G minor region the analyst does not hear.
- **Cadences at phrase ends (3).** Mozart K. 332 bar 4 (analyst: half cadence; we: none) and bar 76 (analyst: imperfect; we: perfect), Mendelssohn bars 44–45.
- **Chromatic chords (3).** Chopin Prelude No. 20 bar 5 (the analyst's Neapolitan resolving to a dominant of G; we read viio7 with a neighbour note), the Bach fugue bars 26–28 (VI replacing iv), and the Bach chorale's cadential 6/3 at bar 12, a point analysts themselves dispute.
- **Form (2).** Haydn: where the transition starts (bar 32 or 50; the published text notes both views). Chopin Prelude No. 4: the climax at bar 18 rather than 16–17.

Modal and colouristic music is now the largest group, and Ravel is the one piece where Opus did not improve on Sonnet. That is the next area to work on.

## Reproducing

```bash
.venv/bin/python -m eval.run                                       # draft alone, scored against expert chord labels
.venv/bin/python -m eval.review                                    # Opus 5.5 at medium effort reviews each passage
.venv/bin/python -m eval.review --model sonnet --effort none       # the Sonnet runs in this log
.venv/bin/python -m eval.run --reviewed out/eval/reviewed/opus-medium   # score the reviewed readings
.venv/bin/python -m eval.judge                                     # compare with published prose analyses
.venv/bin/python tools/robustness.py                               # 31-score robustness run
```
