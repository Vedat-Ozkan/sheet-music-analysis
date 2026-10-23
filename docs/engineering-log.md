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

**Later the same day.** The file button (`choose_score`), built when Claude connectors could not receive attachments, was removed. Claude now uses the plugin, and ChatGPT passes attached files straight to the server, so the button only covered a forgotten attachment, at the cost of a fourth tool, a card that sized itself badly in ChatGPT and an upload endpoint. Without an attachment, ChatGPT now asks the user to attach the file.

### 20. Slow deploys (2026-10-06)

**Problem.** Every deploy rebuilt the whole image on Cloud Build, 5.5–6.3 minutes, though nearly every change was to our code. A layer cache with Kaniko made it worse: 10 minutes to fill the cache, then 7 min 58 s with every heavy step a cache hit, because Kaniko unpacks each cached layer (4.5 minutes) and copies the 2 GB of environments into the final stage again (1.5 minutes). Our own code took under a second.

**What we did.** The image is split. `Dockerfile.base` holds Python, PyTorch, the model and its weights, tagged by a hash of its inputs and built only when they change; `Dockerfile` copies the code on top with an ordinary Docker build, which reuses the base's layers in the registry.

**Result.** Not yet measured: the first deploy builds the base once.

### 21. Cloud Run billed four hours a day with no analyses (2026-10-09)

**Problem.** Cloud Run reported about 15,450 billable instance-seconds a day on 7 and 8 October (4.3 hours, at 2 vCPU and 4 GiB about US$22 a month after the free tier) while the server drew nothing: no draft or render was logged. The request log showed 123 `POST /mcp` requests from Claude held open for exactly 301 s, one after another around the clock, each ending in Cloud Run's "Truncated response body" warning at the 300 s request timeout. All other requests took under a second; cold starts (about 24 a day, 11 s each) were small.

**Cause.** Claude's connector speaks the 2026-07-28 MCP protocol. After `initialize` it sends `subscriptions/listen`, a request whose response is a server-sent event stream kept open until the client disconnects, so it can be told when the tool list changes. The `mcp` SDK (2.2) serves that method on every `MCPServer` by default, so our server acknowledges and holds the stream; Cloud Run bills the whole time a request is open; at 300 s it cuts the stream and Claude re-listens at once. Cloudflare also keeps its connection to Cloud Run open for the full 300 s after the client drops (a probe closed after 12 s was still logged at 301 s). Reproduced with a hand-made `subscriptions/listen` request against the live server.

**What we did.** `server/app.py` removes the `subscriptions/listen` handler after the server is built. Without it the server advertises no change notifications at the 2026 protocol, so a client has no reason to listen, and a listen request gets an immediate method-not-found instead of a held stream. Nothing else uses the stream: our tool list never changes.

**Result.** After the deploy a hand-made listen request is refused in 0.3 s, and Claude's next two handshakes (seven requests) all finished in under 10 ms with nothing held open six minutes later. Before: 15,450 billable seconds a day; expected now: a few hundred (cold starts and short requests), inside the free tier. To be confirmed from the next day's metric.

### 22. Labels piled on each other, and lone bars on the last line (2026-10-10)

**Problem.** Five passages from five eras (a Bach chorale, Mozart K. 545, Schubert's "Der Lindenbaum", Brahms Op. 118 No. 2, Debussy's "Clair de lune"), each drawn from a hand-checked analysis, showed three kinds of fault. Labels landed on each other or on the music: "N" over "N" in Debussy bar 3, "APP" over "APP" on a sharp in Brahms bar 8, "chromatic" on a bass clef. Lines were filled greedily, so 8 bars of Mozart came out 4 + 3 + 1 with bar 8 alone. A MuseScore export of the Mozart had no clef on the left hand, and Verovio drew none.

**Cause.** When no spot near a note was clear, `_place_label` returned its first choice anyway. Two notes of one chord with the same label got two circles and two labels. The line joining a distant label to its note was not counted as taken space. Line breaks were Verovio's greedy fill. A staff with no clef is treble in MusicXML, but Verovio leaves it blank.

**What we did.** Label placement now also tries spots to either side, and when nothing is clear it takes the spot that covers the least. Notes of one chord with the same label share a circle and a label, and leader lines are reserved. When the last line is under three-quarters full, `engine/annotate.py` spreads the bars evenly over the same number of lines with encoded system breaks. It uses Verovio's `smart` break mode, because `line` mode drops the last line of a selected excerpt in Verovio 6.3. A staff with no clef gets a treble clef when the file is loaded.

**Result.** An automatic check compares every overlay label with Verovio's boxes and with the other labels. On the five pages, labels overlapping something fell from 4 to 0, and labels with less than half the required clear space fell from 2 to 1. Two labels are still flagged (one overlap with the Mozart "N", one tight "7→3" in Bach); both look clear when zoomed in, so these are the check's own false alarms. Pages with a near-empty last line fell from 3 to 0 (Mozart 3 + 3 + 2, Bach 5 + 4, Schubert 4 + 4). Tests pass (53).

### 23. Pages still looked busy: slurs through beams, broken ties, doubled chords (2026-10-10)

**Problem.** The owner found the pages unprofessional even after the fixes above. Slurs ran through beams, and Brahms bar 5 had a crushed hook. Brahms bar 3's crescendo and diminuendo sat at different heights. Pedal brackets looked like analysis brackets. Too many bracket rows stacked up, and colours were added to music where tonic and dominant roles are not the point. In Clair de lune bars 1–4, a flat line ran along the left hand, the opening chord had doubled ties, a stem crossed "con sordina", and a "p" sat on its hairpin. Two string quartets (Mozart K. 458, Beethoven Op. 59 No. 1) and two full scores (Mozart's "Jupiter", Dvořák's Largo, from the MIT-licensed MCTL dataset) were added to the check. An orchestral score with drums crashed the score reader.

**Cause.** Most of the clutter was in the files or in Verovio, not in our overlay:
- Verovio keeps each slur on the side the file gives it, even through a beam.
- Files give every dynamic and hairpin its own vertical group, so they are never aligned.
- A MuseScore tie with no end gets joined to the next note of that pitch, 12 bars later in Clair de lune.
- That file writes the opening chord on both staves to fake a cross-staff beam.
- The overlay never counted the staff lines as taken space, so a label could land between them (the Jupiter "APP").
- Unpitched notes have no pitch name.

**What we did.**
- `engine/slurs.py` lays the page out and finds slurs that touch a stem, beam or notehead. It flips them and lays the page out again, keeping a flip only where it helps. Slurs wider than a phrase mark are left alone.
- `engine/render.py` now does several things when it loads a file:
  - puts each staff's dynamics on one line;
  - stops a hairpin at a dynamic inside it;
  - drops pedal marks;
  - drops ties that run backwards or skip past the next bar;
  - silences a cross-staff copy of notes the other staff already plays, and shows the kept chord's stem;
  - spaces "espressivo (";
  - sets a wider margin between dynamics and notes;
  - trims empty space from the PNG.
- The overlay:
  - writes the key only when it changes;
  - treats staves as taken space;
  - draws a leader to any label that is not directly over, under or beside its circle.
- The skill now asks for function colours only when the T–PD–D cycle is the point, and for at most one bracket row.
- `tools/engraving_check.py` runs all nine passages.

**Result.**
- Colliding slurs in Brahms went from 5 to 0; the other pieces had none.
- Ties dropped across the nine scores: 3, all broken (Debussy bar 1 → 13, Schubert 45 → 47, and one more). A Brahms tie with a gap of an eighth note inside one bar is kept on purpose.
- Clair de lune bars 1–4 now have no doubled noteheads or stray lines.
- The automatic check flags 3 overlapping labels and 2 tight ones across the nine pages:
  - one is a real problem ("7→3" on a slur in Brahms bar 3);
  - the Jupiter "APP" now has its leader line;
  - the rest look clear when zoomed in.
- The robustness run passes 31 of 31, and 52 tests pass. The golden image is out of date until the new look is approved.

### 24. Slurs on the wrong side, and circles on scale runs (2026-10-10)

**Problem.** The owner compared our pages with printed editions and found several faults:
- Slurs in Debussy bars 1–2 hung below the notes.
- A slur in bar 3 crossed the duplet "2"s.
- The left-hand A♭s in bar 1 were not tied.
- "7→3" sat in a crowded spot.
- "Theme in the cello" was bracketed over the whole quartet.
- P and N were circled on ordinary scale notes in Mozart.
- Two Brahms "N"s were really anticipations.

Mutopia's engravings of the first editions (Fromont 1905, Simrock 1892) served as the reference.

