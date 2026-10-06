# Engineering log

A record of the problems met while building this tool, what was done about each, and how the results were measured. Numbers come from runs kept in `out/` (not committed) and can be reproduced with the commands at the end.

**The tool:** a plugin for Claude and ChatGPT that reads a MusicXML score and returns the score engraved with a harmonic analysis drawn on it (Roman numerals, cadences, phrases, non-chord tones, voice leading) and a written commentary. A graph neural network (AnalysisGNN) drafts the analysis; the chat model reviews and corrects it; our engine places every label on the engraved page.

## At a glance

- **A two-stage analysis pipeline, measured against human experts.** A neural draft followed by a chat-model review, scored by duration against chord-by-chord readings by human analysts on 12 pieces from Bach to Grieg, and against published teacher and textbook analyses for the rest of a 23-piece set.
- **The review stage raises agreement with experts on 11 of 12 scored pieces.** Weighted by length across 12 pieces (1,158 bars), the share of the music where key, chord and bass all match the human analyst rose from 0.54 to 0.71, and the share with the right key from 0.81 to 0.89. The largest gains were Schumann (0.61 to 0.92), Haydn (0.42 to 0.72) and Beethoven Op. 2 No. 1 (0.47 to 0.73).
- **Checked against what teachers actually wrote.** Against published analyses of 19 pieces (textbook chapters, exam-board teaching notes, articles and dissertations), our analysis agrees with 63% of 431 checkable claims, partly agrees with 26%, and disagrees with 4%, on the judge's first marking, which is lenient (a second marking of the same analysis gives 4 to 18 points less; challenge 9). Every disagreement was read by hand and sorted into areas to improve.
- **Measured which chat model to use.** Over the full 23-piece set, Opus 5.5 at medium effort beat Sonnet 5.5 as the reviewer: full agreement with expert labels 0.66 → 0.71, agreement with teachers' claims 52% → 63%, at 36% more cost and 25% less model time.
- **Found and fixed a silent failure in the neural model's output.** The model names each key's tonic but not its mode, so every minor key was read as major. Recovering the mode from the chords lifted key accuracy on minor-key pieces from 0.00 to 0.92 (Chopin Prelude No. 20), 0.27 to 0.79 (Beethoven Op. 2 No. 1) and 0.20 to 0.89 (Tchaikovsky).
- **Matched expert-to-expert agreement on one movement analysed by three expert teams.** On Beethoven's Op. 2 No. 1, first movement, the reviewed analysis agreed with three independent expert analyses at 0.76 full agreement, against 0.78 between the experts themselves (one movement, one review; a single review varies by about 0.04).
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

**Problem.** In testing on claude.ai, a `.mxl` attached to the chat never reached the server: Claude connectors cannot receive attachments, and a compressed `.mxl` is not readable as text. A first fix (an upload page that gave the user a code to paste back) worked technically, but the owner rejected it as a workaround. A second (a file button inside the chat) was also rejected, because it made users pick a file they had already attached.

**What we did.** Followed the pattern Anthropic's own document skills use: a skill runs the engine inside Claude's sandbox on the attached file, and only a compact note list goes to the server for the neural draft. The model's predictions from the note list matched its predictions from the file on every note of the test nocturne. ChatGPT passes attachments to the server directly, so it keeps the server route.

**Result.** The installed plugin was accepted: one upload, an answer in about a minute.

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

**Problem.** The first annotated pages had labels touching circles, beams and slurs. The requirement set: label text must never be cramped, and other elements give way to it.

**What we did.** Every label is placed with padded clear space, and that space is reserved; anything drawn later (callouts, brackets, arrows) has to stay outside it (`engine/overlay.py`).

### 6. Evaluation infrastructure failures

**Problem.** Partway through the first review run, 39 of 85 passages failed at once. The error kept only the last 300 characters of the reply, which were usage statistics, so the cause was lost.

**What we did.** The error now carries the reason from the reply. Finished passages are cached, so the run resumed where it stopped instead of starting over.

### 7. The judge could not read its sources

**Problem.** The first prose comparison gave Claude only the addresses of the published analyses and let its web tool read them. That tool cannot read most PDFs, and one site reset the connection. Nine of 20 pieces lost at least one source; Mendelssohn and both Ravel pieces lost their only one, so the comparison silently had nothing to compare.

**What we did.** The script now downloads each analysis and extracts its text itself (PDFs with `pypdf`), and gives the text to the model. Short pages, which are contents pages linking to the real analysis (teoria.com splits each analysis into linked pages), still go to the web tool, which follows links. The first results are kept for comparison.

**Result.** Sources read went from 11 of 20 pieces in full to 19 of 20; the one left is behind a site that refuses downloads (HTTP 403). Checkable claims found went from 332 to 402.

### 8. How much of a change is noise? (2026-10-03)

**Problem.** Following the owner's suggestion to base the method on textbooks, the skill gained guidance for modal and impressionist music, drawn from open theory textbooks and Mark DeVoto's definitions (`research_notes/modal/`), and the note table gained a bar-by-bar count of which scale or collection the notes come from (`engine/pitch_collections.py`). Five modal and late-Romantic pieces and four tonal ones were reviewed again, and the judge was changed to re-mark the *same* list of claims (`--claims-from`), so that a new list could not move the score. Teacher claims agreed fell from 60% to 51%. Before believing that, we ran a control: the judge re-marked the unchanged baseline analyses on the same claims.

**Result.** With nothing changed, the judge alone moved agreement from 60% to 53%, and 24 of the 185 verdicts changed. (Challenge 9 found that most of this drop is systematic, not random: the first marking is lenient towards the analysis the claims were written beside. The fair comparison is 53% against 51%.) The modal run's 51% sits inside that noise, as does its small drop on the four tonal pieces (expert-label *full* 0.85 / 0.92 / 0.80 / 0.81 → 0.85 / 0.87 / 0.74 / 0.79). Reading the changed verdicts one by one found one real flaw in the new guidance: it told the model that an unresolved note is a chord tone, so it stopped marking Debussy's unresolved appoggiaturas, which DeVoto names as typical of the style. That was fixed. Most of the other changes were about things the guidance does not touch (registral shape, where a reprise begins), which points to variation between review runs as well.

| Same 9 pieces, 185 claims | Agreed |
|---|---|
| Baseline review, first judging | 60% |
| Baseline review, judged again (control) | 53% |
| Review with the modal guidance | 51% |

**What it means.**
- The modal change has no measurable effect yet, good or bad. It is not claimed as an improvement.
- One judging run carries roughly ±7 points of noise on the share of claims agreed, and per-piece shares far more. The Sonnet → Opus difference (52% → 63% over 400+ claims) is larger than that, but the per-piece teacher tables in this log are single runs and should be read with that in mind.
- Next: measure how much the review itself varies, by reviewing the same pieces twice, and steady the judge by marking each claim several times and taking the majority.

### 9. Textbook methods, measured fairly (2026-10-03)

**What we tried.** The owner suggested basing the whole method on how textbooks teach analysis. From 38 chapters of *Open Music Theory* (`research_notes/common-practice/`), the skill's tonal method was rewritten: start from phrase endings and work backwards, strict cadence criteria, the tonicization–extended tonicization–modulation spectrum, the textbook procedure for chromatic notes and six-four chords, and sequences. Two widely taught Debussy pieces with good analyses were added to the evaluation, "Voiles" (teoria.com and the *Scottish Music Review*) and "Clair de lune" (an MA thesis), bringing it to 25 pieces.

**Three measurements, each against its noise.**
- *Expert chord labels, 12 pieces:* *full* 0.708 before, 0.700 after. Reviewing the same five pieces twice with the same skill moved *full* by 0.01 to 0.06 per piece (0.04 on average), as much as the change of method did.
- *Teacher claims, re-marked on one list:* tonal pieces 64% before, 62% after (294 claims); modal pieces 44% before, 45% after (112); the two new Debussy pieces 33% before, 29% after (49).
- So neither the modal guidance nor the textbook tonal method made a difference that these measurements can see. Pieces moved both ways (Mozart K. 545 18 → 22 claims agreed, Tchaikovsky 17 → 12).

**A second finding about the judge.** The judge writes its list of claims while it can see the analysis under test, and marks that analysis in the same pass. Re-marking the *same* analysis on the same list later gives lower agreement every time:

| Same analysis, same claims | First marking | Marked again |
|---|---|---|
| 13 tonal pieces | 68% | 64% |
| 5 modal pieces | 53% | 44% |
| "Voiles" and "Clair de lune" | 51% | 33% |

The first marking is lenient towards the analysis it was written beside. Comparisons must therefore set a re-marked baseline against a re-marked new run, never the first marking against a re-marking (an earlier draft of challenge 8 did the latter). The teacher-agreement figures elsewhere in this log (63% for Opus, 52% for Sonnet) are first markings: the Sonnet–Opus comparison is like with like, but the absolute shares flatter the tool.

**Why the textbook method changed little, we think.** The method it replaced already covered the same ground in fewer words, and the disagreements that remain are mostly interpretive (where a modulation really happens, which mode a passage is in) or about things a note table does not show (register, texture, layers). One review run varies about as much as these prompt changes.

### 10. Better input instead of more rules: facts and the score image (2026-10-03)

**What we tried.** Since rules from textbooks had not helped, two ways of giving the reviewer more to see:
- *Facts in the note table:* the scale or collection of each bar (per staff where it differs), notes outside the key signature, melody repeats (exact or transposed), and points of arrival.
- *The engraved score:* the passage rendered as ordinary pages (`engine/render.py`, `engrave_pages`), which the reviewer opens before analysing (`eval.review --image`). Chord symbols printed in some source files are stripped first, including from compressed `.mxl` files, so the image cannot give answers away.