**Cause.**
- Verovio picks a slur's side from the first note's stem, and the round 23 pass flipped colliding slurs to whichever side was clear. Neither follows engraving practice.
- The A♭ tie in the file points 12 bars ahead, and round 23 dropped it.
- Verovio's staff box takes in ledger lines, so the space under a staff with low notes counted as taken.
- The non-chord-tone circles in the example lists were picked by hand with no rule.
- A review by a side agent found that the round 23 duplicate-chord rule had removed 3 Brahms notes nobody had looked at. Their courtesy naturals and slurs went with them in bar 65.

**What we did.**
- `engine/slurs.py` now sets every slur's side by Gould's rules, judged from the stems as drawn:
  - two voices: the upper voice above, the lower voice below;
  - one voice: the notehead side when the stems agree, above when they are mixed.

  A slur that still hits a stem, beam, notehead or tuplet number is raised with MEI `@bulge` instead of being flipped.
- A broken tie is reconnected to the next note of its pitch on its staff.
- A removed cross-staff copy now passes its ties, slurs and written accidentals to the note that stays.
- The overlay measures a staff by its five lines and puts voice-leading labels under the arrow.
- `region` takes an optional `staff`. Hidden directions make Verovio open the gap above that staff.
- The skill now says to circle accented non-chord tones and the first instance of a characteristic figure, and never notes inside a run. It also says to check whether a note anticipates the next chord before calling it a neighbour.

**Result.**
- Debussy bars 1–5 and the Brahms two-note slurs now sit on the same sides as in the first editions, and the bar 3 slur clears the duplets.
- Brahms bar 65 keeps its naturals.
- The label check across the nine pages flags 1 overlap (the Jupiter "APP", which has a leader line and reads clearly) and 2 tight labels.
- 52 tests pass; the golden image is waiting for approval. The robustness run passes 31 of 31.

### 25. Checked against printed editions: the slur rule had never run (2026-10-10)

**Problem.** Nine reviewers each compared one Round 4 page with a printed edition. Where IMSLP was reachable they used scans: Breitkopf 1863 and 1878–82, Peters c. 1890, Eulenburg 1903, NMA. Otherwise they used Mutopia re-engravings of the first editions (Bach, Brahms, Debussy).

None found a wrong pitch or rhythm. Most of what differed came from the files themselves, which our engraving draws faithfully:
- missing dynamics, slurs and staccatos (K545, Schubert, K458);
- misspelt lyrics in Schubert;
- "Andante espressivo" in Debussy where the first edition has "Andante très expressif";
- wrong horn key signatures, a stray bass note and "muta" texts in the wrong bars in Dvořák.

The engraving faults were:
- Slurs sat on the wrong side in Schubert, Brahms, K458 and the Beethoven cello.
- Debussy bar 1 showed the A♭ twice, with a lens of ties, two rests and no cross-staff beam.
- Jupiter and Dvořák printed part ids ("flute1", "piccolotrumpet1").
- Jupiter printed its title and composer inside the music.
- Brahms joined its crescendo and diminuendo into one diamond and set "p" and "dolce" at different heights.
- Ties coming into the excerpt crossed the "C" time signature.

**Cause.**
- Verovio boxes notes, never noteheads, so the round 24 stem lookup found nothing. Every single-voice slur went above, and the lift check never saw a note. Round 24's Debussy and Brahms slurs were right by coincidence.
- The two-voice rule compared average pitches, so the upper voice's low chord notes pulled it under the inner voice.
- MEI `@bulge` turned out to be about one staff space per unit, not half, so lifted slurs overshot.
- In Debussy bar 1 the file writes the chord in both hands. The right hand's copy has its stem hidden, and the cross-staff copy carries the beam. Round 23 kept the wrong copy.
- Verovio does not import `<instrument-name>`, where such files keep the readable name.
- MuseScore pages write the title block as ordinary directions.

**What we did.**
- Slurs:
  - stem directions come from note boxes;
  - two voices are compared by their top notes;
  - notes drawn on another staff count on that staff;
  - the bulge unit is now one staff space.
- When the staff's own copy of a doubled chord has its stem hidden, it goes, with the rest under the beam. The cross-staff copy and its beam stay.
- Ties from notes struck together in different voices curve apart.
- Part names that look like ids are replaced by the instrument name, numbered: "Horn I in C".
- Text that names the piece or composer from the file's header, and "Movement N" headings, are removed.
- A hairpin that ends where the next starts stops half a beat short.
- A word just after a dynamic joins it ("p dolce").
- Ties into the excerpt from an earlier bar are dropped.
- Words that a stem runs through move to the other side of their staff.

**Result.**
- Slurs now match the editions in the four flagged places, and Brahms bars 6–8 arch above.
- Debussy bar 1 has its cross-staff beam, one rest, and "con sordina" under the left hand as in Fromont.
- The label check flags 1 overlap and 2 tight labels, as before.
- 52 tests pass; the golden image still waits for approval. Robustness passes 31 of 31.
- Still from the files: Dvořák's second-system abbreviations ("Cl. I. II." over "Cl."), and Jupiter's empty horn III–IV staves.
- Verovio's Leipzig "tr" is heavier than a printed one; Leland's is plain, but changing the music font changes every page.
- "div." and "a 2" in Dvořák are attached to the right staff but sit midway between staves.

### 26. Owner's look at Round 5: inner-voice slurs, a cramped chord slur, a small note (2026-10-10)

**Problem.**
- In Brahms bars 1 and 5, the slurs inside the cross-staff beam sat below. The Simrock first edition (1893) puts both above.
- In Debussy bar 1, the slur from the A♭ chord to the F was squeezed against the chord.
- In the Beethoven quartet bar 1, the cello's D was drawn small.
- A side review noted that dropping ties into an excerpt makes a held note look like a new attack.

**Cause.**
- The two-voice rule treated the beam that crosses the staves as a lower voice.
- MusicXML puts a chord's slur on its first, lowest note. A slur set above the chord therefore started from inside it, and `@bulge` barely raises a short slur.
- The music21 file marks that D `<type size="cue">`. The Breitkopf 1863 score prints it full size.

**What we did.**
- Slurs between notes of one cross-staff beam go above.
- A slur on one note of a chord is moved to the chord. Verovio then starts it from the outer note on its side.
- A slur that is still blocked after it has been lifted is raised a step further, up to four passes. Ties now count as obstacles.
- Any group of two or more ties starting together curves apart, including cross-staff notes.
- Ties into an excerpt are kept again, as the owner chose. Verovio draws them from the time signature, so the arc seemed to grow out of the "C". Each is now redrawn as a short arc, at most two staff spaces long, starting clear of the time signature and ending on the held note. Such ties are drawn as "spanning" groups named by class rather than id, which is why a first attempt to find them by id missed them all.
- The cue-size note stays as written, as the owner chose. The trill keeps Verovio's default font.

**Result (v16, ties in v17).**
- Brahms bars 1 and 5 match Simrock.
- Debussy's slur clears the chord.
- The label check finds 1 overlap and 2 tight labels, as before.
- 52 tests pass, with the golden image deselected. Robustness passes 31 of 31.

### 27. Making the finished page look printed: fonts, PDF, empty staves, line breaks (2026-10-10)

**Problem.**
- The card image was 1400 px wide, soft on high-density screens, and the PDF was a raster image inside a PDF.
- Instrument names with a ♭ ("Clarinet in B♭") came out in a different typeface from the rest, so the names looked uneven.
- A test on 27 more ensembles (concertos, sonatas, band, choir, hymns, lead sheets, guitar, organ, continuo, opera, four hands, two pianos, drums, big band) showed:
  - labels in some files read "B accidentalFlat" or "&amp;";
  - two identical marks were printed on top of each other;
  - "p" and "cresc." at one point were drawn apart;
  - dynamics a beat apart were forced onto one line and touched;
  - a clef was immediately cancelled by another clef.
- Orchestral pages printed every resting staff on every line. Printed scores show all staves on the first system only.
- Lines broke wherever the bars filled up, sometimes in the middle of a phrase, and could leave one or two bars alone on the last line.
- The label check only looked at our own labels. Nothing checked the music's own text against the notes.

**Cause.**
- resvg sets a whole string in the fallback font when one glyph is missing. Liberation Serif has ♯ but not ♭ or ♮.
- The PDF was made from the PNG.
- The label and mark problems are in the files. Verovio prints what it is given.
- Verovio hides empty staves only when asked (`condense`), and its "auto" setting starts on page 2.
- Verovio's breaks know nothing about phrases.

**What we did.**
- **Fonts.** tools/build_fonts.py builds Score Serif: Liberation Serif plus DejaVu's ♭ and ♮. It is renamed because the OFL reserves "Liberation". fonts.conf points Times and serif at it.
- **Image quality.**
  - The card image is drawn at 2800 px, twice the old width.
  - The PDF is now vector, built per page with cairosvg and joined with pikepdf. The base image needs libcairo2. cairo is loaded only when a PDF is made, and where it can't load (a skill sandbox without the library, or a base image not yet rebuilt) the PDF falls back to an image PDF at A4 width, so analyses never fail because of it.