**Results, one review each against the baseline** (owner's request: keep tests cheap, no repeats):

| Piece | Measure | Baseline | Facts | Facts + image | Image only |
|---|---|---|---|---|---|
| Bach, Prelude in C | full (labels) | 0.80 | 0.86 | 0.83 | |
| Mozart, K. 545 | full (labels) | 0.85 | 0.86 | 0.89 | |
| Chopin, Prelude No. 20 | full (labels) | 0.85 | 0.89 | 0.89 | |
| Debussy, "Voiles" | teacher claims, median of 3 | 7/24 | 4/24 | 6/24 | |
| Ravel, *Jeux d'eau* | teacher claims, median of 3 | 9/22 | 10/22 | 12/22 | |
| Debussy, "Des pas sur la neige" | teacher claims, median of 3 | 11/25 | 12/25 | 12/25* | |
| Grieg, Notturno | full (labels) | 0.50 | | | 0.46 |
| Bach, chorale BWV 269 (control) | full (labels) | 0.91 | | | 0.91 |
| Debussy, "Clair de lune" | teacher claims, one marking | 10/25 | | | 9/25 |

\* The reviewer did not open the pages for "Des pas"; after the instruction was made firmer it opened them in every passage.

**What it means.** Every difference is within what one review varies by on its own (about 0.04 on *full* per piece, a couple of claims on a teacher list). The image's one clear gain, *Jeux d'eau* (+3 claims, the same in all three markings), did not recur on Grieg or "Clair de lune". Looking at the pages added about 30% to the cost where the reviewer opened them in the first test, and nothing measurable in the second. Neither change is adopted; the facts code was removed, and the image rendering stays in the evaluation tools for later tests.

**Overall, from challenges 8 to 10.** Three kinds of change to the reviewer's instructions and input (textbook rules, computed facts, the score image) made no difference these measurements can detect. The changes that did move the numbers earlier were in the engine (recovering the minor mode, challenge 1) and in the choice of reviewing model (Sonnet to Opus). The most useful result of the day is the measurement itself: knowing that one review and one judging each vary by several points, and that the judge's first marking is lenient, is what stopped us from shipping changes that only looked like improvements.

### 11. Where the remaining errors are, and a rule that did not fix them (2026-10-03)

**Breakdown.** Every stretch of music where the Opus review disagrees with the expert labels (29% of the 12 labelled pieces, by duration) was put in one category:

| Category | Share of the music | Share of what is lost |
|---|---|---|
| Right chord, key label differs: same tonic, other mode (mostly convention, e.g. C minor against C major with borrowed chords) | 3.3% | 11% |
| Right chord, key label differs: other tonic (tonicization against modulation) | 5.2% | 18% |
| Right chord, wrong bass (inversion) | 4.7% | 16% |
| Seventh added or missing | 3.3% | 11% |
| Quality of third or fifth | 2.6% | 9% |
| Related chord (two or more notes in common) | 4.8% | 16% |
| Different chord | 5.0% | 17% |
| No label | 0.5% | 2% |

Almost a third of the loss is a correct chord with a different key label. Mozart K. 332 alone has 17% of its length in the "other mode" row, which is the convention difference found in challenge 1.

**A bass check, tried and rejected.** Where only the bass was wrong, the expert's bass was the lowest note sounding in 38% of cases and ours was not, which suggested a mechanical fix (`eval/bass_check.py`): rewrite the inversion when a chord tone other than the labelled bass is lowest. Scored on the existing reviews, at no model cost:

| Rule | Chord and bass | Full |
|---|---|---|
| None (Opus review) | 0.797 | 0.708 |
| Lowest note starting with the chord | 0.748 | 0.663 |
| Lowest note over the chord's whole duration | 0.789 | 0.700 |

Alberti basses, passing bass notes and song accompaniments defeat both rules; the reviewer's own judgement of the structural bass is better than either. Not adopted.

### 12. RNHybrid, the newer draft model: better keys, worse chords (2026-10-03)

**Where it came from.** RNHybrid, AnalysisGNN's successor (Karystinaios et al., arXiv 2607.13587, July 2026), reports a better Roman numeral score (0.576 against 0.530) and local key (0.872 against 0.828). Its weights on Hugging Face (`manoskary/analysisgnn-hybrid`) carry no licence, but the same full-piece checkpoint, byte for byte (SHA-256 `b4417e1d…`), ships in the author's Scoreprompts space under `license: mit`, the basis on which the current checkpoint was accepted. It pairs the graph network with a frozen MusicBERT-large (`manoskary/musicbert-large`, MIT).

**Setup.** A separate environment (`.venv-rnh`, PyTorch 2.6 CPU, the `gradio` branch of the analysisgnn code in `vendor/analysisgnn-gradio`). It runs our own note list in about 6 s and 2.2 GB for a short piece, 112 s for all 1,158 labelled bars. Two runner fixes were needed, both leaving the current model's output unchanged: undo the old checkpoint's triple softmax only where the probabilities really are flattened (doing it to RNHybrid's plain probabilities scrambled its chord heads to near zero), and keep the Roman numeral head where its size matches the decoder (185 classes). `engine/draft.py` reads chords from that head when a model has a working one.

**Results, draft only, against the expert labels (no chat model involved):**

| Draft, 12 pieces, weighted by length | Key | Root | Chord | Full |
|---|---|---|---|---|
| AnalysisGNN (in use) | 0.811 | 0.811 | 0.729 | 0.535 |
| RNHybrid, chords rebuilt from degree, quality and inversion | 0.866 | 0.748 | 0.637 | 0.493 |
| RNHybrid, chords from its Roman numeral head | 0.824 | 0.691 | 0.616 | 0.499 |
| RNHybrid, Roman numeral head with the paper's beat voter | 0.825 | 0.690 | 0.616 | 0.500 |

Checks that the gap is the model and not our pipeline: its own root head alone scores 0.785 against AnalysisGNN's 0.818; feeding it the original file instead of our note list gives identical predictions; the beat voter changes only 2 to 3% of note-level predictions. The paper's gains are on held-out test sets with its own metric; on these pieces RNHybrid is better on key and worse on chords. Not adopted. Its keys could still be combined with AnalysisGNN's chords (not yet tried).

### 13. A scorer bug, an exact reference for "Clair de lune", and two more review ideas (2026-10-04)

**A bug in our own scorer.** Reading the chord disagreements one by one turned up pairs like `#viio7/vi` (expert) against `viio7/vi` (ours): the same chord, scored as different roots. music21 raises a sharp on vi or vii in a minor context a second time by default; When in Rome writes that sharp as a cautionary sign. The scorer now reads both as cautionary (`Minor67Default.CAUTIONARY`). The fix is confirmed by the expert files themselves: their fit (the share of notes in the expert's own chords) rose for Mozart K. 332 from 0.883 to 0.939 and for Tchaikovsky from 0.858 to 0.907. Weighted *full*: draft 0.535 → 0.542, Sonnet 0.657 → 0.664, Opus 0.708 → 0.717. A correction of the measurement, not of the analysis.

**"Clair de lune" scored exactly.** The DCML experts' labels printed inside its MusicXML lose some positions on export (two labels in one voice come out together, with no offset), so they are read instead from DCML's own harmonies table, which gives each label's bar and onset (`eval/dcml.py`). Fit 0.909; all 150 labels read. Draft 0.59, Opus review 0.71.

**Two more review ideas, one review each on Bach's Prelude in C, Grieg's Notturno and Tchaikovsky's "June" (full, exact labels, rescored with the fixed scorer):**

| | Bach | Grieg | Tchaikovsky | Weighted |
|---|---|---|---|---|
| Baseline | 0.80 | 0.50 | 0.69 | 0.65 |
| Whole-piece overview from the draft (key plan, cadences, phrase ends) | 0.69 | 0.54 | 0.66 | 0.63 |
| The draft model's runner-up where it is a close call | 0.86 | 0.52 | 0.67 | 0.66 |

- *Overview:* worse, and Bach shows why. Its draft key plan is wrong (draft key 0.77), and with that plan in front of it the reviewer's key accuracy fell from 0.89 to exactly 0.77. A summary built from the draft carries the draft's errors to every passage.
- *Runner-up readings:* where shown, the runner-up was the expert's chord in 19% of cases in which the main label was wrong, but the gain after review (+0.01) is within one review's noise.
- Neither is adopted. Cost $10.26.

### 14. The human ceiling: how far experts agree with each other (2026-10-04)

**Question.** After a series of changes that made no measurable difference, how much better could the analysis get? Two expert analysts do not agree perfectly either, so agreement with one of them has a ceiling.

**Method (`eval/ceiling.py`).** When in Rome holds independent analyses of the same Beethoven sonata movements by two or three separate teams (DCML, Dmitri Tymoczko's TAOM, BPS-FH). Each pair was scored in both directions with the same scorer used for our own output, and kept only where both analyses fit the score (at least 0.85 of the notes inside their chords), so that a bar-numbering mismatch is not counted as disagreement. 9 of 26 pairs qualified; most of the rest are misaligned conversions. The TAVERN variation pairs could not be used: their score files crash Verovio.

**Expert against expert, 9 pairs, 1,653 bars, weighted by length:**

| Key | Root | Chord | Chord and bass | Full |
|---|---|---|---|---|
| 0.804 | 0.859 | 0.775 | 0.701 | 0.596 |

**Head to head on one movement**, Beethoven Op. 2 No. 1, i, which has three aligned expert analyses (fit 0.88 to 0.93):

| Full agreement | When in Rome | DCML | Tymoczko | Average |
|---|---|---|---|---|
| Other experts | 0.80, 0.76 | 0.80, 0.77 | 0.76, 0.77 | 0.78 |
| Opus review | 0.73 | 0.80 | 0.74 | 0.76 |
| Sonnet review | 0.56 | 0.59 | 0.58 | 0.58 |
| Draft alone | 0.47 | 0.46 | 0.46 | 0.46 |

**What it means.** On the one movement where the comparison is like with like, the Opus review agreed with the experts about as well as they agree with each other (0.76 against 0.78), and with DCML exactly as well as the When in Rome analyst did (0.80). That is one movement and one review, and the gap is the size of one review's variation, so it shows the reviewed analysis *can* reach expert-to-expert agreement, not that it does in general. The nine-pair figure (experts agree at 0.60 full) comes from different movements from our test set, so it is not a direct comparison with our 0.72; it does show that exact-label agreement between experts is far from 1, which is a likely reason prompt and input changes stopped moving our scores. Making the claim general would need more pieces with several aligned expert analyses, and our reviews of them.

### 15. A survey of 300 pieces, and the cadential 6/4 (2026-10-04)

**Why.** The one change that clearly improved the analysis, recovering the minor mode, came from noticing a systematic error in the draft. Twelve pieces are too few to see more such patterns, so the draft was run on every piece in When in Rome that has a score file beside an expert analysis (`eval/survey.py`): 331 pieces, of which 318 lined up with their scores (Mozart sonatas, Beethoven quartets, Bach preludes, about 180 songs from the OpenScore Lieder corpus), leaving out the evaluation pieces. CPU only, no chat model. The draft model was trained on part of this corpus, so its raw accuracy here is not a fair benchmark; the point was the pattern of errors.

**What it showed.** Draft *full* 0.48 over the survey. Two patterns ran one way across every composer: the draft writes V7 where experts write V (1.3% of all music, against 0.2% the other way), and it reads straight through cadential 6/4s, calling them V or V7 where experts write Cad64 or I64 (about 2.4%). Inversions differ in both directions. Two survey bugs were found and fixed on the way (every song had been read from one shared file).

**Sevenths: not our rule.** Four versions of the rule that upgrades a triad to a seventh chord were scored on all the survey pieces and on the 12 evaluation pieces; the one in use was already the best (*full* 0.473 against 0.467 with the rule off). The extra sevenths come from the model's own quality predictions. Left as it was.

**Cadential 6/4: fixed in the draft.** A V span is now split when it opens, on a beat, with the tonic triad over the dominant bass and no leading tone, and the leading tone then arrives: the opening becomes `Cad64`, the rest stays V or V7 (`engine/draft.py`; tested on a four-bar cadence run through the real model). Deterministic, so the gain is exact rather than within noise:

| Draft | Survey, about 285 pieces | Evaluation, 12 pieces (not used to design it) |
|---|---|---|
| Full before | 0.4731 | 0.5423 |
| Full after | 0.4806 | 0.5481 |
| Root before → after | 0.772 → 0.780 | 0.821 → 0.827 |

A wider version (6/4s resolving only in the next span, and tonic chords over the dominant bass) gave no further gain and was not kept.

### 16. Letting the reviewer check its labels against the notes (2026-10-04)

**What we tried.** My mechanical bass rule (challenge 11) failed because it decided on its own. The alternative: a script lists only clear factual contradictions between each chord label and the notes sounding while it lasts (a seventh that never sounds, a bass that is never the lowest note, most of the chord missing), and the reviewer corrects each label or keeps it with a reason. This needed a Roman numeral reader that runs without music21, as the skill's sandbox has none (`engine/harmony.py`); it agrees with music21 on 2,962 of 2,967 ordinary labels across our pieces, the survey pieces and our reviews, after three conventions were added (the key's own seventh, so IV7 in C has E; a minor chord's seventh is minor; in minor, a flat on a numeral counts from the major scale).

**Design that removes review noise.** Rather than a fresh review, which varies by about 0.04 on its own, the check was run on the baseline review's first answers (`eval.review --selfcheck --start-from opus-medium`), so any difference comes from the check alone. Four pieces, $3.11.

**Result.** 29 labels flagged in 8 passages. The reviewer kept 18 unchanged and changed 11, of which 7 only added an explanation to the label ("V7 over G pedal", "V (D only)") and 4 changed the chord (V7/iv to IV7, viio7 to V9, bVI43 to V43/bII, I to I64). Full agreement was identical on all four pieces; root, chord and bass moved by at most 0.01. The contradictions that the notes reveal are mostly pedal points and incomplete chords the reviewer had already weighed. Not adopted. The `--start-from` option stays: it reruns only a later stage on fixed first answers, which keeps review noise out of a test.

### 17. Slow drafts on the hosted server (2026-10-06)

**Problem.** On Cloud Run (2 vCPU, 4 GiB, scale to zero) the first draft after a deploy took 70 s and the next 22 s, against about 5 s on the development machine. Every draft started a fresh Python process that imported PyTorch and loaded the 127 MB checkpoint again, and on Cloud Run those files are read lazily from a 2.9 GB image.

**What we did.** The model runner gained a `--serve` mode that loads the model once and then answers one request per line; `engine/draft.py` keeps one such process per server and restarts it if it dies or hangs. Replies use their own copy of stdout so library output cannot mix with them.

**Result.** Output identical to a one-off run on the Chopin nocturne. In the container under Cloud Run's limits: first draft 5.6 s (model loading included), later drafts 0.4 s from a note list and about 2 s from a score file. On the development machine a repeat draft fell from 6.5 s to 0.5 s.

**Still open.** On Cloud Run itself the first draft after a deploy still takes about 60 s: importing PyTorch takes 54.6 s there against 3.4 s locally, while loading the model (2.7 s) and the analysis (1.8 s) are quick. The second-generation execution environment did not change this. Later drafts take 0.4–3 s.

### 18. Crowded chord labels (2026-10-06)

**Problem.** Verovio spaces each bar by its notes alone. In a bar with five or six chords (bar 12 of the nocturne, as drawn in a live Claude test) the overlay pushed each numeral right of the one before, so the labels sat next to each other with no clear space, drifted away from their beats, and the last one ran past the end of the staff.

**What we did.** Before laying out the page, `engine/annotate.py` adds an invisible chord symbol (`<harm>`) under the bottom staff for every numeral, padded because Verovio sets chord symbols smaller than our numerals. Verovio widens a bar until its chord symbols fit, and the overlay removes them before drawing the real numerals.

**Result.** In the bars 9–16 test page the crowded bar is wider and every numeral sits under its own beat with clear space, inside the staff. Pages without crowding are spaced as before, apart from small shifts; the reference image for bars 1–8 was regenerated (one system taller).

### 19. ChatGPT's pages read worse than Claude's (2026-10-06)

**Problem.** The first ChatGPT test (nocturne, bars 1–8) drew the same harmonies as Claude but a messier page: "E♭:" before almost every chord, "V⁶/5/vi" for V65/vi, and "vii°7/ii over F" in bar 2 where Sonnet and Opus read ii arriving early with appoggiaturas above the bass. ChatGPT never sees the skill: it had a 12-line guide sent with the draft and only the draft's chord summary, not the beat-by-beat note table.

**What we did.** The renderer writes a key in the numeral row only where it changes, and reads figures written with a slash (6/5, 4/3) as stacked figures. The server now sends ChatGPT the note table and the skill's own rules (`skill/SKILL.md` from "## Method" on), so both apps analyse by the same method from the same evidence.

**Result.** In the next ChatGPT run of bars 1–8 the key appears only at line starts, V65/vi is stacked, and bar 2 is read as ii from beat 3 with the chromatic notes as appoggiaturas, as Sonnet and Opus read it. ChatGPT still wrote explanations into labels ("vii°7 tonic pedal", "ii chromatic APP", "Imaj42"); the shared rules now say a label is the numeral and figures only, with pedals as regions and non-chord tones as `nct`.

### 20. Slow deploys (2026-10-06)

**Problem.** Every deploy rebuilt the whole image on Cloud Build, 5.5–6.3 minutes, though nearly every change was to our code. A layer cache with Kaniko made it worse: 10 minutes to fill the cache, then 7 min 58 s with every heavy step a cache hit, because Kaniko unpacks each cached layer (4.5 minutes) and copies the 2 GB of environments into the final stage again (1.5 minutes). Our own code took under a second.

**What we did.** The image is split. `Dockerfile.base` holds Python, PyTorch, the model and its weights, tagged by a hash of its inputs and built only when they change; `Dockerfile` copies the code on top with an ordinary Docker build, which reuses the base's layers in the registry.

**Result.** Not yet measured: the first deploy builds the base once.

## Checking against teachers' prose

For each piece, a second Claude model reads the published analysis (a textbook chapter, teaching notes, an article or a dissertation), lists up to 25 checkable claims it makes (keys, modulations, cadences, phrase and form boundaries, notable chords, modes), and marks whether our reviewed analysis agrees. This is a model's judgement, not a measurement, and a single run of it varies by several points (challenge 8): every claim and verdict is kept with what our analysis says, for a person to audit (`out/eval/judged/opus-medium/`; the Sonnet run is in `out/eval/judged/sonnet/`).

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
.venv/bin/python -m eval.judge --reviewer RUN --claims-from opus-medium [--repeats 3]   # re-mark the same claims (challenges 8-9)
.venv/bin/python -m eval.review --tag NAME [--image] [--overview] [--alternatives]     # a variant run in its own folder
.venv/bin/python -m eval.ceiling                                   # expert against expert (challenge 14)
.venv/bin/python -m eval.survey                                    # draft over 300 When in Rome pieces (challenge 15)
.venv/bin/python -m eval.bass_check                                # the rejected bass rule (challenge 11)
.venv/bin/python -m eval.review --tag NAME --selfcheck --start-from opus-medium   # the self-check alone (challenge 16)
.venv/bin/python tools/robustness.py                               # 31-score robustness run
```