- **File cleanup.**
  - Labels are cleaned.
  - Exact duplicate marks are dropped.
  - A dynamic and a word at the same point on the same staff are joined ("p cresc.").
  - A dynamic less than a beat after the one before it on its staff is no longer forced into line with it.
  - A clef cancelled by the next clef is removed.
  - In chord symbols, a "b" or "#" before a number becomes ♭ or ♯ ("Am7b5" → "Am7♭5"). Verovio converts only the root.
  - A clef change written before a bar's first note moves to the end of the bar before. Verovio draws such a clef full size after the barline; print sets it small before it (Beethoven trio, cello, bar 3). A first try made it a staff change between the bars, but Verovio draws that full size too.
- **System divider.** As the owner chose, the "//" between systems is drawn only on scores with more than four staves (orchestra, band, quintets, choir with piano). Solo piano, songs, duos, trios and string quartets leave it out, as their editions do.
- **Empty staves.** `condense: "encoded"` with `optimize` on the first score definition: the first system names every instrument, and later systems drop resting staves.
- **Line breaks.**
  - Bars are measured at natural width on one line.
  - Line capacity comes from Verovio's fullest line.
  - A short dynamic-programming pass chooses breaks that fill lines evenly. It prefers breaks at phrase starts and after cadences, avoids breaking just before a cadence, and keeps the last line at least three-quarters full.
- **Music collision check.** tools/engraving_check.py now also boxes Verovio's own text (dynamics, words, tempo, lyrics, fingering) and clef changes, and reports any that overlap notes, accidentals, rests or other text by more than a tenth of a staff space. Bar numbers are skipped, because their boxes come out unplaced. Lyrics have no boxes in Verovio 6.3, so they can't be checked.

**Result (v21).**
- Line breaks:
  - K. 545 now breaks at bar 5, where phrase b starts; before, it broke inside phrase a.
  - Bach, Schubert and Debussy break at phrase starts.
  - Dvořák breaks before bar 10, inside phrase a. Breaking after its cadence would need six orchestral bars on one line, 19% over capacity, so the full first line was kept rather than going to three systems.
- Condensing: on the Dvořák page, the second system shows 7 staves instead of 25.
- The PDF matches the PNG, and instrument names now share one typeface.
- The label check finds 1 overlap and 2 tight labels, as before. The music collision check finds 0 collisions on the 9 pieces.
- Two reviewers checked 15 of the ensemble pages. IMSLP's downloads sit behind a bot check, so they compared against general practice (Gould), not printed editions. I checked their claims against the files:
  - Ours and fixed: the full-size cello clef in the trio, and "Am7b5".
  - From the files, not ours: no figured-bass figures in the Bach teaching sheet (it has none; the trombone sonata's 47 figures print correctly), missing hyphens in the Lacrymosa (the file ends the word after "cry"), no instrument groups in the band score, and two identical bass staves in the Bach sonatas.
  - Not right: the organ "garbled ornaments" are ordinary mordents, and the "//" no longer touches the bar number.
  - Still open: a resting staff with a clef change at its end stays on the page (Grieg, Piano II). Hiding it would need the clef moved to the next line, which Verovio draws full size. Very long text directions (the Bach teaching sheet) run off the page.
- Ensembles: 26 of 27 have no music collisions. Autumn Leaves keeps one chord-symbol clash that is in the file. No log of the first ensemble run was kept, so there is no before count.
- 52 tests pass, with the golden image deselected. Robustness passes 31 of 31.

### 28. Piano reductions of large scores (2026-10-10)

**Problem.** A full orchestral page is hard to read for most users. Published reductions (Goetschius's 1928 "Analytic Symphony Series") put the same music on two staves. The owner wants users to be able to ask for one.

**Decisions (owner).**
- The analysis is made on the original score. The reduction is only a clearer view of it.
- Instrument cues use standard abbreviations (Fl., Ob., Cor. ingl., Vl. I, Str., Tutti).
- For scores with more than four staves, the original is drawn first and the piano version is offered once. It is drawn only if the user accepts.
- It runs in the skill and on the server. The server cost was measured before any deploy.

**What we did.**
- `engine/piano.py` builds on the second prototype:
  - Melody: the busiest line that stands out (the top line, or another instrument family than the accompaniment) is the tune and goes on top.
  - Harmony: everything else is merged into chords and split between the hands. Harmony above the tune moves down an octave. Each hand keeps at most four notes, dropping doublings first.
  - Held chords: a chord held unchanged becomes one long note. Any change of notes strikes a new chord, so no harmony is lost.
  - Cues: a cue appears where the tune changes hands.
- Instrument families come from music21's instrument classes. Strings often arrive as a generic "StringInstrument", so the part name is looked up instead.
- Notes the analysis points at (non-chord tones, voice-leading arrows) are added to the chord material unless the tune already has them, so they are never dropped, thinned or moved. Their marks are then re-pointed to whichever piano staff they land on. A first version added them only where a chord already started, and lost a marked note a sixteenth after the beat (K. 458 bar 5).
- The time and key signatures are read from the first bar. music21's context search finds neither in a bar cut out of the score, so K. 458 first came out with no key signature and quarter-note beats.
- `render(..., piano=True)`, the skill's `--piano` and the server's `piano` argument all use the same path. music21 is imported only for a reduction, so the skill installs it only when a user accepts.

**Result.**
- Jupiter (bars 1–8) and Dvořák (bars 5–12) draw on two staves with all their labels.
- K. 458 keeps its marked neighbour note.
- 54 tests pass, including a new end-to-end test.
- Cost, measured on the development machine:

  | Page | Original | Piano version |
  |---|---|---|
  | Jupiter | 15.2 s CPU | 12.4 s CPU |
  | Dvořák | 9.9 s CPU | 5.5 s CPU |

  Loading music21 adds 0.1 s and 31 MB once per instance. A piano page therefore costs no more than the original page it follows. At the current Cloud Run settings (2 vCPU, 4 GiB) that is about $0.0007 per piano page beyond the free tier, and it counts toward the existing daily render cap.

**Still rough.** Dense inner voices in chamber music (K. 458 bars 5 and 8) turn into tied chord chains. The offer is only for scores with more than four staves, where the textures are fuller and the reduction reads well.

### 29. Deploy of the vector PDF and piano reduction (2026-10-10)

**What was deployed.** `d39c7bb` (logs 23–28: engraving rounds, vector PDF via cairosvg, piano reduction) with `server/deploy.sh`, as revision `sheet-music-analysis-00018-s45`, serving 100% of traffic. Settings unchanged: gen2, 2 vCPU, 4 GiB, concurrency 4, min 0, max 1 instance, 300 s timeout, daily caps in `server/app.py`.

**Base image.** Rebuilt, because `Dockerfile.base` (libcairo2) and the package lists changed: new tag `base:734c41625b5daadb`. Cloud Build: base 6 min 18 s, server 51 s, about 7 build-minutes in all. The old base (`base:d54605c0043b3114`) is still tagged, so the untagged-cleanup policy keeps it; the repository holds 1.3 GB.

**Result.** The new instance started in 7 s with no warnings or import errors in its log. One `render_analysis` call through mcp.sheetmusicanalysis.com (Chopin Op. 9 No. 2, bars 1–8, the score placed in the bucket under a score id) returned in 9.6 s. Its PDF is 95 KB, one page with seven embedded fonts and no images, so it is the vector PDF, not the image fallback. The piano option was not tried on the live server.

### 30. Usage report and a logging redeploy (2026-10-11)

**Problem.** No usage numbers existed, so the order of the next features had nothing to rest on. Both directory listings (Claude and ChatGPT) were submitted and are in review as of today.

**What we did.** `tools/usage_report.py` reads the server's existing Cloud Logging lines (no new cloud cost) and prints drafts, renders, piano renders, views, bar ranges, limit hits and errors per day and per platform. The deployed log lines lacked the view and the bar range, so `render_analysis` now logs `view` and `measure_range`, and `draft_analysis` logs `measure_range`. Deployed as revision `sheet-music-analysis-00019-7n7`; base image `base:734c41625b5daadb` reused, server layer only (Cloud Build 1 min 14 s). Settings unchanged: gen2, 2 vCPU, 4 GiB, concurrency 4, min 0, max 1, 300 s.

**Result.** Before: 14 days of logs showed only launch-day testing (2026-10-06: 30 drafts, 19 renders, 5 errors, which looks like our own launch testing) and no view or range. After: one live `render_analysis` check (Chopin Op. 9 No. 2, bars 1–8, harmony) returned in 11.4 s and the report shows `views [harmony 1]  ranges [1-8 x1]`. The new `measure_range` on `draft_analysis` was not checked live, since that call runs the model.

### 31. PDF reading spike: homr against Audiveris (2026-10-11)

**Problem.** Most people have a PDF, not MusicXML. Before designing a PDF path we needed to know whether optical music recognition (OMR) reads clean PDFs well enough, and which tool to use. Details, scripts and per-file tables are in `spike/omr/RESULTS.md`.

**What we did.** Ground truth: `bach-269.mxl`, `mozart-k545-1.mxl` (73 bars), `chopin-prelude-4.mxl`. Clean PDFs made three ways: our Verovio engine (round 1, too clean to be representative), MuseScore 4.7.4 and Mutopia LilyPond editions (round 2). Scans: archive.org (Peters Mozart, Schirmer Chopin); IMSLP serves a captcha to scripts, which we did not get around. Each output was compared with ground truth on pitch, rhythm, key and meter per bar, and loaded with the engine's `ScoreIndex`. Everything ran locally on CPU, no cloud cost.

**Result.** Pitch agreement on the five MuseScore and Mutopia PDFs: homr mean 97.3% (89.9–100), Audiveris mean 96.9% (91.2–99.6). Key and meter 100% for both on clean PDFs; rhythm 94–100%. Neither tool clears 95% on every clean file. Scans are worse: 84.8–97.3% pitch, and homr read the Mozart scan's meter right in only 39.7% of bars. Speed 6–19 s a page and 0.8–1.5 GB peak RAM for both. homr crashed Verovio (a native segfault, not catchable in Python) on 7 of 27 page files and writes one file per page; Audiveris never crashed, writes one file per PDF, but loses a page holding a single bar ("No system found"; re-exporting the saved `.omr` recovers the other pages). Install: homr 545 MB environment plus 157 MB models; Audiveris 188 MB with its own Java runtime. The confirm-the-score step is needed with either tool.

**Owner's decision (2026-10-11).** Audiveris. Scans are accepted too, with a plain warning that reading errors are likely and the check step matters.

### 32. Where PDF reading runs, and what it costs (2026-10-11)

**Problem.** Claude connectors cannot receive attachments, so in Claude the PDF is only in the sandbox; in ChatGPT the server gets the file. Reading a PDF had to run somewhere without adding a workaround step for the user or breaking the $5 monthly budget. Details in `spike/omr/step2/RESULTS.md`.

**What we did.** Server: Audiveris 5.11.0 timed on this machine limited to 2 CPUs and a 1 GB Java heap, like the Cloud Run instance (Docker was not available, so the image size and memory limit were not measured). Claude: a probe script run in a real claude.ai chat downloaded, unpacked and ran Audiveris on a 1-page PDF, and checked which domains the sandbox can reach.

**Result.** Server: 7.4–13.9 s a page, 1.07–1.33 GB peak, about $0.00055 a page beyond the free tier (Cloud Run $0.000058 per instance-second at 2 vCPU and 4 GiB). Sandbox: download 1.9 s, unpack 0.7 s, the page in 23.9 s at 784 MB peak; Java is already installed; our own domains are blocked (403), so pages cannot be sent from the sandbox to the server. Decision: Claude reads PDFs in the sandbox at no Cloud cost; ChatGPT reads them on the server. **Owner's decision:** a daily cap of 150 PDF pages (a PDF counts its pages; over 12 pages refused). Worst case with every cap hit every day, about $4.45 a month (assumes the server itself stays under 0.8 GB and a $0.50 reserve, both unmeasured). To keep real cost near zero: read pages only until the asked-for bars are reached, and keep a result per file so the same PDF is not read twice.

### 33. Reading PDFs, first version: the check step in both hosts (2026-10-11)

**Problem.** Phase 2 steps 4–5: read a PDF with Audiveris, engrave what was read, ask the user to check it, and analyse only on their go-ahead, in Claude (sandbox) and ChatGPT (server).

**What we did.** `engine/read_pdf.py` runs Audiveris, re-exports the saved `.omr` when a page with no staves stops the export, and reports pages, skipped pages and whether the PDF is a scan (rule: no page paints a vector path; text is ignored because scans often carry an invisible OCR layer). Server tool `read_pdf` (ChatGPT only): 12-page limit, `pdf_page` cap of 150 a day counted per page, one read at a time with a "busy" reply, results kept by the file's SHA-256 under `scores/` (deleted after a day with the scores); returns a score id that `draft_analysis` accepts. Skill script `skill/scripts/read_pdf.py` downloads the Ubuntu 24.04 `.deb` into the temp folder on first use. Two things found that the spike missed: Audiveris asks GTK for the screen scale at startup and crashes where GTK is absent (the slim server image) unless `-Dsun.java2d.uiScale=1` is set, and it refuses to start under the engine's `FONTCONFIG_FILE`; both are handled in the module, so the image needs no X, GTK or sound packages. Its launcher sets an 8 GB heap; `_JAVA_OPTIONS=-Xmx1g` caps it (Mozart scan, 4 pages: 34.5 s, 1.24 GB peak, unchanged result).

**Result.** Local server, through the MCP endpoint: Mutopia Chopin (1 page) 20.4 s; Mozart scan (4 pages) 36.4 s with the scan warning; Verovio Chopin with a 1-bar last page 15.2 s, page 2 reported skipped; same PDF again 1.4 s from the cache; a second read during a read got "busy"; 15 pages refused; cap refused a 5-page read at 148 of 150. A read score id went on to `draft_analysis` (5.8 s). Skill script: 16.7 s for the Chopin page including the first download and unpack, 35.4 s and 1.17 GB peak for the Mozart scan. Not run: the Docker image build (no Docker here), and the real claude.ai and ChatGPT chats.

**What the spike missed (found by the owner on the first demo page).** The engraved Chopin prelude had almost none of its left-hand chords, and from bar 4 the right hand was drawn an octave low. The MusicXML was fine (599 of 606 notes); our Verovio import was not. The spike's `compare.py` counted notes in the raw MusicXML and never what the engine sees, so it scored this file 98.7%. Three Audiveris habits were at fault, all fixed by `clean()` in `engine/read_pdf.py` before the score leaves the module:
- `<beam>` repeated on every `<chord/>` note: Verovio drops the chord ("Chord starting point has not been found"). Removed from chord notes.
- Octave lines started and never stopped: Verovio draws the rest of the piece an octave off (pitches were right). Unclosed ones are dropped; closed ones are kept.
- `<divisions>` changing partway through a part (12, then 8, then 24 in the MuseScore Mozart): Verovio keeps the first value but writes later durations in the new units, so every onset after the change was off by a factor (2/3 in Mozart bar 17 on). Durations are rescaled to one value per part.

`spike/omr/engine_check.py` now compares through `load_toolkit` + `ScoreIndex` (pitch and onset per bar, the events the analysis uses). Notes the engine sees / truth, pitch agreement, pitch+onset agreement, before → after:

| OMR output | Before | After |
|---|---|---|
| MuseScore Bach | 228/229, 99.6%, 79.9% | 228/229, 99.6%, 98.7% |
| MuseScore Mozart | 1183/1281, 88.4%, 30.6% | 1246/1281, 91.0%, 86.5% |
| MuseScore Chopin | 120/606, 19.8%, 15.3% | 598/606, 98.7%, 98.0% |
| Mutopia Chopin | 121/606, 19.8%, 19.1%; 87 notes drawn an octave off | 599/606, 98.7%, 98.0%; 0 |
| Mutopia Mozart | 1203/1281, 91.6%, 47.8% | 1266/1281, 96.5%, 93.4% |
| Mozart scan | 1172/1281, 81.1%, 59.9% | 1235/1281, 84.8%, 78.3% |
| Chopin scan | 120/606, 18.8%, 18.0% | 596/606, 95.5%, 94.2% |
| Verovio Bach (round 1) | 228/229, 97.8%, 96.5% | unchanged |
| Verovio Mozart (round 1) | 1203/1281, 92.2%, 71.9% | 1266/1281, 97.1%, 93.7% |
| Verovio Chopin, page 1 only (round 1) | 120/606, 19.8%, 18.0% | 597/606, 97.5%, 91.6% |

After the clean-up every file keeps all its MusicXML notes except the MuseScore Mozart (15 fewer: in bars 59, 60 and 62 Audiveris wrote the same five notes twice, and Verovio drops the copies). The only Verovio messages left are unmatched slurs. The Mozart scan's remaining onset gap is OMR, not import: a missed treble clef in the left hand of bars 1–4 and 42–44 puts those notes a twelfth low. `tests/test_read_pdf.py` now engraves nocturne bars 9–12, where the old import lost 29 of 137 notes, and checks the notes and left-hand chords ScoreIndex sees; with the clean-up disabled it fails (108 against 137).

**Every bar on the check page (owner, 2026-10-11).** The ChatGPT card showed only page 1 of the engraving. It now shows one tall image of the whole score (`engrave_tall` in `engine/render.py`; Mozart scan, 73 bars: 2800 x 13,214 px in the card, staff space 24 px, so about 6.5 CSS px at a 760 px chat column, the same scale as the analysis card); the PDF link keeps ordinary pages. The skill keeps one PNG per page but pulls a last page of one or two bars onto the page before it (Chopin prelude: 2 pages, the second holding bar 25 alone, became 1).

**Naming likely misreads, and leaving out slurs (owner, 2026-10-11).** The owner found misreads in the Chopin that the page did not point to (a turn read as a double sharp in bar 16, lost triplets in bars 12 and 18) and wrong extra slurs. `problem_spots` in `engine/read_pdf.py` now names bars that don't add up and notes with double sharps or flats, and the message lists them (first four, then a count). A bar is named when a voice runs past the meter or a short voice runs on into the place where another voice of the same staff starts after a hidden gap; a voice that merely stops early is not, since that is nearly always a left-out rest (a plain per-voice rule flagged 11 correct bars in the Mutopia Mozart). Short bars are allowed as the opening pickup, a last bar completing it, or two halves of a split bar. Checked against ground truth on eight readings: Chopin (Mutopia, MuseScore) bars 12 and 18 plus the bar 16 double sharp, nothing else; Bach 2 and 9, both wrong; Mozart (Verovio) 8 bars, all wrong; Mozart scan 12 bars, all wrong (31 more wrong bars are not caught, mostly the misread clef); Chopin scan 4, all wrong; Mutopia Mozart 6, one of them (67) actually right. Slurs are removed from every reading unless the user asks (`keep_slurs`, `--keep-slurs`); the cached reading keeps them, so asking costs no second read (server 2.6 s, skill 0.9 s).

### 34. A PDF crashed the live server (2026-10-11)

**Problem.** In the first ChatGPT test of PDF reading, ChatGPT still held the app's old tool list (it called `choose_score`, which no longer exists, and did not know `read_pdf`), so it passed the PDF to an analysis tool as the score. Verovio, given bytes that were not MusicXML, guessed the format (Plaine & Easie), segfaulted and killed the container twice ("Container terminated on signal 11", two 503s). Any wrong file type could have taken the server down for every user.

**What we did.** `load_toolkit` now refuses anything that is not MusicXML (no `<score-partwise>` or `<score-timewise>` near the start, or not a compressed .mxl) before Verovio sees it, and `resolve_score` tells the model to call `read_pdf` when it is given a PDF. Deployed as revision `sheet-music-analysis-00023-bmn`; settings unchanged.

**Result.** Before: a PDF sent to `draft_analysis` crashed the instance. After: the same call returns "This file is a PDF. Call read_pdf with it first, then use the score_id it returns." in 0.9 s, with no crash in the logs. All 31 robustness scores and 56 tests still pass. The owner has to refresh the app in ChatGPT for it to see `read_pdf`.

### 35. Why PDF reading loses notes: a benchmark, and retraining ruled out (2026-10-11)

**Problem.** The owner found the Chopin Prelude Op. 28 No. 4 triplets (bars 12 and 18) still read as plain eighths. Audiveris's "implicit tuplets" switch and reading at 400 or 500 DPI changed nothing. The owner asked for reading "as accurate as possible", including retraining Audiveris ourselves.

**What we did.**
- **Benchmark** (`spike/omr/bench/`): 23 public-domain pieces with known MusicXML, engraved by MuseScore 4, LilyPond and Verovio, plus synthetic and real scans: 57 PDFs, 159 pages. It scores what the engine sees (after `clean`), by kind of mistake. Audiveris gives identical results on repeat runs, so differences between settings are real.
- **Retraining pilot** (`spike/omr/train/`): Verovio pages with exact symbol boxes, matched to Audiveris's glyphs, and a headless trainer for its classifier (`BasicClassifier`). It raised held-out symbol accuracy on Verovio pages from 95.7% to 99.5%. On the Chopin it added no triplets, and symbols absent from training got worse, because training resets the feature scaling from the new samples only.
- **The Chopin "3" was never a recognition problem.** The shipped classifier labels it TUPLET_THREE at 0.95. `TupletsBuilder` then takes every note on the same beam as the triplet (five notes: two eighths and the triplet) and rejects it as too many.
- **Where the lost notes go** (`spike/omr/bench/analysis/`). The pipeline loses 22% of notes by pitch and timing together:
  - missing note heads: 5.1%, mostly second-voice rests discarded by `RestInter` as too close to a note, after which later notes are mistimed or dropped;
  - crashes and skipped pages: 4.1%, two Audiveris null-pointer bugs triggered by Verovio layouts;
  - triplets: 4.5%, signs rejected or invented, and ratios like 5:4 that Audiveris cannot represent;
  - other timing (voices, dots, grace notes): 3.6%;
  - pitch: 2.8%, mostly missed mid-staff clef changes;
  - lost bars: 1.1%, a crash when a hairpin is exported.

**Result.**

| | Notes, right pitch | Notes, right pitch and timing |
|---|---|---|
| Audiveris as shipped | 86.6% | 78.3% |
| Small heads switch on (grace notes 2 → 264 of 451) | 85.1% | 76.4% |
| Small heads + implicit tuplets | 88.0% | 77.2% |
| Per PDF, keep whichever of the three has fewest bars that don't add up | 87.3% | 80.6% |
| Tuplet beam patch (tuplet notes found 838 → 964, invented 190 → 245) | 86.6% | 78.3% |
| Rest rule off (`RestInter.minInterChordDx=0`; Bach BWV 846 MuseScore 11% → 45%) | 86.9% | 78.8% |
| Combined: crash fixes (Codex: null guards in `PartwiseBuilder`, `Voices`, `SlurInter`), rest rule, tuplet patch with a bracket/centring guard (838 → 969 found, 190 → 221 invented) | 91.2% | 82.0% |
| Combined, best of three readings (default, small heads, + implicit tuplets) by fewest uneven bars; extra readings only when the first has more than 3 uneven bars (2.35 readings per page) | 91.4% | 84.3% |

Each switch or patch helps some pieces and hurts others; the gain comes from fixing crashes and from choosing between readings per PDF. Retraining the classifier is dropped, because it does not touch the causes. A Codex review of the scoring found only negligible effects on these totals (ornament counts credit any ornament in the bar, so they are rough). Its review of the patch found two holes in the tuplet guard (bracket span measured too wide; beam ink can count as bracket) and two crash risks; all four were fixed, with no change on the benchmark. The guard's thresholds were tuned on this benchmark, so the patch was also checked on 8 held-out OpenScore songs (11 PDFs), one reading each: right pitch 92.6% → 94.5%, right pitch and timing 70.2% → 75.7%, tuplet notes found 6,685 → 7,547 of 9,982 (invented 13 → 4), no PDF worse.

The patch is published as release `5.11.0-sma.1` of https://github.com/Vedat-Ozkan/audiveris (branch `sma-5.11.0`, AGPL-3.0): `audiveris.jar` replaces the one in the official 5.11.0 package, checksum-pinned in `Dockerfile.base` and `skill/scripts/read_pdf.py`. Cached readings are keyed by `READER`, so readings from before are not reused.

Time and memory on 2 CPUs (the Cloud Run size), measured locally: one reading takes about 9 s a page; a 6-page PDF that needs the two extra readings takes 92 s, an 11-page one 167 s (inside the 240 s budget), and the two parallel readings peak at 1.7 GB together.

**Triplets printed without a "3" (later the same day).** Audiveris finds no triplet when the "3" is left out, the common case in songs. `engine/triplets.py` repairs a voice after reading: when it runs past the bar, or runs into another voice of its staff that starts after a hidden gap, by exactly what turning whole beamed groups of three into triplets would save, each group starting on its own beat or sub-beat, with a printed triplet of the same kind within three bars. Each guard was measured by relaxing it alone; cutting threes out of longer beams and widening the three-bar window cost 8 to 67 wrong notes on the main set for 4 gained, so Chopin Op. 28 No. 4 bar 18 (five eighths under one beam, the last three a triplet) stays unrepaired; the check message names it. A beamed quarter (a misreading) made the repair loop forever; fixed before release. Rejected the same day: a patch to keep the notes Audiveris drops when a bar's rhythm does not add up (`MeasureRhythm`): pitch 91.4% → 93.6% but pitch and timing 84.3% → 83.5% and uneven bars 362 → 426 on the main set; Hensel lost 35 points.

Final, production code on the released build, right pitch / right pitch and timing (each set's notes in brackets):

| Set | Before the triplet repair | After |
|---|---|---|
| Main, 57 PDFs (41,371) | 91.4% / 84.3% | 91.4% / 84.5% |
| Held-out, 11 PDFs (12,942) | 97.4% / 88.1% | 97.4% / 90.2% |
| Held-out 2, 6 songs read after the rules were frozen (4,222) | 94.1% / 80.6% | 94.1% / 81.0% |
| Held-out 3, 6 songs full of unprinted triplets, read after the rules were frozen (5,886) | 89.3% / 63.5% | 89.3% / 66.0% |

From the start of this work (the released Audiveris, one reading): main 86.6% / 78.3% → 91.4% / 84.5%; held-out 92.6% / 70.2% → 97.4% / 90.2%.

**Faster benchmark.** `spike/omr/bench/run.py` now caches only Audiveris's own output, per PDF and settings; everything after it runs from the current code. All four sets (80 PDFs) rescore in 41 s instead of a full read (about 25 minutes with 6 readings at a time).

**Deployed** 2026-10-12 from a clean checkout of commit 5027d39 (without the Phase 4 changes): revision `sheet-music-analysis-00024-cgv`, base image `base:5efd7a5f78c06fd5` rebuilt in 6 min 37 s (the patched jar's checksum passed), server layer 1 min 3 s; settings unchanged (gen2, 2 vCPU, 4 GiB, concurrency 4, max 1, 300 s), PDF cap 150 pages a day. Checked on the live server with the Chopin PDF: bar 12's triplet is read, bar 18 and the bar 16 double sharp are named in the message; the same PDF again took 6.9 s (cached reading).

### 36. Engine work for later phases, written and cross-reviewed by Codex (2026-10-11)

**Problem.** Phase 2 waits on owner decisions (the check step's look and wording), on cost numbers and on the open directory reviews. The owner allowed later phases' engine work to start early in Codex (OpenAI's coding agent, run with `codex exec`), to be corrected later, with no display, site or deploy work ahead of their decisions.

**What we did.** Each module was written by one Codex session, reviewed by a fresh one that had to prove every bug with a small counter-example, then fixed, with each counter-example kept as a test:
- `engine/correct.py`: fix misread bars of a PDF reading from the notes text form (the "correct a bar in the chat" step).
- `engine/part_writing.py`: voice-leading checks for chorale textures (Phase 4).
- `engine/check_analysis.py` and `engine/comparison.py`: read a student's numerals, typed or in a MusicXML, and classify each difference from our analysis (Phase 3). `comparison.py` moved out of `eval/compare.py`, and all 13 reference pieces score exactly as before.
- `engine/notation.py`: ABRSM and figured-bass label text (Phase 5).
- `engine/export.py`: the numerals written into the user's MusicXML as bass lyrics (Phase 6). The spike in `spike/export/` found MuseScore 4.7 keeps all 22 labels as lyrics, while its `<harmony><numeral>` import turned ii65 into ii76. Dorico was not tested.

**Result.**
- **Reviews:** they found 13 real bugs (7 in the music-theory modules, 6 in correction and export, counting suspected ones that proved real). All were fixed.
- **Bar fixer:** taking out any bar and putting it back unchanged changes nothing, across 185 bars of 5 real scores, including split bars, 8va spans and grace notes.
- **Voice-leading checks:** all 17 planted errors in two exercises were found, with no extras. The 7 hits in three Bach chorales are classroom exceptions Bach wrote, not mistakes.
- **Tests:** 248 pass.
- **Not yet wired in:** none of this is in the skill or server. Displays, the ABRSM spellings, voice ranges and the framing text wait for the owner.

### 37. The voice-leading report offered in the chat (Phase 4, 2026-10-11)

**Owner's decisions.** The report is offered, then shown on request: for a chorale-style score (`part_writing.applies`) the model says in one line that it can check the voice leading, and draws nothing unless the user says yes or asked. Ranges are Open Music Theory's (soprano C4–G5, alto G3–D5, tenor C3–G4, bass F2–D4), named in the range finding. A stricter "exam" range set was considered and dropped: no official table to cite, and it flags notes many teachers accept.

**What we did.** Both draft paths (`draft_analysis` and `draft_from_notes`) add a PART-WRITING CHECK section when the texture applies, with the draft's chords passed to the checker. Findings at the same place share one numbered spot (one callout, every finding explained in its paragraph), and each arrow carries a short label ("P5", "P8", "direct 5"): the first example page stacked three callouts on bar 1 with nothing tying a number to a pair of voices. Existing marks only. A piano piece gets no section.

**Not yet live.** Committed separately from the PDF work and not deployed: the pages go to the owner first.

### 38. A night of Codex work on later phases, checked by Claude (2026-10-12)

Six tracks ran overnight in Codex, each built, reviewed twice by a fresh Codex and fixed twice. Usage ran out at 02:04; the runner read the reset time (06:40), waited and resumed, and all six finished by 07:19.

**Merged after Claude's check** (all 422 tests pass on the merged result):
- **Corrected bars (Phase 2):** replaced bars get proper beams, triplets included, and `review_correction` returns only the changed bars, drawn alone, with a plain note ("Bar 18: three eighth notes are now a triplet."). Chopin bar 18 matches the PDF's rhythm; the bass beams 4 eighths together where Chopin beams 2+2.
- **Export (Phase 6):** labels stay on their reviewed beat instead of moving to the next note. MuseScore 4.7.5 round trip keeps 128/128 labels on 10 scores (126/128 before).
- **Check my analysis (Phase 3):** more typed forms (Unicode figures, ø, spaced slashes, augmented-sixth names); ambiguous input asks a question. MuseScore's Roman-numeral export reads all 12 labels, but MuseScore itself loses 5 meanings (ii65 to ii, V7/V to V, It+6 to I6).
- **PDF warnings (Phase 2):** two new signals, durations that disagree with their note value and backups before the bar. On the 80 benchmark readings: 8 more wrong bars named, no new false warnings (main set recall 41.1% to 41.9%). Clef/key changes, density, short voices and range signals were tried and dropped: each lowered precision. The new signals do not change which reading is chosen (the first version did, and cost the Haydn canzonet 31 correct notes).

**Sent back, then merged after a third round:**
- **Voice-leading check:** the Bach audit (330 chorales) removed false unresolved-seventh and doubled-leading-tone reports, 13 of 88 sampled being checker bugs. The last overnight round, unreviewed, added 22 leading-tone reports, most of them III to VI motions in the home key where the note is not a leading tone. Sent back: a local dominant now needs evidence of its key. Against the reviewed round, exactly 3 leading-tone reports are added (BWV336, 245.40 and 64.4, all real V–I with the soprano leading tone leaping) and none removed. Reports 2582 to 2296 overall.
- **Numeral styles (Phase 5):** ABRSM and figured bass render with no collisions and the default page is byte-identical. ABRSM set "V7b/vi" with a plain 7 beside raised ones; fixed. The styles still wait for the owner's look before they are offered.

All 436 tests pass on main with every track merged.

### 39. Check my analysis: the plumbing (Phase 3, 2026-10-12)

`draft_analysis` and `draft_from_notes` take an optional `student_analysis`. Typed numerals are parsed before the daily limit is charged, so an unclear answer comes back as the parser's question at no cost. The draft gains a STUDENT CHECK section: each of the student's labels beside the draft's chord (confidence, runner-up, bass, pitch classes) and how they compare, with guidance to act as a second reader. Numerals written into the score file are read only when the argument is the word `score`: a published edition carries its own numerals, so reading them unasked would pass them off as the user's answer. In Claude, `skill/scripts/model_notes.py --student-analysis` validates the answer, prints the question if one is needed, and otherwise prints the answer in normalized typed form (stderr) for the tool call, since the draft is made server-side. Test piece: Chopin Op. 9 No. 2, bars 1-8, 20 labels with three planted differences (I53 for I, I6 for I, V65 for V65/vi), found as spelling variant, inversion and chord. No page marks yet, no deploy, SKILL.md untouched (paragraph in `docs/phase3-skill-paragraph.md`).

`compare_labels` now classifies "key and chord both differ" as a different chord (it was a key difference), which also changes the STUDENT CHECK rows in the server and skill drafts.

### 40. Piano reduction: one decision per sounding note (2026-10-12)

**Challenge.** The piano view chose octave and hand chord by chord, from the tune at that moment, so a held note could drop an octave or change staff halfway: ties hung in the air or ended on nothing, and an inner part hopped between staves (K.458 bar 8, Mozart 41 bar 24, Dvořák bar 35). Parts in the tune's rhythm were dropped as "doublings" even when they harmonised it in thirds (K.458 bars 1 and 5), and rests were merged across beats.

**What we did.** Each note of the accompaniment, tied notes of a part counted as one, now gets its octave and hand once and keeps them to its release, across the barline too. A part then moves to one staff, or the start or end of it does, where that saves ties or keeps it together, within a ninth per hand, without the hands crossing and without high left-hand notes. Each staff is one voice or two, split by part or by held against moving notes, whichever needs fewer ties. Only true octave doublings (struck and released together) are dropped. Rests and notes are split to show the beat (Gould). The real Dvořák, Mozart 41 and Haydn 104 files are now under `tests/data/piano/`.

**Result.** Reviewer's checker, bars 1–40 (unpaired ties, gaps, voice totals): K.458 20 → 0, Mozart 41 41 → 0, Dvořák 69 → 0, Beethoven Op. 59/1 13 → 0, Haydn 104 37 → 0. Every note of the five scores now sounds in the reduction for its whole length. Reducing Mozart 41 takes 8.1 s for bars 1–8 (was 6.8 s, mostly parsing the 8 MB file) and 11.6 s for bars 1–40 (was 8.7 s).

### 41. PDF reading: treble clefs in mid-line read as half notes (2026-10-12)

**Challenge.** A treble clef in the middle of a line (a change back from bass clef, or a courtesy clef at the end of a line) was often lost, and every note after it was read in the wrong clef. On the main benchmark, Audiveris found 116 of 300 clef changes.

**Cause.** In Audiveris's note-head step, the loop of the treble clef matches the hollow note-head template and its spine passes for a stem. That false half note's ink is erased before the symbol step, so the symbol step never sees the clef.

**What we did.** Fork change in `NoteHeadsBuilder` (branch `sma-5.11.0-clefs`, candidate 5.11.0-sma.2, not released): around each hollow head candidate, the clef-sized ink is classified as a whole. If the best guess is a treble clef graded 0.5 or more, and no head inside it is a good head (a stemmed chord can look like a clef), a clef is created there, the head candidates are dropped, and the clef is frozen so the symbol step keeps it.

**Result.** Each setting read alone, setting 0, main set: clef changes found 116 → 156 of 300, pitch 91.1% → 92.7%, pitch+timing 82.4% → 84.1%. Held-out set 3: pitch 81.7% → 85.3%. As production reads (best of 3 settings):

| Set | Pitch | Pitch+timing |
|---|---|---|
| main (57 PDFs) | 91.3% → 93.2% | 85.2% → 86.6% |
| held-out (11) | 97.4% → 97.4% | 90.2% → 90.2% |
| held-out 2 (6) | 94.1% → 94.7% | 81.0% → 81.3% |
| held-out 3 (6) | 89.3% → 89.9% | 66.0% → 66.5% |

**Trade-offs.**
- "Invented" clef changes rise on some readings (main set, setting 0: 56 → 58; held-out: 13 → 16). Looking at the ink of every clef the change created on these PDFs (Schubert Die Stadt, Bizet Absence, Holmes, Berg, Franz Lotosblume, Haydn canzonet, Bach C major prelude, Clara Schumann Polonaise 3), all but one are real treble clefs: courtesy clefs at the end of a line, or clefs next to a barline that the scorer counts in the neighbouring bar. The one real mistake is a stacked whole-note chord with a fermata (Haydn canzonet, vr edition, page 2), graded 0.98 as a treble clef.
- A margin over the classifier's second guess would not help: the second guess is 0.05 or less on every real clef found (the best guesses range from 0.62 to 0.98), and 0.23 on the Haydn chord.
- A frozen clef cannot be removed later in Audiveris, so a wrong one stays and changes the pitch of the notes after it, until the next clef.
- Production totals drop on a few PDFs when the chooser picks a different reading: Kinkel Trennung scan loses 27 pitches and 69 pitch+timing.
- Threshold 0.2 instead of 0.5 gives almost the same totals but loses 38 pitches on the Mozart K.545 scan in settings 1 and 2, so 0.5 stays.

**Not yet live.** Releasing the fork, the Docker base image and the reader version wait for the owner's decision.

### 42. Round 2 display polish before the owner's re-review (2026-10-13)

**Challenge.** Seven display defects were flagged on the round 2 "after" images. Each was checked at full size against images re-rendered from the branch (the marks and PDF images reproduced byte for byte).

**Fixed.**
- **Tendency arrow on the staff (BWV 64.4 bar 7).** The bass D3 sits on the middle line, so no spot within two steps of it is outside the staff; the arrow fell back to inside the staff, on the bottom line, and its R moved half way along the shaft, about 0.6 staff space from it. A new placement starts the arrow straight off the note just past the staff edge, R at its tail, both clear of the lines (decision S). The arrow is now 411 units from its note (the old rule allowed 330 beside a note; 450 is allowed when the arrow is straight off it). No other tendency image changed.
- **ABRSM cadential six-four.** The default style's continuation (V⁶₄ then –⁷₋₃) ran in every style, so ABRSM pages read "Ic –⁷₋₃". ABRSM teaching writes Ic–V (MyMusicTheory, Grade 6: "Cadential 6/4 = Ic-Va"), so ABRSM now prints "Ic V⁷". Default and figured-bass pages are byte-identical.
- **Preview bar numbers hitting the system above (Joplin bar 33, and two stems on page 2).** A number raised over a first-ending bracket reached a low left-hand beam of the system above. Placement looked only at its own system, and the 360 units between that beam and the bracket could not hold a 540-unit number with its margin. Previews now use Verovio `spacingSystem` 7 (default 4), and placement also checks the system above. Page counts are unchanged on the four round 2 PDFs; pages are 3–5% taller (measured on the review images: Joplin p1 +4.9%, Chopin +5.3%, Schubert p1 +3.2%), and K.545 moves systems between pages. Base: 2 numbers touching the system above (Joplin), now 0 of 216 numbers on all four PDFs. Beams are not obstacles anywhere in the overlay (a beam group's box covers its notes), so bar 33 is fixed by the spacing, checked by eye.

**Not changed.**
- **Ring code on the alto's bottom line (BWV 102.7 bar 2).** Real: the alto's VO sits on a staff line. But the gap between the alto and tenor staves holds one code with clear space, not two. Preferring an off-staff spot first moved the alto's VO into the gap, and the tenor's VO then went onto its staff or against its fermata (two variants tried). The owner had accepted this bar as is. A joint placement of the codes of one chord was not tried.
- **Rings without a code (BWV 418 bars 8 and 11).** Intended: each is the second note of a pair already coded (bar 8: tenor G♯3 with the bass's VO; bar 11: soprano E5 with the alto's S).
- **"Ped. simile" gone from the Chopin check page.** Intended: the earlier "no pedal marks" decision, extended to pedal words in commit 74b880b after the "before" image was made.
- **Bar 1 unnumbered on previews.** Intended: a piece's first bar is not numbered (standard practice). Decision K was about numbering previews that have nothing to flag.
- **Card phrase bracket.** It ends at the system's last barline, open because the phrase (a′, from the pickup) continues on the next system; it does not run off the page.

### 43. Round 2 display polish, second pass (2026-10-13)

**Challenge.** The standards review of entry 42 found part-writing codes sitting across staff lines, a fault mark missing from a review image, preview bar numbers clipped at the top of pages 2 and later and placed inconsistently at endings, and two review images made from the wrong input.

**Fixed.**
- **Ring codes on staff lines.** Text across staff lines is not engraving practice (Gould: words and signs go outside the staff). A code now takes a clear spot off the staves first: beside or straight off its ring, past a fermata (marks stack outward from a note), or just past the staff's edge on the ring's side. Where no spot is clear, or a ring on a ledger note all but touches another staff's fermata (BWV 64.4 bar 6), a hidden line of room is added at that note and the page is laid out again, up to four lines; room that does not help is taken back. Across the 20 test chorales drawn with the draft's own marks, codes on a staff went from 22 to 2 (BWV 245.40 bars 5 and 12: a tenor eighth inside a beamed run, where no spot works). 6 of 20 pages are 0.7–3.6% taller; the others keep their size. The engraving check's 9 pages are pixel-identical and still have no collisions. The white mask behind BWV 102.7 bar 2's alto VO no longer meets a staff line, so its stub is gone.
- **Preview bar numbers at endings.** Bar 33's number stood above its first-ending bracket but 34's and 67's under the bracket, beside the bold ending digit: Verovio boxes only the digit. The bracket is now an obstacle from its line down to the staff, so all 7 numbers at Joplin's endings stand above it (before: 4 above; 34, 66 and 67 under).
- **Preview top margin.** On pages 2 and later the first number started at the image's top edge (Verovio's margin holds its own, smaller, system-start number). The top margin now grows until the highest number on every page is the image's trim margin (2.5% of the width) from the edge. Page heights change by 0–2% (Joplin p3 grows because one system moves from p2 to p3; page counts are unchanged on all four PDFs).

**Explained, no engine change.**
- **The missing bar 12 "R" (BWV 64.4, final/04 v2).** The review's render script read the draft's `draw` lines with a pattern that had no `direction` field, so `draw arrow … label "R" direction "up"` matched nothing and was skipped; the engine drew it every time. A new test draws every code the draft lists on four whole chorales and checks each is on the page.
- **ABRSM sample with numerals that don't fit the music.** All three final/02 style samples (default included) were drawn from a stress-test annotation list, not an analysis. The v3 samples use the hand-checked BWV 269 analysis (`examples/engraving/bach-269.json`). It has no cadential six-four, so a separate ABRSM sample from the hand-checked Brahms Op. 118 No. 2 shows "Ic V" under a D bracket.
- **Phantom first ending in final/07 and final/09 v2.** They were drawn from `tests/data/chopin_prelude_op28_no4_reading.musicxml`, an old reading with endings and no repeat, passed straight to the preview; decision L's cleanup runs when a PDF is read. The v3 images use the PDF reading, as round2/pdf does.
- **K.545 "48" beside "ff".** About two staff spaces apart on the same baseline, a light italic number against a bold dynamic: readable, left as is.
- **Schubert "Die Stadt" numbered one behind (not fixed).** Audiveris writes the first bar as `number="0" implicit="yes"`: its notes add up to 2¾ of the bar's 3 beats (a misread), so it is taken for a pickup, and the engine keeps the file's numbers.

### 44. Round 2 display polish, third pass (2026-10-13)

**Challenge.** The third standards review found a ring code across another note's head, flat and stem (BWV 245.40 bars 5 and 12), a code nearer an unringed note than its own ring (BWV 404 bar 6), two tendency arrows inside the staff (BWV 64.4 bar 12, BWV 102.7 bar 5), the skill's last-page pull-in undone by the new top margin, render time tripled on coded pages, and a figured-bass sample identical to the default one.

**Fixed.**
- **Codes never on another note.** The last resort took the first spot without looking. Now it takes the spot that touches no notehead, accidental or stem and covers least. Codes also get spots straight above or below their ring, stepping out through the gap to the next staff, so the extra room has a place to fill. BWV 245.40's VO now stands straight above its ring, past the flat, with the staves moved apart. Ring codes touching a note in the 20 test chorales: 2 → 0. On a staff: 2 → 0.
- **Each code nearer its own ring than any unringed note** (decision R). BWV 404's S now stands straight above its own ring. A code straight off its ring only competes with notes in its own column, since marks stack outward from their note (Gould). The new display-rule check still flags BWV 245.40, where no spot meets every rule (DECISIONS-PENDING AN).
- **Tendency arrows.** The arrow can now stack past a fermata (BWV 64.4 bar 12, above the fermata), or sit past neighbouring notes that hang over the staff edge. When only the next staff is in the way, the staves move apart for the arrow as they do for codes (BWV 102.7 bar 5, below the alto staff). The shorter 300-unit shaft is also tried outside the staff.
- **Skill PDF pages.** The top margin is now set before the pull-in. Clara Schumann polonaise 3 is 4 pages again (was 5), and Lehmann "Golden Bridges" 1 page (was 2). All 8 short-last-page readings match the layout before entry 43, and every page keeps its top margin.
- **Render time.** Each code measures how far short its gap is and asks for that many lines at once. A gap blocked only by the code's own staff asks for nothing. One room per gap per bar, so rooms above and below a gap no longer stack. The last measuring pass is the page itself, so it is not drawn again. BWV 245.40 bars 0–28: 1.09 s → 0.55 s. The 20 chorales: 5.43 s → 4.18 s in total (mean of 3 renders each). One line is 390 units and Verovio's margin is 2 × 180, both measured on BWV 245.40; a fifth request gives up. The one-step room gave pixel-identical pages to the line-at-a-time result on all 20 chorales. Merging the rooms of a gap then made two pages shorter: BWV 336 by 12 px and the BWV 418 bar 11 excerpt by 13 px (at 2800 px wide).
- **Figured-bass sample.** It is now drawn from the hand-checked Brahms Op. 118 No. 2, which uses the style's own figures (vii^ø⁶₅♮₃/IV, V♯⁴₂/V, iii⁷♯₅/V, V⁷♯₃/V). Bar 4 is not relabelled (decision pending, AJ).

**Before/after.** engraving_check: 0 overlapping, 0 tight, 0 music collisions. The four review PDFs (previews and cards) and final/07 are pixel-identical to v3. Changed review images, with -v4 versions written: final/04 BWV 102.7, 64.4, 245.14 and 418; round2/marks R-bwv418-11-11 and R-bwv245.14-9-9; final/02 figured-bass. The display-rule check (corpus-checks) reports 19 violations on this branch. Those in this work's scope: BWV 245.40 decision R (2), and arrows inside the staff at BWV 336 bar 2 and the tendency sample bar 1 (4, owner question AM).

### 45. PDF reading: a tie no longer goes to the sparse reading (2026-10-13)

After the sma.2 clef fix, the Kinkel "Trennung" scan lost 27 of 381 pitches and 69 pitch-and-timing events. The default setting has no small-note detection and drops the grace notes and half of the bass in bars 10-11. Under sma.1 it had 7 bars that don't add up against 5 for the other settings, so setting 1 won; the clef fix made bars 10 and 11 add up without restoring the notes, the three readings tied at 5, and the tie went to the first. Now, among readings tied on skipped pages and uneven bars, one with under 90% of the most pitched notes is dropped. Kinkel: pitch 308 -> 335, pitch and timing 255 -> 324 (the sma.1 values). Replaying the chooser over 240 cached readings (80 PDFs x sma.1, sma.2 and a candidate build) changes only Kinkel; of 42 ties it changes one pick. Why a margin rather than "most notes wins": on the Schubert *Die Stadt* tie, 897 vs 900 notes, the larger reading has 139 fewer right pitches. In all 39 setting pairs where one reading has under 90% of the other's notes, the smaller one has fewer right pitches. A floor near 0.92 would also switch two Bach and Mozart ties for the better; with two data points it stays at 0.9.

A guard for the Haydn canzonet chord read as a treble clef (bar 35) was built and dropped: the bar was already empty under sma.1 (with an invented C clef), so pitch counts are the same with or without it. Its branch stays in the fork clone.

**Replaced at the merge of the round 2 branch.** That branch's guard (commit 8036e75) leaves out any reading with under 95% of the fullest reading's pitched notes before the fewest uneven bars are looked for, not only on a tie; it replaces this tie rule, as the owner decided. Kinkel's sparse default (27 of 381 pitches lost) is still passed over.

### 46. One log line per tool call, with timings by stage (2026-10-23)

Week 1 of `docs/plans/observability-and-scalability.md`. Before: `render_analysis` and `correct_bars` had no timer; a draft's time was a single wall-clock figure; the model's own time went to stderr as plain text; a server fault (the model failing to load or timing out) was logged exactly like a user's bad input; and some error returns were not logged at all (no note list, a question back to the student, a bad student analysis), so the usage report never saw them. A render whose MusicXML export or worksheet failed wrote a second line that the report counted as a second render.

After: each of the five tools writes exactly one JSON line when it finishes, keeping the old `event` and detail fields that `tools/usage_report.py` reads, and adding:
- `outcome` (ok, user_error, limit, busy, server_error, or cancelled when the client goes away mid-call) with a matching `severity`;
- a Cloud Logging trace field, taken from the `traceparent` or `X-Cloud-Trace-Context` header (a fresh id if neither arrives);
- `cold`, `uptime_s`, and `timings_ms` for each stage: fetch, parse, counter, gnn_wait, gnn_start, gnn, build, omr, render, export, publish and total.

The model process reports its inference time in its reply (`ok 0.518`), and its load time as a JSON line. A server fault carries a `stack_trace` so Error Reporting can pick it up. An exception nothing catches is logged the same way and then raised as before, so no tool returns anything different. uvicorn's own warnings use the same JSON format.

Measured locally on the Chopin nocturne note list (5,796 characters): cold draft 6,363 ms, of which 5,507 ms was model start-up (WSL; about 54 s on Cloud Run), 581 ms inference and 218 ms building the text. Warm: 789 ms total, 518 ms inference. With a missing checkpoint the line reads `server_error`, severity ERROR, with the stack trace. In production it is NOT RUN yet: the plan's week-1 check runs in staging, and staging comes in week 4.

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
