# Engineering log

A record of the problems met while building this tool, what was done about each, and how the results were measured. Numbers come from runs kept in `out/` (not committed) and can be reproduced with the commands at the end.

**The tool:** a plugin for Claude and ChatGPT that reads a MusicXML score and returns the score engraved with a harmonic analysis drawn on it (Roman numerals, cadences, phrases, non-chord tones, voice leading) and a written commentary. A graph neural network (AnalysisGNN) drafts the analysis; the chat model reviews and corrects it; our engine places every label on the engraved page.

## At a glance

- **A two-stage analysis pipeline, measured against human experts.** A neural draft followed by a chat-model review, scored by duration against chord-by-chord readings by human analysts on 12 pieces from Bach to Grieg, and against published teacher and textbook analyses for the rest of a 23-piece set.
- **The review stage raises agreement with experts on 11 of 12 scored pieces.** Weighted by length across 12 pieces (1,158 bars), the share of the music where key, chord and bass all match the human analyst rose from 0.54 to 0.71, and the share with the right key from 0.81 to 0.89. The largest gains were Schumann (0.61 to 0.92), Haydn (0.42 to 0.72) and Beethoven Op. 2 No. 1 (0.47 to 0.73).
- **Checked on 30 pieces the draft model never saw in training.** Several of the 12 pieces were in the draft model's training data. On the same held-out passages the draft alone scores 0.48, and the review lifts it to 0.67 (+0.19), improving 26 of 30 pieces (challenges 58 and 66; first reported as 0.44 → 0.61 before the scorer fixes of challenge 66).
- **Checked against what teachers actually wrote.** Against published analyses of 19 pieces (textbook chapters, exam-board teaching notes, articles and dissertations), our analysis agrees with 63% of 431 checkable claims, partly agrees with 26%, and disagrees with 4%, on the judge's first marking, which is lenient (a second marking of the same analysis gives 4 to 18 points less; challenge 9). Every disagreement was read by hand and sorted into areas to improve.
- **Measured which chat model to use.** Over the full 23-piece set, Opus 5.5 at medium effort beat Sonnet 5.5 as the reviewer: full agreement with expert labels 0.66 → 0.71, agreement with teachers' claims 52% → 63%, at 36% more cost and 25% less model time.
- **Found and fixed a silent failure in the neural model's output.** The model names each key's tonic but not its mode, so every minor key was read as major. Recovering the mode from the chords lifted key accuracy on minor-key pieces from 0.00 to 0.92 (Chopin Prelude No. 20), 0.27 to 0.79 (Beethoven Op. 2 No. 1) and 0.20 to 0.89 (Tchaikovsky).
- **Measured how far experts agree with each other, by style.** Across 151 independent pairs of expert analyses (10,684 bars, weighted by bars), experts agree on key, chord and bass for 0.71 of the music: 0.87 on Bach chorales, 0.79 on Mozart sonatas, 0.59-0.65 on Chopin mazurkas and Beethoven sonatas (0.69 without the chorales). On the chord's role (same function family, inversion aside) they agree on 0.91. Scored against the same other experts each expert is scored against, our reviewed analysis agrees on the chord's role 0.86 of the time, against the experts' 0.80 (6 pieces; challenge 66). On 30 unseen pieces our *full* agreement is 0.67, about 0.04 below the expert level.
- **Matched expert-to-expert agreement on one movement analysed by three expert teams.** On Beethoven's Op. 2 No. 1, first movement, the reviewed analysis agreed with three independent expert analyses at 0.76 full agreement, against 0.78 between the experts themselves (one movement, one review; a single review varies by about 0.04). Challenge 66 found that this review and the expert files were all placed one bar off the score's notes. Re-reviewed with the skill of that time and the numbering fixed (challenge 68): 0.80 full against the three experts on average (0.78, 0.85, 0.78), against 0.78 between the experts themselves; function 0.89 against 0.85.
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

Measured locally on the Chopin nocturne note list (5,796 characters): cold draft 6,363 ms, of which 5,507 ms was model start-up (WSL; about 54 s on Cloud Run), 581 ms inference and 218 ms building the text. Warm: 789 ms total, 518 ms inference. With a missing checkpoint the line reads `server_error`, severity ERROR, with the stack trace. On Cloud Run, in a new staging service (`server/deploy.sh PROJECT staging`: its own service, bucket and image tag, login required, the production settings): cold draft 50,145 ms, of which 46,925 ms model start-up (imports 44.5 s, load 2.4 s), 1,969 ms inference and 897 ms building the text; warm 2,968 ms, 1,654 ms inference. Cloud Run supplies the trace header itself, so each line's trace matches its request log. The forced failure logged as ERROR with its stack trace. Error Reporting, once its API was switched on, groups the failure twice: the server's DraftError, and the model process's own traceback (FileNotFoundError for the missing checkpoint), one count each per failure. The deploy uploaded 3.7 GiB of source (37,937 files), most of its 6.5 minutes; a `.gcloudignore` listing only what the Dockerfiles copy cuts it to 52 files, 4.6 MiB, and the staging deploy to 2.5 minutes.

### 47. Metrics, a dashboard and email alerts (2026-10-24)

Week 2 of the observability plan. Before: no metrics beyond Cloud Run's own, no dashboard, no alerts; an error or a runaway bill was found only by looking. All of it is now files in `server/monitoring/`, created by `apply.sh` (safe to re-run):
- seven log-based metrics from the per-call line: `tool_calls` (by tool, outcome, platform, cold start) and the time spent in total, waiting for the model, starting it, running it, rendering and publishing;
- a dashboard of 18 charts: traffic, latency percentiles split by cold start, time per stage, Cloud Run's request latency, start-up, CPU and memory, recent warnings and errors, and Error Reporting;
- two email alerts to the owner: "Server errors" (any server_error in 10 minutes, on either service) and "Cost guard" (production billed over 3,600 instance-seconds in a day; log 21's leak billed 15,450).

Both alerts fired by test and the emails arrived: a forced model failure on staging at 00:15:55 UTC emailed at 00:19 (the metric lags about 3 minutes), and a temporary copy of the cost guard pointed at staging with a 1-second limit emailed at 00:15, then was deleted. A scripted staging run (6 drafts in a row, then 2 at once) filled the charts: warm p95 5.8 s, cold p95 65.5 s, and the model wait reached 2.1 s at p95 when two drafts arrived together, the queueing the plan predicted. The uptime check is not created yet: every 15 minutes (the longest gap allowed) it could cold-start the production container, up to about 1,050 billed seconds a day, around a third of the monthly free allowance.

### 48. Tracing each call into Cloud Trace (2026-10-24)

Week 3 of the observability plan. Before: a slow call could be seen only as numbers in its log line. After: on Cloud Run, every tool call is also a trace, drawn as a waterfall in Cloud Trace and linked from its log line. A warm staging draft reads: Cloud Run's request 2,809 ms > the MCP library's `tools/call draft_from_notes` 2,758 ms > our `draft_from_notes` 2,662 ms > counter 134, model 1,810, parse 8, build 709. The span id in the log line matches the tool span.

Two things were not obvious. The MCP library (2.x) opens its own span for every call, but nothing set the incoming trace from the HTTP headers, so on the first local run it landed in a separate trace from ours. A small wrapper around the web app now sets the trace from `traceparent` or `X-Cloud-Trace-Context` before the library runs, so all spans share Cloud Run's trace. And Cloud Trace stores spans in a `_Trace` bucket that it creates only after the first spans arrive through its API, which takes several minutes; until then every read returns "_Trace bucket not found".

Sending the spans happens at the end of each call, because Cloud Run gives a container CPU only while a request is open; it costs under 0.1 s (the library's span minus ours, 96 ms, also includes the library's own work). The two packages add about 22 MB to the image and 0.1-0.3 s to start-up; the cold staging draft was 35 s. Locally (no `K_SERVICE`) nothing is exported. The Cloud Trace exporter now warns that it is deprecated in favour of OTLP to `telemetry.googleapis.com`; it still works, and switching is a later, separate change. The server's account was given `roles/cloudtrace.agent` by the owner.

### 49. Where the cold start goes (2026-10-24)

The first draft on a fresh instance takes 30-50 s, almost all of it the draft model's Python imports: 26.8-41.6 s over four cold starts on staging, against 3.75 s for the same modules from the same image on the development machine. Profiling one cold start (`PYTHONPROFILEIMPORTTIME`): the analysis model package 16.6 s (local 1.56), of which torch_geometric 9.6 and pytorch_lightning 4.65; partitura 9.4 (1.18); torch 6.4 (0.76). The shipped bytecode is valid (11,472 .py files, each with a current .pyc; importing writes none). 23.2 of the 33 s goes to about 4,700 small modules that take under 1 ms each locally: about 5 ms per file on Cloud Run against 0.23 ms, 21x, while modules that compute are only 2-3x slower. That points to slow first reads of files from the container image rather than a slow CPU; not yet proven (the local runs had the files cached).

A throwaway Cloud Run job confirmed it. In a fresh container the first import took 29.7-42.1 s over four runs; a second and third import in new processes took 5.6-6.4 s. Reading every file of the model's environment first, one at a time, took about 4 minutes (42,118 files, 1.43 GB), so the cost is per file read, not per byte; reading them with 16 at a time took 15 s, after which the import took 7 s.

The fix: during the image build, the model process records every file it opens while importing, loading the weights and analysing a tiny sample (Python's audit hook for opened files, plus the shared libraries in `/proc/self/maps`): about 5,500 files, 920 MB, most of it torch's main library. When a draft starts the model, it reads those files 16 at a time just before its own imports. It runs only when a draft starts the model, so renders, PDF reading and downloads are unchanged. On staging, four true cold starts each (instance up 1 s):

| | Client time | Server total | Model start-up | Imports |
|---|---|---|---|---|
| Before (median) | 66.7 s | 52.5 s | 47.9 s | 45.9 s |
| After (median) | 22.5 s | 13.7 s | 10.6 s | 9.7 s |

The read-ahead itself takes about 5 s and runs alongside the imports. Peak memory 0.19 of 4 GiB, against 0.18 before.

What the plan proposed for week 4 and what was decided instead: loading the model at start-up behind a readiness check does not shorten the first draft at min 0 and max 1 instances (the request waits either way) and would make cold renders, PDF reading and download links wait 50 s instead of about 11 s, so it waits for the week-6 instance decision. The daily counter is not the first bottleneck at max 1: the model, one draft at a time at about 0.5 drafts/s, is; and the storage library retries a contended update for up to 2 minutes, so overload shows as slow calls, not errors. The week-5 load tests measure it before anything changes. A `DAILY_LIMITS` environment override lets staging run with limits of 100,000; production keeps its defaults.

### 50. Load tests on staging (2026-10-24)

Week 5 of the observability plan. Before: no measured capacity; the plan's numbers were estimates. k6 (`tools/load/drafts.js`) sent 70% `draft_from_notes` on six test scores (680-5,796 characters of notes) and 30% `render_analysis` of Chopin bars 1-8, to staging only. Throughput counts calls that succeeded inside each 2-minute step; times are measured at the client.

How many calls one instance takes at once (max 1 instance):

| At once | Users | Calls/s | Draft p50 / p99 | Render p50 / p99 | Refused |
|---|---|---|---|---|---|
| 1 | 1 | 0.18 | 1.6 / 3.5 s | 13.7 / 15.5 s | 0 |
| 1 | 2 | 0.23 | 4.5 / 10.8 s | 15.8 / 17.4 s | 20% |
| 2 | 2 | 0.30 | 2.6 / 5.6 s | 15.5 / 19.6 s | 0 |
| 2 | 4 | 0.38 | 6.6 / 12.2 s | 16.9 / 26.7 s | 9% |
| 4 | 4 | 0.33 | 6.3 / 11.9 s | 40.7 / 51.9 s | 0 |
| 4 | 8 | 0.19 | 10.3 / 18.0 s | 10.4 / 73.2 s | 64% |

One instance tops out at about 0.3 calls/s whatever the setting; renders use the CPU and slow everything beside them. Two at once gives the same throughput as four with renders at p99 19.6 s instead of 51.9 s. Every refusal was Cloud Run's own HTTP 429 "Rate exceeded" after about 10 s with no free slot, never a tool error.

More instances (two at once each): 1 instance 0.30 calls/s, 3 instances 0.65, 5 instances 1.07, roughly in line. A new instance served its first call 9-37 s after starting. While scaling out, Cloud Run refused calls (429, or 500 "no available instance") once the queue filled: 2% at 8 users on 5 instances, 27% at 16. Both services carry a service-level cap of 3 instances that overrides a revision's own maximum; production's revision maximum of 1 sits under it.

Other runs, at max 1 instance and two at once:
- **Spike from idle to 8 users:** 58 calls, none failed. The first answered at 27 s; drafts in the first minute waited 52 s at the median, 18.6 s after that.
- **30 minutes at 2 users:** 471 calls, none failed. Drafts p50 2.6 s, p99 7.1 s; renders 18.9 s, 24.3 s. No drift between the first and last 5 minutes; memory flat at 0.20-0.24 of 4 GiB.
- **Six more true cold starts:** client median 20.3 s, model start-up 11.4 s, close to log 49 (22.5 s, 10.6 s).

The daily counter, which week 4 left to be measured (927 warm drafts, server side): p50 160 ms, p95 0.93 s, p99 2.4 s, max 6.7 s, about an eighth of a typical draft. It slows calls under contention but never failed one, and the model is not the bottleneck either (waiting for it: p50 0, p95 0.8 s); renders sharing the CPU are. Staging billed 6,124 s for all of it, about $0.36: about $0.38 per 1,000 drafts with their renders, $0.32 in the steady 30-minute run. Staging is back to four at once, max 1, min 0.

Owner's decision the same day: both services now take two calls at once and run at most two instances (production revision 00027, same image as 00026; settings only). Total spend stays bounded by the daily limits; a second instance adds only its own start-up, about 20 s billed each time it starts. Loading the model at start-up is still open.

### 51. Service level objectives (2026-10-24)

Week 6 of the observability plan. Two SLOs on the production service in Cloud Monitoring, over 28 days, from the per-call log metrics (`server/monitoring/slo-*.json`, created by `apply.sh`): 99% of tool calls without a server error, and 95% of warm drafts under 6 s on the server. The plan said 3 s; the load tests put warm drafts at p95 5.7 s under load and about 2-3 s when idle, so 3 s would be missed by any busy hour. Cloud Run's own metrics could not do this: every call is `POST /mcp` and tool errors return HTTP 200. The filters match staging's data (1,376 calls and 942 warm drafts in the last day); production has no data for them until the week 1-5 code ships there. No burn-rate alert: at a few calls a day one slow draft would fire it, and the server-error alert already emails on every failure.

`deploy.sh` now deploys the image it just built by its digest instead of by tag, so a later settings-only update cannot pick up a newer image pushed to the same tag. The running services still name their tags until their next deploy.

Shipped the same day: the week 1-6 work went to production as revision 00028 (image pinned by digest, two calls at once, at most two instances, production limits). A cold production draft of the longest test score took 17.6 s at the client (model start-up 12.4 s), wrote its log line with timings and trace link, and appeared in Cloud Trace with all its stages; no errors on the new revision. Staging is on revision 00039 from the same code.

### 52. The budget email counted usage before the free tier (2026-10-24)

The CAD 5 budget emailed 50% on Oct 8, 90% on Oct 17 and 100% on Oct 24, but it excluded all credits, and the free tiers show up as credits, so it measured usage at list price. Rebuilt from usage (no billing export; the console was not checked): Cloud Run 54,369 instance-seconds in October (production 46,109, of which 41,301 on Oct 7-9 from log 21's leak; staging 7,535 for the load tests; 725 for the cold-start job), about US$3.15 at list price but inside the free tier (109k of 180k vCPU-s, 217k of 360k GiB-s); Cloud Build 139 minutes of 2,500 free; Artifact Registry 4.4 GB and the build-source bucket 11 GB, the only parts beyond a free tier, about US$0.40 a month together. The budget now includes credits, so its emails mean money owed; the amount stays CAD 5. Two cleanup rules, kept in `deploy.sh`: build sources older than 7 days are deleted (the 11 GB were mostly uploads from before `.gcloudignore`), and base images older than 7 days are deleted except the two newest, beside the existing rule for untagged images.

### 53. Could a recording replace the score? (2026-10-24)

A local feasibility test, no product code. Both claude.ai and ChatGPT (even Free) accept an mp3 and put it in the code sandbox unchanged; YouTube and Spotify links are ruled out by their terms. Test piece: Chopin Prelude Op. 28 No. 4, recording by Ivan Ilić (CC BY 3.0, Wikimedia Commons, 110 s), against our draft of the MuseScore edition the eval uses (no expert labels exist for this prelude). Pipeline: the Kong/ByteDance piano model, Beat This! for beats, quantising, partitura's key and spelling, then our draft unchanged.

| Run | Bar lines right (of 25) | Full numeral agrees | Final V-i |
|---|---|---|---|
| Fully automatic | 9 | 56% | found, wrong bar |
| Meter and key given | 12 | 59% | found, one bar early |
| Timing from the real score | 25 | 73% | right |
| Real score's notes, same score-building | 25 | 77% | right |

The notes themselves are good: onset F1 0.977 (Basic Pitch 0.744). The losses come after: building a score from notes (hands, note ends, spelling) costs about 20 points even with perfect notes, and beat tracking about 14 more; it took one beat per bar for most of the piece, and the slowing at bar 12 shifts every later bar. Bar numbers wrong from bar 12 on would be visible to any beginner. Kong takes about 1.1 s of one CPU per second of audio. Verdict: not usable as an automatic feature yet; the hard part is the score, not the notes.

### 54. Audio phase 0: can it run inside Claude? (2026-10-24)

Plan `docs/plans/audio-input.md`, phase 0. A probe run in a real claude.ai chat: Python 3.13, 2 CPUs, 8 GB RAM, 30 GB disk, ffmpeg installed; PyPI installs work (numpy, soundfile, onnxruntime in 1.9 s) and GitHub releases download at 21 MB/s, but PyTorch's CPU wheel index, Hugging Face and Zenodo are blocked (403); a 10-minute command ran to the end; files in /tmp survive to the next turn; a 3-minute mp3 reads in 0.2 s; the CPU is about 1.8x slower than the development machine (2000x2000 matrix products: 1.12 s against 0.62 s on 2 threads).

So the models run without torch: the Kong piano model exported whole to ONNX, front end included, and Beat This! from the spectrogram on, with framing and FFT in numpy. On the same input the ONNX outputs match torch exactly (604 of 604 notes, onset and offset F1 1.0, 94 of 94 pedals, 72 of 72 beats, 55 of 55 downbeats). On 2 cores here a 3-minute recording takes 83 s at 2.37 GB peak, flat because the audio is processed in fixed chunks; at the sandbox's speed that is about 150 s, inside the phase's limit of about 5 minutes and 6 GB. Models: 154 MB and 83 MB, too large to attach to a chat (30 MB), so they need a GitHub release; packages: numpy, soundfile, onnxruntime and soxr, about 130 MB. m4a needs ffmpeg, which the sandbox has.

The models are now the GitHub release `audio-models-1` on the main repository, with sha256 sums and credits (Kong: CC BY 4.0; Beat This!: MIT). The real claude.ai run on the same 3-minute mp3: packages installed in 2 s, both models downloaded and verified in 5 s, transcription and beats in 89 s (Kong 74.2 s, beats 11.9 s), peak 2.39 GB; 95.5 s in all. Phase 0 passes: under its limit of about 5 minutes and 6 GB.

### 55. Audio phase 1: the baseline against the gate (2026-10-24)

`eval/audio.py` measures the gate on 20 pieces that are in ASAP and have When in Rome expert labels: 15 Beethoven, 2 Mozart (K. 332 I and III), Bach BWV 846, Chopin Op. 10 No. 1 and Liszt's Gondoliera, with 6 pickups, 5 compound meters, 3 in 2/4, 4 meter changes and 8 with tempo changes or fermatas. Excerpts of at most 64 bars or 150 s, real MAESTRO performances streamed one file at a time (evaluation only, kept out of the repository), positions mapped through ASAP's beat annotations. A bar counts as right only if both its ends fall within the larger of 0.3 s and a quarter of the local beat. The transcription is not the problem: note F1 0.974-0.999 on every piece.

The baseline (Beat This! with a fixed number of beats per bar from the first downbeat) fails both conditions: bars at least 90% right on 2 of 20 pieces (16 needed), and full-numeral accuracy against the experts 44.0% from audio against 50.4% from the real score, 6.4 points apart (5 allowed; root and quality 64.6 against 70.4, key 75.5 against 76.4). The tracker usually finds the downbeats (F above 0.9 on 13 pieces), but counting a fixed number of beats per bar lets one extra beat shift every later bar, and it writes compound meters as 2/4. Score-building also costs numerals by itself: K. 332 I has every bar right and still loses 16 points. Next are the plan's T1-T3: bar lines from the tracked downbeats with the meter chosen from the music, tempo smoothing, and the user's optional answer.

### 56. Audio phase 1: T1-T3 also fail the gate (2026-10-24)

| Method | Bars at least 90% right | Full-numeral gap to the score path (50.4%) |
|---|---|---|
| T0 baseline | 2 of 20 | 6.3 |
| T1 bar lines from tracked downbeats, meter from the music | 5 | 9.3 |
| T2 T1 plus tempo smoothing (Viterbi) | 6 | 7.3 |
| T3 T2 plus the real starting meter and pickup | 7 | 6.8 |
| Bar lines taken from ASAP (perfect timing) | 20 | 5.5 |

The gate needs 16 of 20 and at most 5 points, so every method fails both conditions, and even perfect timing misses the numeral condition. The numerals barely depend on the bar lines (44.1% at 27% of bars right, 44.9% at 100%), because labels are matched by time. Where the points go, with perfect timing: the transcription costs almost nothing (about 44 from transcribed notes, 44.3 from the score's own notes through the same writer); spelling, the hand split and the key cost about 4 (48.0 with the real ones); the score writer itself about 2.4. The remaining bar failures are beat-level: one piece tracked in eighth notes, downbeats at the half bar in three, tempo changes in two. The salience weights were chosen on these same 20 pieces, so T1-T3 are if anything optimistic. Not yet tried: other trackers (T4), fine-tuning the tracker (T5, needs a one-off GPU spend), and automatic spelling, hand split and key work.

### 57. Audio phase 1: the last round fails too; audio is parked (2026-10-24)

The owner allowed one last bounded round (local, free). Every choice was made on 8 further ASAP pieces with When in Rome labels (Beethoven Op. 53 I and II, Op. 22 I, Op. 110 I, Op. 13 III, Chopin Op. 10 No. 12, BWV 856 and 868), and the 20 gate pieces were run once at the end.

| Method | Bars at least 90% right | Full-numeral gap to the score path (50.4%) |
|---|---|---|
| T0 baseline | 2 of 20 | 5.4 |
| T2 fully automatic | 6 | 7.3 |
| T3 meter and pickup given | 7 | 6.4 |
| Bar lines from ASAP (perfect timing) | 20 | 4.5 |

Only perfect timing passes, and no method can supply it, so the gate fails and audio is parked as the plan says. Root and quality: 63.9 (T2) and 64.4 (T3) against 70.4; key 76.7 and 77.2 against 76.4.

What helped: spelling each note around the first draft's local key, with the key signature from the draft's majority key, gained 2.4-3.6 points on the tuning set and is kept in `eval/audio.py`. A cost-based hand split (+0.4 at best) and pedal-extended note ends (+0.8 at best) were noise and were dropped.

What didn't: PM2S (MIT code, CC BY weights) was worse than Beat This! on every tuning piece (downbeat F 0.29-0.80 against 0.32-1.00, bars about 0%). BeatNet was not run: not trained on piano, offline mode needs madmom, published results below Beat This!. A harmonic-rhythm test for bar length separated nothing. A bar-length prior in the smoothing fixed BWV 868 (0% to 95%) but broke Op. 13 III (92% to 0%), net zero, removed. Bar sizes counted in eighths were never chosen. The tempo-change fix was not run, for want of a similar tuning piece. Both trackers were trained on ASAP, so these numbers are on recordings they had seen, and are optimistic.

Why parked: with every bar right the analysis is close enough, but the bar failures are genuinely ambiguous (half-bar against whole-bar downbeats, eighth-note tracking, tempo changes) and nothing free and local resolved them. What would reopen it: a beat tracker that gets bar lines right on unseen piano performances, or fine-tuning one (a quoted one-off GPU cost, owner approval). The harness, test set and ONNX models (release `audio-models-1`) stay for that. `site/docs.html` keeps saying audio isn't supported.

### 58. A larger test on pieces the draft model never saw (2026-10-24)

**Question.** Is 0.54 → 0.71 still right after about 100 engine and skill commits, and does it hold beyond 12 hand-picked pieces?

**A flaw in the old test.** The training code of AnalysisGNN (`vendor/analysisgnn`) trains on the AugmentedNet collections and the Distant Listening Corpus, and each sets aside a fixed list of test pieces. Several of our 12 pieces were in training: the Bach C major prelude, the chorale, Mozart K. 332 i, Beethoven Op. 2 No. 1 i and Op. 13 ii. So the draft's own score there is flattered.

**Method.** A held-out set (`eval/pieces.py`, `HELDOUT`): 94 labelled pieces in neither training set. 70 come from the DCML piano corpora (Beethoven, Chopin mazurkas, Grieg, Dvořák, Liszt, Medtner, Mozart, Schumann, Tchaikovsky) and 24 from When in Rome (15 songs, 6 Bach preludes, 3 chorales). 90 ran; 4 failed (three Liszt label files point to beats outside their bars, and one Beethoven movement timed out). Review: Opus 5.5 at medium effort on 30 of them, picked across composers from the 56 whose labels fit the file well (fit ≥ 0.85), with two evenly spaced 24-bar passages each (`eval.review --passages 2`), and draft and review scored on those same bars. Intervals come from resampling pieces 2,000 times.

**Results.**

| | Pieces | Draft *full* | Reviewed *full* | Key: draft → reviewed |
|---|---|---|---|---|
| The 12 core pieces (+ Clair de lune), today's code | 13 | 0.55 | 0.71 (0.67-0.76) | 0.82 → 0.88 |
| Same, run of 2026-10-03 | 12 | 0.54 | 0.71 | 0.81 → 0.89 |
| Held out, draft only | 90 | 0.42 (0.39-0.46) | | 0.75 |
| Held out, fit ≥ 0.85, draft only | 56 | 0.47 (0.43-0.51) | | 0.73 |
| Held out, reviewed sample, same bars | 30 (1,182 bars) | 0.44 | 0.61 | 0.72 → 0.84 |

On the held-out sample the review adds 0.17 (95% interval 0.11 to 0.24) and improves 26 of 30 pieces. On the 8 core pieces that both runs reviewed in full, the review scores the same as before (0.734 on 2026-10-03, 0.733 today), so the commits since then did not change the analysis. Pieces moved both ways by up to 0.11 (Bach prelude 0.80 → 0.69, Op. 2 No. 1 0.73 → 0.78), which is within one review's variation.

**What it means.** The honest draft-alone figure is about 0.45, not 0.54. The review's gain on unseen music (+0.17) matches its gain on the core pieces (+0.16), and absolute agreement after review on unseen music is about 0.61. The four pieces the review made worse include Beethoven Op. 14 No. 1 ii (0.66 → 0.50) and Chopin Op. 41 No. 1 (0.07 → 0.02, where draft and review both disagree with the expert almost everywhere; not yet read by hand). The 34 held-out pieces with fit below 0.85 are mostly songs and DCML pieces whose label file and score may number bars differently; they were left out of the review, not fixed.

**Cost.** $22.49 on the API key, then the account ran out of credit and the remaining passages ran on the subscription (their estimated cost is also in `out/api-spend.jsonl`, so the ledger overstates API spending for this day by about $30).

### 60. Error messages kept out of the logs (2026-10-24)

An error's message can quote what the user sent (a part name, a note, an id), and six log lines in `server/app.py` still wrote it in full, against the privacy page. They now log only the error's kind (for example `ScoreError`); the user still gets the full message in the reply. This was built on 2026-10-13 on the usage-log branch, which never merged because the observability work replaced the rest of it. Tests: 175 server-path tests pass. Goes live with the next deploy.

### 59. How far experts agree, on 124 pairs instead of 9 (2026-10-24)

**Question.** Challenge 14's expert ceiling rested on 9 Beethoven pairs (0.60 full) and one movement (0.78). Is that representative, do experts agree more on simpler music such as Bach, and how much of their disagreement is labelling convention rather than a different hearing?

**Method (`eval/ceiling.py`, rewritten).** Every When in Rome folder with a second analysis, kept only where the two files' Analyst lines name different sources (DCML, BPS-FH, BCMH, TAVERN's two encoders, Tymoczko's TAOM team). A provenance check of all 370 such folders found many second files to be copies or conversions of the first (all 6 BPS files, 29 DCML Beethoven files, 24 Tymoczko Beethoven copies); the source rule excludes these, along with identical files. Corelli (48 pairs) is left out because its scores exist only as MuseScore files. Each analysis may be shifted one bar to fit the notes, and pairs must fit at least 0.85. TAVERN's scores are UTF-16 MusicXML, now decoded, but most of its pairs still misalign (fit about 0.5, probably bar numbers restarting per variation), so only 2 count. No published study measures duration-weighted Roman numeral agreement on scores; the nearest figures are for chord labels on recordings (roots 76-92%, major/minor chords about 73%; Koops et al. 2019, Poltronieri et al. 2025).

A new scoring level, *function*, forgives three conventions on top of *chord and bass* (which already ignores key): a cadential 6/4 against V over the same bass, a triad against its seventh chord, and tonicization against modulation. It is added to `engine/comparison.py`, so our own runs report it too.

**Expert against expert, 124 pairs, 9,155 bars, weighted by length:**

| | Pairs | Bars | Key | Root | Chord and bass | Function | Full |
|---|---|---|---|---|---|---|---|
| Bach chorales (TAOM v BCMH) | 66 | 906 | 0.93 | 0.99 | 0.94 | 0.97 | 0.87 |
| Mozart sonatas (DCML v TAOM) | 23 | 2,872 | 0.93 | 0.93 | 0.82 | 0.85 | 0.77 |
| Chopin mazurkas (DCML v TAOM) | 20 | 1,719 | 0.75 | 0.89 | 0.73 | 0.80 | 0.58 |
| Beethoven sonatas (DCML, BPS-FH, TAOM) | 13 | 3,304 | 0.76 | 0.85 | 0.71 | 0.77 | 0.57 |
| TAVERN variations (a v b) | 2 | 354 | 1.00 | 0.97 | 0.92 | 0.96 | 0.92 |
| All | 124 | 9,155 | 0.84 | 0.90 | 0.78 | 0.83 | 0.68 |

With pairs down to fit 0.80 (chorales with many passing notes fit about 0.82 even when aligned): 148 pairs, full 0.68.

**Where experts lose agreement** (share of all music): naming a different key 7.8% (most of it tonicization against modulation), different chord 4.7%, inversion 4.7%, cadential 6/4 or seventh 4.6%, related chord 4.1%, chord quality 2.9%, same tonic but other mode 1.7%. Close to half of the gap between *full* and 1 is convention: forgiving key naming, cadential 6/4s and sevenths lifts agreement from 0.68 to 0.83. The rest (about 0.17 of the music) are different hearings of the chord or its bass.

**Our reviewed analysis, scored the same way:**

| | Key | Root | Chord and bass | Function | Full |
|---|---|---|---|---|---|
| Core 13 pieces | 0.88 | 0.90 | 0.80 | 0.85 | 0.71 |
| Held-out 30 pieces | 0.84 | 0.84 | 0.71 | 0.76 | 0.61 |
| Experts against each other | 0.84 | 0.90 | 0.78 | 0.83 | 0.68 |

By style, on held-out pieces: Beethoven 0.60 full (6 pieces; experts 0.57), Chopin mazurkas 0.58 (5; experts 0.58), Mozart 0.77 (1; experts 0.77), Bach chorale 0.68 (1 chorale, 13 bars; experts 0.87). The samples on our side are small and the pieces differ from the experts' pieces, so this is a comparison of levels, not a head-to-head.

**What it means.** The user's intuition holds: experts agree far more on Bach chorales (0.87 full, 0.97 function) than on Beethoven or Chopin (0.57-0.58). On the sonatas and mazurkas our reviewed analysis on unseen pieces sits at the experts' own level. Overall it sits about 0.07 below them on *full* and *function*, and the gap is widest on Bach, where experts nearly agree and we do not yet (the Bach preludes, 0.38 full, are our weakest style).

### 60. Claude alone, without the draft model: a first look (2026-10-24)

**Question.** How well does the chat model analyse with no AnalysisGNN draft?

**Method.** Three held-out pieces (Bach WTC I prelude 22, Beethoven Op. 2 No. 1 iii, Grieg Op. 38 No. 7), the same 5 passages (121 bars) already scored in challenge 58, Opus 5.5 at medium effort, one run each. Three inputs, none with the draft (`eval.review --no-draft --source table|musicxml|pages`): our note table, the MusicXML file alone (read with the Read tool), or the engraved pages alone as images. The method text from the skill and the annotation format are given in every case.

| Input (bars weighted) | Key | Root | Chord and bass | Function | Full | Cost per passage |
|---|---|---|---|---|---|---|
| Draft alone | 0.79 | 0.78 | 0.56 | 0.67 | 0.45 | none |
| Draft + Claude (the pipeline) | 0.96 | 0.81 | 0.72 | 0.77 | 0.68 | about $0.35 |
| Claude + note table, no draft | 0.95 | 0.83 | 0.72 | 0.77 | 0.68 | $0.34-0.69 |
| Claude + MusicXML, no draft | 0.96 | 0.86 | 0.76 | 0.80 | 0.72 | $1.39-5.20 |
| Claude + page images, no draft | 0.96 | 0.76 | 0.61 | 0.69 | 0.58 | $0.37-1.69 |

Per piece (*full*, draft / pipeline / table / MusicXML / pages): Bach 0.41 / 0.58 / 0.53 / 0.59 / 0.20; Beethoven 0.42 / 0.66 / 0.68 / 0.74 / 0.70; Grieg 0.51 / 0.73 / 0.76 / 0.77 / 0.65.

**What it means.** On these three pieces the draft adds nothing measurable once Claude has the notes: Claude alone with the note table scores the same as the pipeline (0.68), and with the raw MusicXML slightly higher (0.72) at four to eight times the cost and up to three times the time, because it pages through the file over 3 to 10 turns. From page images it does worse (0.58), mostly on Bach, where it misreads the notes (0.20). Three pieces and one run each, against a run-to-run spread of about 0.04 per piece, so the table, MusicXML and pipeline rows are not distinguishable; only the page-image drop is clear. Worth testing on the full held-out sample before drawing conclusions about the draft model's role.

### 61. A plain chat, with no method, skill or tools (2026-10-25)

**Question.** What does a user get from plain Claude with the score attached, and nothing we built?

**Method (`eval/plain.py`).** The same three held-out pieces and bars as challenge 60. One message: the title, the whole MusicXML file pasted in, and "give a Roman numeral analysis of bars …", with only an example of the RomanText layout so the answer can be scored. A one-line system prompt, no tools, and an empty Claude Code config folder holding only the login, so no CLAUDE.md, memory or skills reach the model (checked by asking it to list its instructions). Sonnet 5.5 and Opus 5.5 at their default effort, two runs each.

| (127 bars, weighted) | Key | Root | Chord and bass | Function | Full |
|---|---|---|---|---|---|
| Plain Sonnet, run 1 / 2 | 0.69 / 0.84 | 0.59 / 0.67 | 0.45 / 0.47 | 0.50 / 0.58 | 0.39 / 0.42 |
| Plain Opus, run 1 / 2 | 0.95 / 0.96 | 0.85 / 0.84 | 0.62 / 0.65 | 0.71 / 0.73 | 0.58 / 0.62 |
| Draft alone (challenge 60) | 0.79 | 0.78 | 0.56 | 0.67 | 0.45 |
| Our pipeline, draft + Opus review | 0.96 | 0.81 | 0.72 | 0.77 | 0.68 |

Sonnet's first Bach answer wrote B-flat minor as `b:` (B minor in RomanText) and scores 0 as written; with the key code corrected it scores 0.16 on that piece and 0.42 overall, so the slip changes little. Plain Opus is weakest on Bach (0.46-0.54 against the pipeline's 0.58) and on Beethoven (0.51-0.63 against 0.66). Cost, estimated from tokens: $2.95 for the six Sonnet answers and $5.30 for the six Opus answers, each answer covering one piece's two passages, mostly for reading the whole MusicXML file.

**What it means.** Plain Opus gets the keys as right as the pipeline but the chords less often: 0.60 *full* against 0.68, which is about two runs' spread apart on three pieces. Plain Sonnet is below even the draft alone. What closes the gap is the method and the note table (challenge 60), not the draft model. Three pieces only.

### 62. A third Beethoven analyst counted (2026-10-27)

Challenge 59's source rule skipped 58 Beethoven sonata files with no Analyst line: `analysis_DT.txt` and, in 24 folders, an `analysis.txt` copy of it. Elsewhere `analysis_DT.txt` carries an Analyst line naming Tymoczko's team, so these are TAOM analyses too, and `eval/ceiling.py` now counts `analysis_DT.txt` as TAOM. Copies stay excluded. Beethoven goes from 13 pairs to 22 (4,377 bars) at fit 0.85: 0.78 function, 0.61 full (was 0.77, 0.57). All styles: 133 pairs, 10,228 bars, 0.83 function, 0.68 full, unchanged. Every other pair scores exactly as before. In `eval/any_expert.py` Op. 2 No. 1 iii now has two experts, which brings the first look to 7 pieces (382 bars): ours against any expert 0.92 function, 0.88 full, experts against any other expert 0.80, 0.71.

### 63. An "idea" level, and four scoring fixes (2026-10-27)

**Question.** Experts agree on the function of a chord far more often than on its exact label. How often do we agree with them at that level, and which misses are scoring faults rather than analysis faults?

**A new level, *idea*.** It accepts everything *function* does. It also accepts the same chord in another inversion, and two chords of the same tonic, predominant or dominant family in the same key, as in the engine's function bands (`engine/draft.py`: degrees 1 and 6 are T, 2 and 4 are PD, 5 and the leading-tone chord are D; applied chords, iii (which schools place in either the tonic or the dominant family) and the subtonic VII have no family). A six-four still matches only through the cadential rule, and an enharmonic diminished seventh matches its respelling. *Function* is unchanged as a level and stays the stricter figure.

**Scoring fixes**, found by reading the misses in the nine worst pieces by hand:
- Chord symbols (`Eb7`, `D9`, `Ab9/Eb`), which the skill asks for in impressionist music, were unreadable and counted as misses. They are now read as chord symbols.
- In bars with no declared length (cadenzas, and many chorale scores), every label was placed at the bar's start. Labels are now placed at their beat. Chorale analyses fit their scores better (about 0.82 to 0.91), so 12 more chorale pairs pass the 0.85 fit.
- The cadential six-four matched any root-position chord. It now matches only V of its own key.
- `Sounding` carries the chord's family.

**Experts against each other, 146 pairs, 10,552 bars:** function 0.83, idea 0.91, full 0.69 (chorales 0.97 / 0.99 / 0.87; Mozart 0.86 / 0.93 / 0.77; mazurkas 0.80 / 0.88 / 0.58; Beethoven 0.78 / 0.89 / 0.61).

**Our reviewed readings against their one expert** (43 pieces of the 2026-10-24 run): function 0.82, idea 0.91. **Against any expert** (7 pieces, 382 bars): function 0.92, idea 0.96; the draft alone 0.62 and 0.70; experts against any other expert 0.80 and 0.87. *Correction (challenge 66): this compared our reading against the better of two experts while each expert had only one other to agree with. Scored against the same others, ours is 0.85 function and 0.91 idea against the experts' 0.80 and 0.87.* Rescored with these fixes, the same reviews give *full* 0.72 on the core 13 pieces (was 0.71) and 0.61 held out (0.613, was 0.608), so the published figures stand.

**What it means.** At the *idea* level we agree with an expert as often as experts agree with each other, but so nearly does everything: the draft alone reaches 0.70, and experts 0.91. The level is useful for telling users what "agrees with an expert" means; it is too lenient to show improvement. Improvement is measured at *function* and *full*.

**Where the remaining misses come from** (nine worst pieces, read by hand):
- Single-line and lead-in bars, where the chord is placed late or the previous one carried over (Grieg Op. 65/1, Chopin Op. 56/3 and Op. 50/3, Beethoven Op. 14/1 iii).
- Notation slips, such as `I7` written for a dominant seventh on the tonic, a ninth of the wrong quality, or `ii/o42` for B–D–A.
- Harmonic rhythm that changes between a passage and its return (Op. 14/1 iii, bars 31–33 against 108–111).

These are fixable. Pedal points, chains of 6/3 chords and `III+` against V are matters of taste: the experts themselves differ on them.

### 64. Four reviewer rules from the worst pieces (2026-10-27)

**What we changed.** The hand reading in challenge 63 found habits of the reviewer that are not matters of taste. `skill/SKILL.md` now says:
- label a returning passage at the same harmonic rate;
- give a bar that opens with a single line or bare octaves its harmony from the downbeat, instead of carrying the previous chord over it;
- a bass held by the pedal or a tie stays the bass;
- the numeral must spell the notes (`V7/IV`, not `I7`, and the printed ninth).

**Test.** 7 of the worst held-out pieces and 3 that already scored well, on the same 2 passages per piece as the 2026-10-24 run, Opus 5.5 at medium effort. The baseline is that run, not a fresh one, so each piece carries one review's variation (about 0.04).

| (10 pieces, weighted by bars) | Function | Idea | Full |
|---|---|---|---|
| Before (2026-10-24) | 0.72 | 0.82 | 0.59 |
| With the rules | 0.75 | 0.86 | 0.62 |

The gains are where the habits were found. Chopin Op. 56 No. 3 rose from 0.66 to 0.83 function: `F#:I7` at bars 57-65 became `B:V7`. Grieg Op. 71 No. 4 rose from 0.83 to 0.92, and Grieg Op. 65 No. 1 rose from 0.59 to 0.80 idea, now with chords on the downbeats at bars 135-141. Four pieces fell by 0.01-0.03 function (Beethoven Op. 14 No. 1 iii, Op. 53 iii, Chopin Op. 50 No. 3, Kinderszenen No. 13), all within one review's variation. The three control pieces did not get worse. At Op. 65 No. 1 bars 29-32 the reviewer still hears one dominant where the expert labels each bass note; that is a reading, not a slip.

**Cost.** On the subscription, through `claude -p`; 20 passages.

**Follow-up on pieces not chosen for being bad.** Seven of the ten pieces above were chosen because they scored worst, and the rules were written from their misses, so that test favours the rules. Two more batches of 7 held-out pieces were picked by a fixed rule (every third remaining piece, offsets 0 and 1). On those 14 pieces (scored as in challenge 65): function 0.791 before, 0.788 with the rules; idea 0.926, 0.922; full 0.662, 0.658. No gain: the rules fix the habits they describe and leave other pieces as they were. They stay in the skill, but no improvement is claimed for them.

### 65. Same chord, other mode, counts as the same key (2026-10-28)

**What we changed.** Chopin Op. 41 No. 1 scored 0.04 *full* with 0.82 *function*. In bars 22-32 and 96-114 the DCML expert keeps the local key c-sharp minor and writes major-key chords in it (`I`, `V7/#vi`, `#vi`); we call the passage C-sharp major (`I`, `V7/vi`, `vi`). The notes are the same, so the key label was the only difference. `matches()` now counts the key as the same when the tonic is the same and the chord, its notes and its bass are identical, whatever the mode label says. The cause list in `eval/survey.py` follows it. `check_analysis` keeps the strict rule for students (owner's decision, 2026-10-28): a student's `C#: I` against an answer key's `c#: I` is still reported as a different key. Where the chords differ (`c#: i` against `C#: I`), the keys still differ.

| | Full before | Full after |
|---|---|---|
| Experts against each other, 146 pairs | 0.687 | 0.703 |
| Beethoven sonatas (23 pairs) / Chopin mazurkas (20) | 0.614 / 0.575 | 0.645 / 0.582 |
| Our review, core 13 pieces | 0.722 | 0.759 |
| Our review, held-out 30 pieces | 0.613 | 0.654 |
| Draft alone, held-out (91 pieces) | 0.424 | 0.447 |

Function and idea do not change. Against any expert (7 pieces) nothing changes. Chopin Op. 41 No. 1 goes from 0.04 to 0.44; the rest of its gap is bars 33-48, which the expert hears in F-sharp major and we hear as C-sharp major leaning on IV, a genuine difference of hearing.

**Where the remaining misses are** (held-out, 30 pieces, share of the labelled music, after the change): agree 0.66; different chord 0.09; bass or inversion 0.07; related chord 0.06; other key 0.06; cadential 6/4 or seventh with the same function 0.04; quality 0.02. Against experts' own losses (other key 0.075, inversion 0.049, different chord 0.046, related 0.040) our excess is in the chord and its bass, not the key. A third of our misses repeat the draft's; two thirds are the review's own choices. On the 24 pieces reviewed twice, 0.32 of the music is missed both times and 0.07 changes between runs, so most misses are systematic, not noise. Of the chord misses, about half have the right chord with its boundary placed differently from the expert's (a rough test: the expert's chord is next to ours, or ours next to theirs), about a tenth are one of our chords spanning three or more of the expert's, and about four tenths are a different hearing. We write 0.73 as many labels as the experts, and our chords account for 0.71 of the notes against the experts' 0.90.

### 66. Three audits of the scorer, and what they changed (2026-10-28)

**Why.** Rules written from our worst pieces did nothing on other pieces, and a hand reading of one bad score (Chopin Op. 41 No. 1) turned out to be a naming convention. Three independent reviews of the code (the scoring core, the expert pairing, the data pipeline) looked for logic that makes published numbers wrong. Each finding below was reproduced before it was fixed.

**What was wrong, and the fix.**
- *Bar numbers after uncounted bars or repeated numbers.* The score reader renumbers such scores 0/1..N, but DCML labels keep the printed number, so every label after the first such bar landed in the wrong bar. For renumbered scores the DCML converter now places labels by their position in the piece (`quarterbeats`); elsewhere it keeps the printed number, because positions drift after a cadenza whose written note values do not add up to DCML's count (Liszt Sonetto 104). Reference fit: Beethoven Op. 57 ii 0.65 → 0.93, Op. 110 ii 0.64 → 0.91, three Chopin mazurkas 0.66-0.71 → 0.89-0.91. Three Liszt pieces that crashed are now scored.
- *First and second endings in When in Rome files.* `m8a` and `m8b` were read as one bar, so every later bar was off by one per ending. They are now placed in the score's order, including endings several bars long. Of 52 survey files with lettered bars, 26 fit their scores better and none worse (Mozart K. 283 ii 0.63 → 0.88, Beethoven Op. 18 No. 4 i 0.65 → 0.92).
- *Beat units in 3/8, 6/4 and similar meters.* RomanText (as music21 reads it) counts dotted beats there; our score reader counts the written unit. Expert labels in those meters were placed too early. They are now converted, unless a file itself counts the written unit (one does). Mozart K. 281 ii 0.85 → 0.91; Dichterliebe 16 0.77 → 0.83.
- *A label on a beat a bar does not have* raised an error and dropped the whole piece. It is now placed at the bar's end, which gives it no length.
- *DCML conversion.* Cadential six-fours (`V(64)`) lost their six-four and were read as a root-position V; augmented sixths lost their lowered note; minor-key local keys on vi and vii were raised; applied chords three levels deep were dropped. All are now converted. Mean fit of the DCML labels to the notes, 71 pieces: 0.862 → 0.878.
- *The cadential six-four rule* matched any chord on the dominant, including a minor v. It now needs a major V in the same key.
- *Stale numbering.* Beethoven Op. 2 No. 1 i had `bar_offset` 1 from an older score; the score now numbers its pickup 0, so the expert labels were one bar off (fit 0.50; 0.89 with offset 0). The cached review was made under the old numbering, so it is set aside (`.json.stale-numbering`) and the piece leaves the reviewed totals until it is reviewed again. Dichterliebe No. 10's labels were also one bar off (fit 0.55 → 0.92).
- *Expert pairs.* Three Beethoven movements had one source under two file names, so the same pair was counted twice. One file per source is kept.
- *The any-expert comparison* gave our reading the better of two experts while each expert had one. It now also reports ours against the same others as each expert, the comparable figure.

**Figures after the fixes** (2026-10-24 reviews, unchanged):

| | Before (challenge 65) | After |
|---|---|---|
| Experts against each other, full / function / idea | 0.703 / 0.827 / 0.908 (146 pairs) | 0.711 / 0.830 / 0.909 (151 pairs, 10,684 bars) |
| Same, without chorales (73 pairs) | | 0.693 / 0.815 / 0.900 |
| Same, averaged per pair / per style | | full 0.79 / 0.76 |
| Core, draft → review, full | 0.53 → 0.76 (13 pieces) | 0.57 → 0.76 (12 pieces, Op. 2 No. 1 set aside) |
| Held out, same 30 pieces and bars, draft → review, full | 0.45 (91 whole pieces) → 0.65 | 0.48 → 0.67 |
| Held out, draft over all pieces | 0.447 (91) | 0.453 (94) |
| Any expert, ours vs same others / experts, function | 0.92 (unfair) / 0.80, 7 pieces | 0.79 / 0.73, 6 pieces (229 bars) |
| Same, idea | 0.96 (unfair) / 0.87 | 0.86 / 0.80 |

The expert figure is weighted by bars, so Beethoven, with long movements, counts for more than its share of pairs; averaged per pair it is 0.79 full. The chorale pairs (78 of 151, TAOM against BCMH) agree unusually closely and may not be fully independent, which is not yet checked. The any-expert figure now rests on 6 pieces and 229 bars.

**Where the misses are, re-measured** (30 held-out pieces): agree 0.68; inversion 0.07; different chord 0.07; related chord 0.06; other key 0.06. On the 24 pieces reviewed twice, 0.30 of the music is missed both times and 0.07 changes. Of the chord misses, 0.47 are the right chord with its change placed elsewhere, 0.12 one of our chords spanning three or more of the expert's, 0.41 a different hearing. Our chords fit the notes at 0.71, the experts' at 0.91. The four reviewer rules (challenge 64), on the 14 pieces not chosen for being bad: function 0.794 → 0.792, full 0.675 → 0.672.

**Not fixed.** In When in Rome pickup bars, beats count from the start of a full bar while our readings count from the pickup's start (one bar per piece at most). Beat tokens such as `b2.67.5` are read as chords (13 in the corpus). The survey's list of which label pairs cause each miss pairs some labels with the wrong span; its totals are unaffected.

### 67. Second readings: the feature and how it will be judged (2026-10-28)

**The feature.** Experts disagree on about 0.30 of the music, mostly in the same few places: a modulation against a tonicization, an inversion or a pedal, a cadential six-four or a seventh, iii's family, the mode. Instead of chasing one expert there, the analysis can name the other reading. A new annotation type, `alternative` (bars, plus the other reading in numerals, e.g. `F#: V7 I`), is drawn as a dotted bracket under the numerals labelled "or …", with a callout to the commentary paragraph that explains both readings. `skill/SKILL.md` asks for one only where a teacher would accept the second reading, at most about one per phrase. Scorers read only `harmony` items, so an alternative never counts toward agreement. The deployed server rejects the new type until it is redeployed, so skill, server and plugin ship together.

**How it will be judged, fixed before any run.**
- *Isolated.* `eval.review --second-readings --start-from opus-medium-2026-10-24` adds alternatives to the existing first answers; the chords are kept exactly as they were (only `alternative` items and new callouts are taken from the second reply), so no review noise enters.
- *Measures* (`eval/second_readings.py`): the share of alternative spans where the expert's reading differs from our main reading over at least a quarter of the span (function level); the share where the expert holds the alternative itself; coverage of our disagreements with the expert; flagged bars per 100.
- *Pass:* the first share beats both baselines at the same span lengths, random spans and spans around the draft's least confident chords, on at least 14 development pieces; flags stay rare (no more than about 10 bars per 100).
- *Locked final set:* `eval/locked-set.txt`, 22 held-out pieces fixed now (every second piece, sorted by id, of the 44 held-out pieces with label fit 0.85 or more that have not been reviewed). It is run once, at the end, with the single-pass production skill.
- *Training overlap.* All 21 When in Rome held-out pieces and the 3 chorales are in AugmentedNet's test split (checked against `AugmentedNet/data/wir.py` and `wirwtc.py`; the WTC preludes are listed there under another folder name), so none was in the draft model's training data.

### 68. Second readings, first batch: not yet (2026-10-28)

**Run.** The 7 held-out pieces of the first fixed-rule batch (challenge 64), 2 passages each, `--second-readings --start-from opus-medium-2026-10-24`: one extra call per passage on the subscription, chords unchanged.

| | Result | Pass rule |
|---|---|---|
| Alternatives | 37 over 283 bars | |
| Flagged bars per 100 | 36 | about 10 or fewer: **fails** |
| Spans where the expert reads differently from us | 0.43 | beat both baselines |
| Random spans of the same lengths | 0.31 | beaten |
| Spans around the draft's least confident chords | 0.60 | **not beaten** |
| Spans where the expert holds our alternative | 0.73 | (no baseline yet) |
| Our disagreements with the expert inside a flagged span | 0.44 | |

**What it means.** The alternatives are musically sensible (a cadential six-four against V, F-sharp major against C-sharp major leaning on IV in Chopin Op. 41 No. 1, a pedal under V), and when the reviewer names one the expert often holds it. But it names too many, about 2.6 per 24-bar passage, and it chooses where less well than the draft's own uncertainty does. "About one per phrase" allows too much. The 0.73 has no baseline yet: a long span easily contains one of the alternative's chords. Next: ask for far fewer (only where the reviewer itself would hesitate), and give it the draft's least confident spots and runner-up readings as places to look; test on the second batch of 7. The locked set stays untouched.

**Beethoven Op. 2 No. 1 i re-reviewed** with the skill text of 2026-10-26 (before the rules of challenge 64 and the alternative), whole piece, numbering fixed. Draft 0.47, review 0.78 full; reading fit to the notes 0.91 (the stale review fitted at 0.47). It is back in the core totals: core review 0.759 full over 13 pieces, draft 0.570.

### 69. Second readings, second batch: rarer, still not where it should be (2026-10-28)

**What changed after challenge 68.** `skill/SKILL.md` now asks for an alternative only where the reviewer itself hesitated, usually none and rarely more than one in 24 bars. The second-readings prompt lists the draft's four least confident chords in the passage, with the draft's runner-up, as places to look. The measure gained a chance baseline for "the expert holds our alternative": the same alternative placed at random spans of the same length. On batch 1 that baseline is 0.38, against 0.73 for the reviewer's own spans.

**Run.** The second fixed-rule batch of 7 held-out pieces (challenge 64), 2 passages each, chords unchanged.

| | Batch 1 (challenge 68) | Batch 2 | Pass rule |
|---|---|---|---|
| Alternatives | 37 over 283 bars | 12 over 269 bars | |
| Flagged bars per 100 | 36 | 12 | about 10 or fewer |
| Spans where the expert reads differently from us | 0.43 | 0.58 | beat both baselines |
| Random spans | 0.31 | 0.37 | beaten |
| Spans around the draft's least confident chords | 0.60 | 0.92 | **not beaten** |
| Expert holds our alternative / at random spans | 0.73 / 0.38 | 0.50 / 0.34 | |
| Our disagreements inside a flagged span | 0.44 | 0.12 | |

**What it means.** The revision made the alternatives rare enough and better aimed than chance, and when one is named the expert holds it more often than chance. But the draft's own least confident chords point to the places where we and the expert disagree far better than the reviewer's choice does (0.92 on batch 2, from 12 spans). The reviewer was shown those spots and mostly chose others. The rule fixed in challenge 67 is not met, so the locked set stays unrun.

Two cautions: batch 2 rests on 12 alternatives, and "the expert reads differently from our main reading" is a disagreement with one expert, not a place where experts split among themselves. The next design to test lets the draft choose where (its least confident spans) and the reviewer decide whether a second reading there is one a teacher would accept, and write it.

### 70. Second readings: the pass rule changes before the next run (2026-10-28)

**Why.** The rule of challenge 67 asks whether an alternative falls where our main reading differs from one expert. That rewards flagging our own mistakes, not places where experts split, and it favours the draft's least confident spots by construction, since the review is built on the draft. The feature's purpose is the second: name the places where experts themselves hear the music differently.

**The rule from now on, fixed before the run.**
- *Pieces:* the reviewed pieces with two or more independent expert analyses at fit 0.85 or more (the any-expert pieces: chorales 269 and BWV 38.6, Beethoven Op. 2 No. 1 i, Op. 2 No. 1 iii, Op. 53 iii, Chopin Op. 6 No. 2, Mozart K. 310 i; 382 bars), with second readings added by the current guidance (challenge 69) to their existing first answers.
- *Main measure:* the share of alternative spans where the experts disagree with each other (function level) over at least a quarter of the span, against random spans of the same lengths in the same bars. The draft's least confident spots are reported but no longer decide.
- *Second measure:* the share where at least one expert holds the alternative, against the same alternative at random spans.
- *Pass:* both shares beat random by a clear margin, with flags still rare (about 10 bars per 100 or fewer). With so few spans this is a first look, not a verdict; the locked set stays unrun until a version passes.

### 71. Second readings against expert splits: right readings, wrong places (2026-10-28)

**Run** (rule of challenge 70). The 7 pieces with two or more independent experts, 382 bars, second readings added to their existing first answers with the guidance of challenge 69. `eval/second_readings.py --experts-split` scores them against the music where the experts disagree with each other. The single-expert mode now counts only reviewed bars, which moves the draft baseline of challenges 68 and 69 from 0.60 and 0.92 to 0.51 and 0.75.

| | Ours | Random spans | Draft's least confident |
|---|---|---|---|
| Spans where the experts disagree with each other | 0.29 | 0.32 | 0.29 |
| Spans where an expert holds our alternative | 0.71 | 0.34 (same alternative) | |

17 alternatives, 8.4 flagged bars per 100; they cover 0.07 of the music where the experts split.

**What it means.** The reviewer does not know where experts split: its alternatives land there no more often than chance. But the alternatives themselves are good readings: an expert holds one 0.71 of the time, twice the chance rate. The feature as specified (marking where experts split) fails its rule; what holds up is narrower: when the reviewer names a second reading, a published expert usually reads it that way. 17 spans is a first look.

**Checked by hand, the 0.71 is weaker than it looks.** Of the 17, 7 sit where the experts agree with each other, every expert "holds" the alternative, and our main reading agrees with them too at the function level (Op. 2 No. 1 i bars 9-10 `c: i`, bar 34 `IV ii6`; Op. 2 No. 1 iii bars 18-23; Op. 6 No. 2 bars 23-24). The alternative there renames the same chords (a key named differently, chords that already appear in the span), so "holds" counts restatements, not second readings. Only 5 of the 17 sit where the experts split. The check needs to require that the alternative differ from our main reading where an expert follows it.

**Page layout** (owner's request): each chord of the alternative is printed under the chord it replaces, in the same figures as the numeral row, with no "or"; `-` leaves a chord as it is. The label gives one chord per harmony label in the range, with an optional key first; when the counts do not match, the chords are spread evenly under the bracket.

### 72. Second readings of key, by rule (2026-10-28)

**Why.** The reviewer could not tell where experts split (challenge 71). The biggest single cause of expert disagreement is naming the key: 7.5% of all music, mostly a short modulation against a tonicization. Two plain rules look for those places in any analysis, with no model.

**The rules** (`engine/key_readings.py`):
- *A short key area:* a key that lasts two bars or less before the next key change, with a different tonic from the key before it. Its other reading is the same chords as applied chords in the key around it (`Bb: V7 I` in E-flat becomes `Eb: V7/V V`).
- *A run of applied chords:* three or more chords applied to the same degree (`ii7/V V7/V viio7/V`), optionally ending on that degree. Its other reading is a short modulation to that key (`Bb: ii7 V7 viio7 I`). A target chord with a seventh ends the run, since it is a new function.
- Flat minor areas on the sixth and seventh degrees of a minor key are spelt `bvi`, `bvii`, because a lowercase vi or vii in minor is read as raised.

**Chosen on half the expert pairs, checked on the other half** (`eval/key_readings.py`). Each pair is used both ways: the rules run on one expert's analysis, and a flag is a hit when the other expert names a different key over at least a quarter of it. Thresholds were picked on the first half (alternate pieces by name) to cover the most key disagreement with at most 10% of the music flagged and hits at least twice chance; the second half was then run once.

| | First half | Second half |
|---|---|---|
| Flags | 447 | 409 |
| Hits | 0.38 | 0.41 |
| Random spans of the same lengths | 0.15 | 0.16 |
| Key disagreements covered | 0.30 | 0.28 |
| Music flagged | 9.5% | 9.5% |

Runs of three applied chords are the strongest single signal (0.64 against 0.26 on the second half, as first measured).

**On our own reviews** (2026-10-24 run, rules applied after the fact). They fire rarely: 13 flags in 2,412 reviewed bars, because the reviewer already writes short excursions as applied chords, as the skill asks. Where they fire, the expert names the key as the alternative does 0.54 of the time, against 0.14 for the same alternative at random spans. On the 7 pieces with several experts there are only 3 flags. The check of "an expert holds the alternative" now uses the key alone when the alternative names one, so a respelling of the same chords no longer counts.

**Page.** The alternative's chords are printed under the chords they replace, and the key name sits on the bracket line just before it starts, where it does not collide with function brackets.

**Not done.** The rules cover key naming only (inversions, six-fours and sevenths are the next causes of expert disagreement). How the reviewer should use the flags (keep, drop, explain) is not built or tested.

### 73. Doing in code what has a rule (2026-10-28)

**Why.** The owner asked that anything about music theory with a fixed answer be done by scripts, not by the chat model, with no loss of accuracy. A survey of what the skill and server ask the model to do found about 13 of 44 tasks with a fixed answer once the model has chosen the chord, bass or non-chord tones, about 24 where a rule can propose or check but the model decides, and about 7 that are judgement. The log's evidence sets the line: rules win when they compute from the model's own choices or check them (mode recovery, challenge 1; parallels, challenges 36-38), and lose when they override a hearing (the bass rule, challenge 11).

**Done, none of which changes what the model decides:**
- The draft's PART-WRITING CHECK lists only findings inside the requested bars (`part_writing.as_text` takes `first`, `last`); before, a passage carried the whole score's findings, up to about 3,700 characters.
- The renderer sends back an `alternative` whose label has a different number of chords from the harmony labels in its range, instead of spreading the chords evenly under the wrong ones (`engine/annotate.py` `check`).
- The server's piano-reduction offer uses the skill's rule, more than four staves.

**Measured, free.** `harmony.mismatches` (a label against the notes that sound under it) flags 167 of 3,265 reviewed labels that can be scored (2026-10-24 reviews). Flagged labels agree with the expert on key, chord and bass 37% of the time, against 82% for unflagged ones; "bass never lowest" flags agree 23%, "seventh never sounds" 10%, "half the notes missing" 65%. So the flags point at real mistakes, which challenge 16 had not shown (it measured score change only).

**Not done.** Sending the method text once per connection instead of with every draft: some hosts may never show server instructions to the model, so it could lose accuracy. Part-writing marks drawn by code: the skill sandbox cannot run the check. Rules that pick the reading (pedals, cadence types) stay out unless measured.

### 74. The label check again, reworded: harmless, with rare large rescues (2026-10-28)

**What changed from challenge 16.** The same script flags, the same design (`--selfcheck --start-from`, so only the check differs), but the prompt now says flagged labels are usually wrong and asks the reviewer to read the notes and name the chord they make, keeping its label only when it can name the exact note that explains the contradiction (the held pedal note, where the missing tone is implied, the beat where the seventh arrives). Challenge 16's reviewer changed the chord on only 4 of 29 flagged labels.

**Run.** Held-out pieces with the most flags, starting from the 2026-10-24 reviews: 7, then 10 more. 31 passages, $11.06.

| | Full: before → after |
|---|---|
| First 7 pieces | 0.622 → 0.639 |
| Next 10 pieces | 0.641 → 0.643 |
| All 17 | 0.633 → 0.641 |
| All 17 without Chopin's Mazurka Op. 56 No. 3 | 0.643 → 0.643 |

The reviewer now changes about a third of flagged labels. Most of the gain is one passage of the mazurka (0.474 → 0.609, keys included). Grieg Op. 38 No. 7 and Op. 71 No. 4 gained about 0.02. The largest drop is Beethoven Op. 10 No. 2, 0.705 → 0.681, about the size of review noise; nothing else fell more than 0.013.

**Decision.** It passes the owner's rule (no worse beyond noise), as insurance against a passage that has gone badly wrong rather than a general gain. Planned for the product as warnings in the render reply, never rejections; not built yet.

### 75. Held-open GET streams, and alerts that say so (2026-10-30)

**Problem.** From 27 October production billed 7,300-10,800 instance-seconds a day against about 300 before, with a few dozen tool calls. The cost guard emailed on the 27th and was not seen. October still ended near the free tier (92,693 instance-seconds, 103% of it, about US$0.16), but a full month at that rate would be about US$10-12.

**Cause.** `GET /mcp` with `Accept: text/event-stream` opens the transport's standalone event stream, which the server held until Cloud Run's 300 s timeout. A directory health checker (`ado-p5-health/1`) sends one about 25 times a day, and `node`, `undici`, Bun and `curl` clients did the same. Reproduced locally: 200 and still open after 8 s. Log 21's fix covered only Claude's `subscriptions/listen` POST.

**What we did.**
- `server/app.py` answers `GET /mcp` with 405 and `Allow: POST` before the MCP app sees it, as the protocol allows for servers without the stream; `/mcp/` redirects to it. `tests/test_server_process.py` starts the real server and checks the refusal, a tool list over POST and `/health`.
- A log-based metric, `held_open_requests` (requests of 250 s or more), and an alert on more than two in an hour (`server/monitoring/`). Over October it would have fired on the first day of both leaks.
- `tools/cost_report.py` prints billed instance-seconds per UTC day and service from Cloud Monitoring and the month against the free tier.
- `--max-instances=1` (owner's choice): the worst case for a stuck instance halves, to about US$145 a month at list price; two calls at once still run.

**Result.** To be confirmed from the next day's metric: production back to a few hundred seconds a day, and the health checker's GET refused in under a second.

### 76. Three crashes from real ChatGPT files in one day (2026-10-30)

**Problem.** The first ChatGPT users hit three different server errors on 30 October, none of them covered by a test: a scanned PDF read without a time signature (the note list header came out as `ts=`, which `decode` and the model runner could not read back); a band score whose baritone and tenor saxophones use `<octave-change>` (Verovio writes a wrong `trans.diat`, e.g. -16 for -12, so pitches came out as `F########2` and the model refused them; tenor notes were silently spelled A#3 for Bb3); and a piano transcription that writes voice 1 twice in a bar after a `<backup>` (Verovio chains the two passes into one 8-beat voice; 112 of 118 bars had notes past the barline).

**What we did.** An empty meter is valid in the note list and the runner (partitura falls back to 4/4); the diatonic step of a transposition comes from its semitones; before Verovio reads a score, a voice whose notes after a `<backup>` would overlap its own earlier notes gets its own number. The `.mxl` container is read as XML, and broken archives, oversize members and empty durations are refused or tolerated as before. When a call fails on our side the chat is told to apologise and give support@sheetmusicanalysis.com with an 8-character reference that finds the log line.

**Result.** All three files draft on staging and production. Old against new on the 64 scores in `tests/data`: 63 read identically, the other is a malformed bar that now lands inside the bar. `tools/diff_check.py`: render 28, export 6, part writing 80 inputs unchanged; the 122 awkward-input tests pass.

### 77. Cold starts: reading the server's own files ahead (2026-10-30)

**Problem.** Instances took 11-20 s to start, sometimes 40-95 s, and twice after deploys over 240 s, where Cloud Run's startup probe dropped them. Pairing 355 starts by instance id showed the delay was before `server/app.py` finished importing (68-137 s of 142 s, 5-8 s after): the first reads of about 1,500 small files from the image, the cost log 49 measured for the model.

**What we did.** The model's read-ahead moved to `engine/read_ahead.py`; the image build records the files the server opens while importing (`python -m server.app --list-files`), and a new instance reads them 16 at a time while it imports. Storage and Cloud Trace imports moved to the top of `app.py` so the recording sees them. The startup probe allows three 240 s attempts.

**Result.** Staging starts 2.9 s twice (imports 2 s, read-ahead 1,543 files in 0.7-1 s); production 3.7 s and 4 s after deploys, against 142 s and a failed 240 s earlier the same day.

### 78. Counting users without tracking them (2026-10-30)

**Problem.** The logs could not tell how many people used the app: each call had a platform but nothing per person, and IP addresses are OpenAI's servers.

**What we did.** Each call logs the names (never the values) of the request headers and `_meta` fields, and for ChatGPT a 16-character HMAC of its anonymous user id (`_meta["openai/subject"]`) under a random key made each UTC day and kept in the bucket under `keys/`, which the lifecycle rule deletes; bucket soft delete is turned off so deleted keys, scores and pages are gone. `tools/usage_report.py` prints distinct users per day. The privacy page says so. A failure in this step is logged and never fails the call.

**Result.** On staging the same id gives the same code within a day and a different one for another id, with no values in the log. Before the change, distinct pieces suggest about four real users, all through ChatGPT on 30 October.

### 79. An eight-reviewer pass, and why defects kept reaching users (2026-10-30)

Eight independent reviewers read the whole project and found about 40 issues, most reproduced: unbounded downloads and `.mxl` decompression (1.5 MB became 3 GB), slow senders holding a request slot for 300 s, redirects to private addresses, 24-bit score ids, reversed bar ranges bypassing the 32-bar limit, blocking work on the event loop, and correctness bugs in ties, key changes, compound meters, corrections and previews. Fixed the same day: downloads stream with a 10 MB cap, a 30 s deadline and every redirect re-checked; ids are 64-bit; reversed ranges are refused; slow work runs in threads; staging gets its own service account; the five newest server images are kept for rollback. Daily limits stay global by the owner's choice.

A retrospective over the past sessions found the main cause in process, not skill: the owner's review rules (old-against-new checks, awkward inputs, review before merge, deploy rules) lived in a memory folder that sessions started from the parent directory never loaded, the repo had no `CLAUDE.md`, deploys ran from whatever tree was checked out, CI had never run because `main` was not pushed, and the test corpus held only well-edited scores, so every production failure was found by a user or the bill.

Released on its own as plugin 1.3.0, ahead of the engine fixes, so the held-open fix is not held up. Moving slow work to threads let two requests run music21 at once, and music21 is not thread-safe; score work now takes turns in one queue (a second request waits for the first, in order), shown by a test where two simultaneous calls never overlap. A Sonnet review found two student-answer checks still parsing on the main loop; they now queue too. The model runs inside the queue, so a cold model load (about a minute) makes other requests wait; at today's traffic that is accepted. PDF reading stays outside the queue: it does not use music21, already runs one at a time, and takes 20–310 s in production. A test that builds the skill and starts each script found `model_notes.py` failing on this release (a table imported from the model-only module); the table moved.

### 80. Eleven engine defects from a review, each with a check across the test scores (2026-10-30)

A reviewer reproduced eleven defects in the analysis engine. Each now has a check that runs over every awkward score in `tests/test_awkward.py` (or the real scores in `tests/data/piano`), written to fail first:

- **The model lost notes.** A tie into another voice left a waiting note that later swallowed an unrelated one. The Mayer quartet fixture lost one note; every awkward score now gives the model exactly its notes.
- **Key changes were dropped.** Each bar now has its own key signature, written as `ks=` on the note list's bar line (old lists read as before) and passed to the model at that bar. Dvorak 9/2 bar 91: four trills played their own note as the upper note; they now reach A♯5 and C♯6. The key is also taken from a non-transposing staff: Weber's Concertino, with the B♭ clarinet on top, read as 1 flat instead of 3.
- **Chords on a third of a beat were missed.** The draft rounded beats to 1.33 or 1.67, which match no note, so the part-writing check found no chord there, and a label copied from the table at 1.67 was read as 157/94 of a beat, just past its chord's notes. Beats are now exact and rounded only in the text, which is unchanged, and a beat given to two places takes the note within 1/200 of a beat of it. Before the fix, chords missed their notes in 6 of 11 awkward scores.
- **The student check stopped** when a label came before the draft's first chord, or the draft had none. Such labels are now listed as unchecked.
- **Piano reduction crashed** on Weber's Concertino bar 1, where a direction's offset runs past 3/4. A bar is now never longer than its time signature.
- **The notes table gave the wrong beat** when the meter changes (it took the last bar's), and range text from bar 1 left out the pickup the note list includes (6 of 12 awkward scores). Bars that change meter or key now say so.
- **False ledger-line advice for transposing parts.** Mozart 41's contrabasses and horn in C, and Dvorak 9's clarinet in A and horns, were judged at sounding pitch: 25 of 41 Mozart lines and 4 of 13 Dvorak lines were false and are gone, and one Dvorak clarinet run shrank from bars 1–14 to 1–3; no other score changed.
- **Playback of a bar range** let in the next bar's first notes whenever a note was held over the barline (6 of 12 awkward scores). It now stops at the last bar's barline. A range with no notes of its own plays nothing instead of the whole piece, and an unknown tempo word gets a plain message.
- **Malformed note-list headers** (`div=0`, `ts=4/0`, `ts=3`) gave internal errors or were accepted; they are now refused with a reason.
- **Typed answers** such as "V 4/3", "V6 5" and "vii⁰⁷" now read as V43, V65 and viio7. The differential check on typed answers changed 5 of 191 inputs, all from a question to the right reading. Part writing, PDF warnings and export did not change. Rendering changed only for the Mozart K. 458 example, whose analysis gives beats 2.67 and 1.17: the V in bar 7 and the NT in bar 5 now sit on their notes (checked on the page).

Known limits: the Brahms Frühlingstrost fixture still fails in the model because its last bar's notes run past the bar. The server's description of the note-list format now mentions `ks=`.

### 81. A second-model review of the merged branch (2026-10-30)

A Sonnet review of the branch reproduced two regressions that our tests had missed:

- **The Claude skill could not start two of its five scripts.** The RomanText export now borrowed a beat helper from the comparison module, which imported a table from the model-only module that is left out of the skill. `model_notes.py` and `render_analysis.py` stopped with "No module named engine.draft". The table moved to the comparison module, and a new test copies the skill as it is built and starts every script; it failed on 2 of 5 scripts before the fix.
- **The student check compared triplet beats against the wrong chord.** The draft now keeps exact beats (entry 80), but a student who typed 2.33, as the table prints it, was placed just before the chord at 2⅓ and compared with the previous one. A student's beat is now moved onto the note within 1/200 of a beat, the same rule the drawing uses.

Also from the review: an .mxl archive's index file is now size-checked like the score inside it. MIDI export now plays repeats and first and second endings in order (it played the written order); the note list still uses written order. Of the 61 test scores, exactly the 15 with repeat signs changed.

More music21 work runs on worker threads; since the queue of entry 79, score work takes turns, so two threads no longer use music21 at once. One reported flaky test did not fail again in the same combination (259 passed).

### 82. Our setup against plain Claude, after the fixes (2026-10-31)

**Question.** How does the full setup compare with plain Claude, and did entries 80-81 change it?

**Method.** The three held-out pieces and 127 bars of challenge 61, all scored by the same code with the corrected scorer (entry 66). The plain answers are the saved ones from challenge 61, rescored. The new run drafted again from the fixed note lists and reviewed with Opus at medium effort, as on 2026-10-24. Every Claude call in `eval/` now runs in a fresh config folder holding only the subscription login, with no API key, CLAUDE.md, memory, plugins or skills (checked by asking the model to quote any it had: none). Before this, reviews and the judge ran with the owner's normal config folder.

| 127 bars, 3 pieces | Full | Function | Key | Per piece, full (Bach / Beethoven / Grieg) |
|---|---|---|---|---|
| Plain Sonnet, run 1 / 2 | 0.41 / 0.44 | 0.51 / 0.59 | 0.69 / 0.84 | 0.00-0.16 / 0.46-0.47 / 0.54-0.55 |
| Plain Opus, run 1 / 2 | 0.62 / 0.66 | 0.72 / 0.73 | 0.97 / 0.96 | 0.50-0.58 / 0.60-0.70 / 0.66-0.69 |
| Our setup, 2026-10-24 | 0.70 | 0.77 | 0.96 | 0.58 / 0.72 / 0.73 |
| Our setup, after entries 80-81 | 0.71 | 0.79 | 0.96 | 0.59 / 0.79 / 0.70 |

Rescoring moved plain Opus from 0.58-0.62 to 0.62-0.66 and plain Sonnet from 0.39-0.42 to 0.41-0.44. The draft alone barely moved with the fixes (Beethoven 0.45 to 0.48 over the whole piece, Bach and Grieg unchanged). Estimated cost of the new review: about $5 of subscription use.

**What it means.** Our setup leads plain Opus by about 5-9 points and plain Sonnet by about 27-30. One run of ours against two of each plain model, on three pieces, with a run-to-run spread of about 0.04 per piece: the Sonnet gap is clear, the Opus gap is suggestive but not yet a published figure. The 30-piece comparison would settle it.

### 83. A thumbs up or down on the ChatGPT card, and a dark theme (2026-10-31)

At the owner's request, the analysis card asks "Was this analysis helpful?" once per ChatGPT conversation, at its third analysis. The server counts analyses per conversation under the conversation ID scrambled with the daily key (`chats/`, deleted after a day) and sets a flag in the result's card-only metadata, so the chat model does not see it. The thumbs call `rate_analysis`, a tool only the card can call, which logs the answer with the daily user code; the card says thanks only when the call succeeds. The card keeps its approved address, so a held ChatGPT update still finds it. The card now follows ChatGPT's light or dark theme; the score page stays white. The privacy page lists both new records. Not yet tried in ChatGPT itself (staging needs a login); expected answers are few, since the busiest day so far had 13 ChatGPT analyses.

### 84. Multi-bar rests drawn compact again, with every bar still counted (2026-10-30)

The fix that kept every bar of a multi-bar rest wrote the rest out as separate empty bars, so a "9" rest became nine bars across the page. The owner prefers the compact sign. The drawing now keeps it, and the score index counts a rest of N as N bars, each with its own number. Bar positions in the file (used by export, corrections and PDF warnings) and bar positions on the page (used to pick a passage to draw) are now kept apart, because they differ after a compact rest. A label, a student's label or a PDF warning on a bar inside a compact rest has nowhere to go, so that drawing writes that one rest out bar by bar, as before.

Checked on the 19 of the first 5,000 PDMX files that have a multi-bar rest: the index (numbers, positions, lengths, notes), the export of a label on every bar and the correction note list are identical to the expanded version for all 19. On the page, a label inside a rest draws the rest out with the label under its bar, and a PDF warning on bar 52 shades bar 52.

A Sonnet review found that marks reaching "N bars ahead" (hairpins) still counted the file's bars, so a crescendo across a compact rest ran 4 beats too long in playback and in the drawing's hairpin spacing. Where a rest stays compact, those counts are now rewritten in drawn bars, so the drawing, the hairpin spacing and playback agree; a test plays a crescendo across a 3-bar rest exactly as with every bar drawn.

Not fixed: a correction that puts notes into a bar inside a multi-bar rest is lost, before and after this change, because the reader skips those bars of the file.

### 85. Plain Claude against our setup, both given a printed PDF (2026-10-31)

**Question.** Entry 82 gave both sides the MusicXML. With a PDF instead, the way most users arrive, how do plain Sonnet, Opus and Fable compare with our setup, and at what cost?

**Method.** The three held-out pieces and 127 bars of entry 82, as scans of modern published editions from IMSLP (1963-1977), cut to the pages holding those bars. Plain: the PDF attached, the Read tool only, a one-line system prompt and the RomanText question of challenge 61. Ours: our reader's MusicXML of the same PDF, drafted, and each passage reviewed by the same model. Every call at the model's default effort, in a fresh config folder on the subscription, one run each. Our reading: Bach 24 of 24 bars with 91% of notes but no time signature; Beethoven 76 bars for 74 (a misread bar line moves every later bar number by 2); Grieg 53 of 53 with 98% of notes. Ours is scored as read, and "lined up": each read bar matched back to the source bar with the same notes, so a label is not marked wrong only for sitting under a shifted bar number.

| 127 bars, 3 pieces | Full | Function | Key | Tokens | Cost US$ (estimated) | Per piece, full (Bach / Beethoven / Grieg) |
|---|---|---|---|---|---|---|
| Plain Sonnet | 0.23 | 0.28 | 0.60 | 32k | 0.18 | 0.00 / 0.12 / 0.43 |
| Ours, Sonnet, as read / lined up | 0.49 / 0.56 | 0.56 / 0.64 | 0.89 | 284k | 1.16 | 0.12 / 0.41-0.58 / 0.73 |
| Plain Opus | 0.52 | 0.64 | 0.96 | 46k | 0.63 | 0.22 / 0.64 / 0.54 |
| Ours, Opus, as read / lined up | 0.53 / 0.65 | 0.60 / 0.72 | 0.92-0.95 | 321k | 3.24 | 0.24 / 0.48-0.78 / 0.70 |
| Plain Fable | 0.26 | 0.32 | 0.77 | 222k | 9.87 | 0.07 / 0.26 / 0.34 |
| Ours, Fable, as read / lined up | 0.46 / 0.56 | 0.56 / 0.68 | 0.92 | 377k | 8.71 | 0.18 / 0.41-0.65 / 0.64 |

**What it means.** From a PDF, our setup roughly doubles exact agreement for Sonnet (0.23 to 0.49-0.56) and Fable (0.26 to 0.46-0.56). For Opus the gain is in the chords themselves (0.52 to 0.65 lined up) but the misread Beethoven bar line cancels it as read (0.53): bar lines are now the main loss from a PDF. Bach is poor on every side; our reading missed the time signature. Ours costs 5-6 times plain Sonnet or Opus, since it sends a full note list and reviews passage by passage; plain Fable spends more than ours reading the PDF itself. One run each on three pieces: the Sonnet and Fable gaps are clear, the Opus figure is not a published one. Fable's Bach review passed the 15-minute limit twice; the limit is now 40 minutes.

### 86. Why ChatGPT users got no PDF result, and every flow ending with output (2026-11-01)

**Problem.** On 31 October four ChatGPT users came; two left after one failed PDF read, and one spent about 97 minutes without getting an analysis drawn. From the logs: every new multi-page read took 220-310 s, the reading step reaching its 240 s limit in most; the call was cut off after about two minutes and ChatGPT sent it again (corrected in entry 105: the cut-off is Cloudflare's, not ChatGPT's), so the first reply was always lost, and 13 of 14 "busy" replies answered a user's own re-send while their first read still ran. Fast failures ("No music could be read", 13-25 s) logged only the error's class, so their cause is unknown. A second review found the rest: in 5 of 7 ChatGPT sessions that drew a page nothing was ever marked (18 of 21 renders had an empty annotation list); the PDF result never stated the bar numbers, so the model guessed ranges (all four PositionErrors); a failed draft model, a bad position or a range over 32 bars returned nothing; a failed correction gave no way to see the bar; requests refused before any work still used up the daily limit.

**Root cause of the slow reads.** The 240 s budget and the "two more readings when the first has more than 3 problem bars" rule were set on 12 October from local timings (9 s a page). The same 4-page scan on staging: every Audiveris step 2.5-3 times slower than locally on 2 cores (JVM start 5.7 against 1.3 s, LOAD 27.6 against 11.3, HEADS 43 against 14.5), so the cloud's vCPUs, not the users' files. The extra readings then ran until the deadline and were thrown away when it came.

**What we did.**
- Reading: the middle of the three settings is dropped (on the 83 benchmark PDFs, the best of settings 0 and 2 equals the best of three: pitch 94.4%, pitch and onset 86.6% on the main set, 89.3% held-out; the first setting alone loses 1.5-25 points of pitch and onset). Both settings start together and the second is stopped when the first is clean; locally on 2 cores both together take 64 s against 90 s one after the other. A reading that finished is used even when the other ran out of time. Audiveris is stopped at the deadline. Each pass logs its step times, page image sizes, interlines, pages done and Audiveris's own failure kind, never text from the page. The Haydn test now expects setting 0's reading (setting 2 ties it on problem bars and the first wins, as before); a tie-break towards more notes cost 0.6 points on the main set and was not kept.
- PDF calls: a call for a file already being read waits up to 100 s for that read and otherwise says it is still being read, instead of "busy"; the finished card is saved per file and slur choice, so a repeat answers in 0.4 s on staging (14-64 s before). The result states the score's bar numbers; an unreadable PDF names what to try next.
- Every flow ends with output: marks at positions that do not exist are left out and listed, the rest drawn; a range over 32 bars draws the first 32 and says where to continue; a render with no marks tells the model to draft first; when the draft model fails the draft returns the NOTES table and the method, logged as "degraded" (severity ERROR); a failing optional section is left out and logged; a failed correction shows the bars as they are now, in N1.
- Limits: render and draft check the score id and bar range before charging. Failed PDF reads stay charged, since they use the compute (owner's rule: what costs money counts); so does a draft whose model failed and which returned only the NOTES table (owner's decision, 2026-11-01).
- Calls the MCP library rejects for bad arguments are now logged, by field name only.

**The 429 in real ChatGPT (2026-11-01).** A test in ChatGPT on production: the read finished at 264 s, but ChatGPT re-sent the call at 125 s and Cloud Run answered 429 at once ("waiting too long for an available instance") with one request in flight. Cloud Run lowers an instance's concurrency by one each second while its CPU is above 90%, so during a read the only instance takes nothing else; raising concurrency cannot help. With the owner's approval, max instances goes from 1 to 2, and the marker for a read in progress moves to the bucket (`scores/pdf-reading-…`, created only if absent, removed by the reader that owns it, taken over after 300 s) so a call that lands on the other instance polls for the saved card, or the saved failure, instead of reading again. The second setting runs at `nice 19` with its own 190 s budget, so the first keeps its speed (locally 62.6 s beside it against 60.3 s alone, and 96.8 s without nice); a long PDF whose second reading cannot finish keeps the first (owner's choice). A call now waits up to 100 s, under ChatGPT's 125 s.

**Long reads on the cloud (2026-11-01).** Rondo alla Turca (5 dense pages, Mutopia) on staging, sent the way ChatGPT does (abandoned at 125 s, sent again): no request refused (41 probes), but the first setting alone took 230 s (46 s a page), and building the card took 101 s instead of about 17: the call that started the read had ended at Cloud Run's 300 s limit, the repeats landed on the other instance, and the reading instance had no open request, so its CPU was throttled. With the owner's approval the request timeout goes to 900 s, the starting call stays open up to 855 s, the first setting's deadline is 480 s and the second's 400 s, and a PDF over 8 pages has its first 8 read and the reply names the pages (owner's choice, option B; the 12-page refusal stays, as the approved tool description says). The held-open alert now counts requests of 880 s or more. Monitoring counts the new "degraded" outcome as bad in the server-error alert and the availability SLO, and a crash in a PDF read is now a server_error on the call line with the reference the user sees (it was logged as user_error, so neither alert nor SLO saw it); PDF stage timings go back on the call line. The monitoring changes take effect when `server/monitoring/apply.sh` runs; the SLO is only created if absent, so its filter needs a manual update.

**Faster local tests.** `pytest -n auto` (pytest-xdist, now in the dev group and CI): the full suite in 8.5-9.7 minutes on 12 workers against about 35 one at a time; the slowest test alone takes 164 s. The daily counters were a read-modify-write guarded only by an in-process lock, so two instances could overwrite each other's counts; each save is now conditional on the counter's generation and retried (owner approved). Against the staging bucket, two simulated instances adding 50 each at once end at exactly 100; the old way ended at 52.

**Result.** Staging, 4-page scan: 207 s for a new read (OMR 183 s), 0.4 s for the repeat. Tests: 8 end-to-end ChatGPT-flow tests with injected failures, 3 same-file tests, 3 reader tests; the full suite passed (1,211) before the second commit. `diff_check`: pdfwarn 80 and render 28 inputs unchanged; `test_awkward` 196 pass. A new read is still over ChatGPT's limit, so the first reply is lost and the user's re-send gets the result; how to read faster within about US$10 a month is being measured next. Not yet confirmed in ChatGPT itself.

### 87. A whole piece drawn as one PDF (2026-11-01)

**Problem.** A page showed at most 32 bars, so a whole piece came back as one PDF per passage. The owner wants the whole piece in one file. The cap dated from the single tall page used for excerpts, not from cost.

**What drawing time depends on.** Measured locally, warm, without marks: Prelude 598 notes on 2 staves 2.9 s; Nocturne 1,253 notes 6.4 s; Rondo 1,577 notes 7.7 s; Ballade 5,258 notes 34.4 s; Dvořák 4,195 notes on 25 staves 70.3 s; Mozart 41, 16,893 notes on 17 staves 124.4 s. Time follows notes and staves, not bars; 95 marks added 1.3 s. Counting notes from MusicXML takes 1-17 ms.

**What we did.**
- The 32-bar cap is removed. A stretch of up to 32 bars stays one tall page, as before. A longer stretch or a whole score is laid out on one tall page so the phrase-aware line breaks still apply, then split into normal printable pages (layout A, owner's choice over one tall page). A first version split every excerpt into printable pages, so 8 Chopin bars with marks came out on 2 pages; 31 tests caught it, and `diff_check render` shows 28 of 28 inputs unchanged after the fix.
- Building the PDF probed each page's ink at full size; it now probes at 1000 px wide. The 6-page Rondo PDF: 17.3 s before, 2.4 s after, same page sizes.
- The ChatGPT card shows the first 2 pages stacked (owner's choice); the result tells the model the PDF has the rest.
- The tool description and the method tell the model to analyse a long piece passage by passage and draw it once.
- A draw counts once towards the daily limit however long it is (owner's decision).

**PDF reader 5.11.0-sma.3.** Note-head template matching on 64-bit masks and the beam step's disk smoothing done row by row (fork branch `sma-5.11.0-speed`). On all 83 benchmark PDFs, run twice: main set pitch 94.36 → 94.37%, pitch and onset 86.60 → 86.66/86.67%, uneven bars 393 → 392; the other four sets equal or up to 0.07 points better. Local seconds a page 30.2 → 20.8-22.8 on a shared machine. The Rondo full read locally 73.6 → 48.3 s (the research agent's single-core-pair timing). Audiveris does not repeat exactly on some songs (6 of 12 song PDFs moved in an unpatched re-run); log 35 said it did.

**The first PDF's 15-20 s.** The first PDF in each process paid 15-20 s in cairo's font lookup. Cause: `engine/fonts/fonts.conf` named its fonts folder as `<dir prefix="relative">.</dir>`, which fontconfig (2.13.1 here) read as the current working directory, so every new process scanned the whole working tree (the repository locally, `/app` with its Python packages and the reader on Cloud Run) and wrote `.uuid` files into the folders it scanned; that is where the stray `.uuid` in the reader's `tessdata` came from. The config now names the fonts folder by its absolute path, written to a temporary file when `engine/render.py` is imported. A first PDF in a fresh process: 15.2 s before, 0.01 s after; a real score PDF still embeds Score Serif.

**The PDF card on the cloud.** After the font fix, building the card still took 32.8 s on staging for the Nocturne (Op. 9 No. 2, 3 pages): drawing 13.4 s, images and PDF 19.4 s, about 3 times the local 10 s; the work itself, mostly rasterising the every-bar image (2.3 s locally), PNG compression and colour reduction. The download image, the PDF and the page images are now built side by side: 27.1 s on staging (8.1 to 5.8 s locally). The every-bar download image is 1400 px wide instead of 2800 (owner's choice after comparing 1400, 2000 and 2800 on the Nocturne): 4.3 to 1.8 s locally, 713 to 389 KB. The analysis card's download image is 1400 px too (owner's choice). Cloud Run goes from 2 to 4 vCPU (owner approved, 2026-11-01): reads are faster, drawing is not, so each draw costs about 1.8 times as much per second; estimated a few dollars a month more with every daily limit reached.

**Reads on staging at 4 vCPU with the new reader** (each read once, on a new instance): Rondo 5 pages 131.6 s (OMR 101 s), the 4-page scan 124.5 s (OMR 102 s, against 183 s on 2 vCPU with sma.2), the Nocturne 169.9 s (OMR 135 s; each setting 121-133 s). Drawing does not use the extra cores: the whole Rondo drew in 28-29 s on 2 vCPU and 29-32 s on 4.

**Open.** A note budget for what can be drawn within ChatGPT's two minutes is still to be measured on staging. Production ChatGPT keeps the old 32-bar tool text until OpenAI approves the update.

### 88. ChatGPT could not see the annotation format, so it never drew (2026-11-01)

**Problem.** In a real ChatGPT chat on staging (Hensel, 3 pages, "analyse the whole piece and give me one annotated pdf"), ChatGPT read the PDF and drafted, then made its own PDF with labels beside the music. Staging logged no drawing call at all. Asked for the exact error, ChatGPT quoted its own schema check: `{'type': 'harmony', 'measure': 1, 'beat': 1, 'label': 'I', 'key': 'F'} is not valid under any of the given schemas`. Asked for the signature it was given, it showed every annotation type as `any // $ref: "#/$defs/Harmony"`: ChatGPT now calls tools from generated code and does not expand `$defs`, so it never saw that a position is `at: {measure, beat}`, guessed, and its own check refused the call before it reached us. Our schema has not changed since the first commit, so this is a change on ChatGPT's side. The same run on production (by mistake, the "sheet-music-analysis" app points there) ended the same way; I had blamed the old 32-bar tool text, which was wrong. It likely also explains the earlier "drawing never reached the server".

**Fix.** The tool list now writes every field out in place (no `$ref`, no `$defs`); render_analysis's schema grows from 12.2 to 14.5 KB, a correct list still passes a standard schema check and the flat guess still fails. The draft's review guide gains one line with real examples of harmony, cadence and phrase items. The draft result is not tool metadata, so that line reaches production ChatGPT on the next deploy; the written-out schema reaches it only after OpenAI approves. A new test fails if any listed tool's input contains `$ref` (it failed before the fix).

**The draft line alone did not reach the model.** After the production deploy, the published app (old tool metadata) still failed: ChatGPT again guessed flat `measure`/`beat` and its check refused both tries. Asked, it said the draft held no example. The Hensel draft is 35,348 characters and the example sat at 25,742, after the 28,000-character notes table; ChatGPT now reads results through its own code and quoted only the opening lines. The example now comes right after the score summary (under 500 characters in), and a test checks that the example in a whole-score draft is near the top and draws without errors (it failed before the move).

**On production with the published app (still the old tool metadata), after the move:** ChatGPT drew. It called render_analysis twice (bars 1-20 with 30 marks in 11.9 s, bars 21-40 with 22 marks in 10.3 s), as the old 32-bar text tells it, and then built its own combined side-panel PDF for "one PDF", offering ours as two sections. The whole piece in one call, as on staging, should follow once OpenAI approves the new tool text.

### 89. Before the next release: results read from the top, whole pieces sized to ChatGPT's two minutes, the Claude skill installs what it imports (2026-11-01)

Two audits (ChatGPT/OpenAI side and Claude side) listed what to fix before one OpenAI resubmission and a plugin release. This entry covers the server and skill fixes that are not tool metadata, so they ship without review.

**Results read from the top.** ChatGPT reads only the start of long results. The draft now runs: summary, label format, drawing plan, how-to, part-writing / ledger / student sections, draft chords, method, and the notes table last (Hensel's how-to was at character 25,742 of 35,348). Drawing results put left-out marks and "nothing drawn" first. On 11-01 a production user drew bars 1-32 twice with no marks (46 and 54 s) and left with nothing.

**Arguments ChatGPT guesses.** An unknown `view` ("full", tried in the audit) hid every mark and was still charged; views are now matched without case or dash differences and unknown ones refused before charging. Ranges accept a long dash and a single bar. One parser and one view check in engine/ serve the server and the skill scripts.

**Whole pieces against the 125 s cut-off.** Whole-piece renders on staging (4 vCPU), one harmony label per bar:

| Score | Bars | Staves | Total | Drawing | Extra files |
|---|---|---|---|---|---|
| Hensel | 39 | 3 | 18 s | | |
| Chopin Nocturne | 37 | 2 | 22 s | | |
| Chopin Ballade | 262 | 2 | 103 s | 47 s | 55 s |
| Dvořák Largo | 127 | 25 | 219 s | 99 s | 120 s |
| Mozart "Jupiter" | 433 | 17 | 382 s | 183 s | 198 s |

The extra files were mostly the worksheet, a second full drawing (Dvořák locally: drawing 34.7 s, worksheet 32.2 s, MIDI 4.8 s, MusicXML 2.5 s, RomanText 2.1 s). The worksheet is now made the first time its link is opened, from its own copy of the score stored with the link, so the link lasts a full day from the drawing; one build at a time, and a failed build says so instead of "expired". MIDI and RomanText stay with the drawing: they are cheap, and an empty or failed one still gets no link (the review found that making them lazily too would advertise links that could fail). This removes the most expensive extra from every render, and most worksheets are never opened, so compute goes down. Drawing time on the cloud fits about 36 s + 0.02 s per staff-bar (staves x bars). The draft now tells the model to draw the whole piece in one call up to 2,000 staff-bars (about 76 s), and otherwise passages of at most 2,000 / staves bars (Dvořák 80, Jupiter 117). Drawings with no marks skip the extra files.

After the change, on staging: the whole Ballade 63 s (was 103 s; drawing 49.5 s, MusicXML/MIDI/RomanText 4.4 s, publish 8.7 s) and Dvořák bars 1-80 (the passage length the draft now gives) 77.8 s, both under the 125 s cut-off. A worksheet link opened on staging: 1.9 s to make (4 bars), 0.1 s the second time.

**Claude skill.** A real claude.ai sandbox today: Python 3.13.18, no music21, verovio or cairosvg; numpy, matplotlib, pikepdf and pydantic present. The skill's pip line lacked music21, which the draft and drawing scripts import, so both crashed in a new chat. The line now pins uv.lock's versions (all have Python 3.13 wheels) and includes music21; a test builds a fresh 3.13 environment from exactly that line and runs the scripts (it fails on the old line). The skill now reads at most 12 pages, the first 8, with the server's wording and next step.

**Real claude.ai tests with the built skill (Sonnet 5.5, fresh chats, uploaded as a personal skill).** Bars 1-8 and the whole Nocturne (one 7-page PDF) drew correctly. Two failures, each root-caused by a separate agent before fixing:
- The chat never called `draft_from_notes`, though `play` worked in the same chat. In claude.ai connector tools load on demand, so "if a tool named draft_from_notes is available ... otherwise skip" read as false; the step also named the connector by a name the account does not use. Step 3 now says to search for the tool and skip only if the search finds nothing, and the Opus sentence leads step 7 (the first answer had left it out). Retest: production logged `draft_from_notes` from Claude at 00:21, and the first answer ended with the Opus sentence.
- PDF reading failed in every Claude chat: "the network policy blocked it with a 403". A researched theory (GitHub's redirect hosts not allowed) turned out wrong when checked in a chat: the reader package (77.7 MB) and our jar download through the redirect fine; only `github.com/tesseract-ocr/tessdata/raw/...` is refused, while the same file on raw.githubusercontent.com (same checksum) downloads. The skill now uses that URL; retest: Hensel read in about 2 minutes with pages and notice shown. The sandbox has 2 CPUs, 8 GB, Java 21, dpkg-deb and git; our own server is not reachable from it.

**Not done here (owner decisions or held metadata):** the view enum and parameter descriptions, file-input shape, read-only hints, per-client server instructions, the submission package and demo video, README text on what the plugin downloads, the plugin release.

### 90. Bars that don't add up: root causes in the PDF reader (2026-11-01 to 11-02)

Owner goal: under 100 flagged bars ("don't add up", `problem_spots`) on the main benchmark (57 PDFs, 2027 bars), by fixing root causes. All reader changes are local fork branches from 9ef6563b3 (sma-5.11.0-startcolumn); nothing is tagged, pushed or deployed. Results: `spike/omr/speed/results/bench-<variant>.json`, variants in `spike/omr/speed/variants.py`.

| Build (main set) | Flagged bars | Pitch | Pitch+timing |
|---|---|---|---|
| 5.11.0-sma.3 (production) | 392 | 0.9437 | 0.8667 |
| + start column, 6-vs-9, small whole heads off, mid-system two-digit times, all-or-nothing time columns (sma5) | 352 | 0.9437 | 0.8834 |
| same + 8/8 option | 334 | 0.9440 | 0.8842 |
| + render small-staff vector pages sharper (sma6dpi, fork a2bdde55a) | 321 | 0.9451 | 0.8893 |
| + deterministic hashes + beam-group tuplet search (int1, branch sma-integration) | 309 | 0.9409 | 0.8902 |

- **Time signatures, blind test** (`spike/omr/bench-timechange`, 55 PDFs picked by a written rule before any run): changes found 15→41 of 72 (songs) and 11→61 of 92 (piano, quartets), no invented time signatures on 16 no-change PDFs. Side effects: grace notes found 56→25 (the all-or-nothing choice between readings in `read_pdf`), low whole notes on ledger lines dropped (small whole heads removed), a lost clef change in Rachmaninoff op. 42/15. Being fixed.
- **Small staves:** Audiveris renders PDFs at a fixed 300 DPI; quartet staves get an interline of 12-14 px, rests break up or are deleted as weak, and bars that then don't add up lose whole chords at export. Vector pages under 18 px are now rendered again at about 20 px (scans excluded). Quartets gain 6-68 notes each; normal staves unchanged. Cost: +7-12 s and about +0.5 GB per reader process on those pages; to be capped to fit 4 GB and timed on staging before deploying.
- **Run-to-run differences:** glyph and section hash codes used the enum's identity hash (`RunTable.java:1088`, `BasicSection.java:733`), so the order of equal-weight candidates (e.g. augmentation dots) changed between JVM starts and could flip which reading `read_pdf` kept (Die Stadt bar 8). Fixed with ordinals.
- **Tuplets:** implicit tuplets are now tried per beam group (rests included) against the measure, replacing the 3/2-whole-voice and partial-shrink paths. Big gains on unmarked-triplet songs, but int1 loses pitch on several PDFs (chords without a time are dropped at export, and some triplets the old code found are missed); being fixed before int1 can be a candidate.
- **Where the rest are:** of int1's 309, the known fixes (8/8, tuplet numbers other than 3, rests drawn over other notes, printed tuplets linked to the wrong chords) remove about 80. The remaining ~230 are scattered (wrong flag/beam count, several causes at once, dots, extra notes; 62 of 309 are on scans). Under 100 is not reachable with targeted fixes; the owner chose to finish these, release, then build a rhythm solver (keep the reader's rejected alternatives and choose per measure the best-supported combination that fills the bar).
- **Combined build int3** (branch sma-integration2: all of the above + chords no longer dropped at export, printed tuplets linked to whole beam groups, unbeamed and per-voice implicit tuplets, small-chord tie crash, clef behind a small head, time half replaces its number): pitch and pitch+timing up on all five sets against production (main 0.9437/0.8667 → 0.9559/0.8940, heldout3 0.8967/0.6607 → 0.9584/0.8121). Main-set flags 392 → 338: higher than int1's 309 because chords that int1 silently dropped are now exported and their bars honestly flagged. All five sets: 729 → 551. Blind time-change set: pitch 0.8959 → 0.9426, pitch+timing 0.7601 → 0.8386, flags 638 → 431; 7 of 55 PDFs lose more than 5 notes (worst −26). Liebeszauber −74 timing: voices are split before tuplets are tried (a joint voice/tuplet search is needed).
- **Rhythm solver phase 0** (`docs/rhythm-solver-design.md`; logging build sma-solver-diag; `spike/omr/speed/solver_phase0/`): on 50 main-set PDFs only 35% of rest/dot/type bars have any discarded candidate of the right kind near where the symbol belongs (rests 0 of 18), under the 50% abandon rule; the evidence that exists is weak (median grade 0.03-0.17 for rests, flags, beams). The missing symbols were never detected, so the edit phases are dropped. Ceiling: about 50 voice-only bars + 20-40 evidence-backed bars + part of 69 tuplet bars. Under 100 is not reachable by improving this reader's logic; it would need better symbol detection.
- **Rhythm solver phase 1** (branch sma-solver1: replayable voice-mapping search with tuplet hypotheses chosen jointly, guards per the design): safe but small. Main set pitch unchanged, pitch+timing +10 notes, flags 338 → 335; Liebeszauber +42 timing (bar 4 now exact); no PDF loses anything; 5 bars cleared, 0 of them wrong (in-sample). Only 2 of the 49 "voice-only" bars cleared, under the design's stop rule of 20: 44 of the 49 also miss rests or notes (e.g. Bach 846's 16th rests), and no fault-free reading exists among the symbols the reader found; a 4x wider search finds nothing more. **Conclusion: under 100 flagged bars is not reachable by improving this reader's logic.** What remains is mostly symbols that were never detected; reaching the goal would need better symbol detection (a new recognition engine or retraining), a separate project for the owner to decide.
- **Staging, reader 5.11.0-sma.4 (2026-11-02, revision 00069):** startup clean (only the deploy's expected user-error smoke calls). Mutopia PDFs sent as ChatGPT does: Beethoven Op. 18 No. 4/iii (5 pages, interline 21, no new rendering) 111 s, OMR 90 s; Bach BWV 1080 "rectus" (3 pages, interline 14, rendered again at 21) 103 s, OMR 87 s. Peak memory 39% and 49% of 4 GiB; the server reads one PDF per instance (`pdf_lock`), so the second rendering fits without a cap. Locally the second rendering adds 4 s on rectus (22 → 26 s); at Cloud Run's 4 vCPU/4 GiB price about US$0.002 per small-staff read, nothing at the current volume (3 production reads in 30 days). The 8/8 option (`rc2-88`, not in sma.4): main set 338 → 321 bars that don't add up, pitch unchanged, pitch+timing 0.8940 → 0.8945, other four sets unchanged.
- **Release (2026-11-02, owner approved):** 8/8 goes in as an engine setting (`optionalTimes=6/4, 7/8, 8/8` passed to Audiveris, new cache key), not a fork release. It changes one main-set PDF (Lehmann "Golden Bridges", MuseScore: 18 flagged bars to 1, 8/8 read correctly, checked full size; the voice's whole notes in bars 6 and 10 and the low bass whole notes are still missing, as before) and nothing on the blind set (55 PDFs, identical scores). A separate review of the branch found that `is_scan` missed a page image drawn through resources inherited from the page tree (and a form without its own resources); fixed, with the test extended, and no scan verdict changes against main on 181 PDFs. Plugin 1.6.0 ships the same reader.

### 91. Users per month, new and returning (2026-11-02)

**Problem.** The user code from entry 78 changed every UTC day, so the logs could only count people per day. The same person on two days looked like two people, and nothing showed users per month, users since launch, or who came back. Three days of production (31 Oct to 2 Nov) gave 4, 5 and 3 ChatGPT users a day, somewhere between 5 and 12 different people.

**What we did.** The owner chose a permanent code. `pseudonym()` scrambles ChatGPT's anonymous ID with one random key kept in the bucket at `pseudonym-key`, made once and never deleted, so a person keeps the same code. `user_code()` also adds an empty object `users/<code>/<YYYY-MM>` for each month a code is active. The lifecycle rule doesn't cover `users/` or the key, so these are kept, and monthly counts don't depend on the 30-day log retention. Each server instance writes a given month's record at most once. `tools/usage_report.py` prints ChatGPT users since launch and, per month, active, new and returning. The conversation count for the rating question now uses the same key; its `chats/` files are still deleted after a day. `keys/` stays in the lifecycle rule until the last daily keys are gone. The privacy page says the code is permanent and drops "no tracking". Claude sends no user ID, so Claude users are still not counted.

**Result.** Counting starts at the production deploy; daily codes from before cannot be joined to the new ones.

### 92. Leland symbol shapes for PDFs drawn with Leland (2026-11-02)

**Problem.** Audiveris matches symbols against Bravura shapes. MuseScore 4 PDFs (every `ms` benchmark PDF) embed Leland, whose rests, flags and heads differ in shape. LilyPond PDFs embed Emmentaler, Verovio PDFs Leipzig or plain paths, scans none.

**What we tried.** Leland for every PDF: main 321 → 309 flagged bars, but bench-real (scans) pitch+timing 0.7244 → 0.7121. Leland for every non-scan PDF: all five tuning sets better, but the blind set (`bench-timechange`, never tuned on) went 431 → 451 flagged bars, all from Verovio PDFs (+30 bars, 11 of 28 PDFs worse) while MuseScore PDFs gained (−10). Shapes have to match the font actually printed.

**What we did.** `uses_leland` looks for an embedded font named Leland (true for all 70 MuseScore benchmark PDFs, false for every LilyPond, Verovio and scanned one) and only then passes `MusicFont.defaultMusicFamily=Leland`. Each Audiveris run now gets its setting number directly instead of finding it by its option list.

**Result (measured end to end, sma.4 + 8/8 → + Leland):**

| Set | Flagged bars | Pitch | Pitch+timing |
|---|---|---|---|
| main | 321 → 317 | 0.9559 → 0.9592 | 0.8945 → 0.8952 |
| heldout | 63 → 62 | 0.9815 → 0.9844 | 0.9318 → 0.9346 |
| heldout2 | 60 → 45 | 0.9484 → 0.9623 | 0.8494 → 0.8716 |
| heldout3 | 62 → 61 | 0.9584 → 0.9630 | 0.8121 → 0.8165 |
| real (scans) | 28 → 28 | unchanged | unchanged |
| blind | 431 → 421 | 0.9426 → 0.9513 | 0.8386 → 0.8430 |

The blind set is no longer unseen for this rule: it is what showed the Verovio regression and so chose "PDFs that embed Leland" over "every non-scan PDF". The rule follows from matching shapes to the printed font, not from a threshold, but the next reader change needs a fresh unseen set.

No set gets worse on any of the three; read time unchanged. A separate review found nothing serious (one unlikely case: an unused Leland font left in an edited or merged PDF would turn Leland on). Full suite passed after updating a test stand-in for `run()`; `diff_check` pdfwarn 0 of 80 changed, `test_awkward` 196 passed. Staging revision 00070: Haydn "She never told her love" (MuseScore, 3 pages) read in 70 s, OMR 60 s, peak memory 25% of 4 GiB, no errors.

### 93. Ceiling check: reading symbols from the PDF's music font (2026-11-02)

**Question.** Before 5-8 days on reading rests, flags, dots and noteheads from the font characters in MuseScore and LilyPond PDFs, how many flagged bars could it fix? Stop rule written before running (`spike/omr/speed/font_ceiling/STOP_RULE.md`): 60+ fully covered bars of 214 → go; under 30 → stop; between → owner decides.

**Method.** Solver phase 0 lists, for each of the 214 flagged bars on ms and ly PDFs (int3 reading, main set), what the bar needs to match the truth, with page, staff and x. `ceiling.py` extracts every rest, flag, dot and notehead character from the PDF and checks for one of the needed kind on that staff near that x (for an extra note Audiveris invented: that no notehead is there). Check of the mapping: at notes Audiveris invented (real positions), a notehead character is there 32 of 36 times, so the coordinates line up; the misses are positions phase 0 had to estimate from the rhythm.

**Result.** Fully covered bars: 22 (within 1 staff space), 27 (2 spaces), 32 (3 spaces); this counts the kind of symbol only, not its exact value, so it is generous. Under the rule's stop line at the strict window, at its bottom edge at the loosest.
- 64 of the 214 bars need only voice changes, and 87 need a change no symbol supplies (tuplets, dropping a beam or a dot).
- Of 62 notes needing a shorter value, 37 have no flag character near them, 27 none on the whole staff: they are beamed, and the missing beam is a drawn shape, not a font character.
- 6 missing rests have no rest character on that staff at all; hidden rests in the truth explain only a few (0-3 per piece).

**Decision.** Font characters alone are not where the flagged bars are; not doing the 5-8 days. Reading beams from the drawn shapes as well would add the beam bars (about 37 needing one more beam, 59 needing one fewer) but is a much larger, full vector reader; it needs its own ceiling check first.

### 94. Ceiling check: can a PDF's drawing instructions give every note's printed value? (2026-11-02)

**Question.** A reader built on the PDF's drawing instructions instead of an image would only be worth months if it recovers the printed symbols almost perfectly. Stop rule written before running (`spike/omr/speed/vector_ceiling/STOP_RULE.md`): per staff and bar, compare the multiset of (rest or note, printed value, dots) for every chord and rest with the truth; 95% or more → viable, under 85% → stop, between → owner decides.

**Method (prototype, about 3.5 hours).** `extract.py` reads font characters (heads, rests, flags, dots) and drawn shapes (stems, barlines, beams as thick filled four-sided shapes); `ceiling.py` cuts each staff into bars at barlines, attaches heads to stems, counts beams stacked from the stem end, and lines read bars up with truth bars by content (a truth bar with no identical read bar counts as a miss).

**Result, all 34 main-set ms and ly PDFs:** 89.4% of 3,247 staff-bars match exactly (MuseScore 93.2%, LilyPond 82.1%). 9 PDFs at 95-100%. Bugs found and fixed on the way: flat beams taken for staff lines, LilyPond beams drawn twice, dots of a chord counted per note. Remaining misses seen are still prototype faults, not missing information: some LilyPond beams not recognised (Mozart K155: eighths read as quarters; the MuseScore engraving of the same piece scores 100%), barlines missed (Bach 846 LilyPond, 32 of 34 bars), rests drawn between staves given to the wrong staff. So 89% is closer to a floor than a ceiling.

**What it does not test.** Voices and tuplets (which notes form a line, where the triplets are) are not checked; they sank solver phase 1 and need their own test. The PDFs are ones we engraved; real exports may have their fonts turned into outlines.

### 95. Test: voices and triplets when every symbol is read exactly (2026-11-02)

**Question.** Entry 94 showed the printed symbols can be read from the drawing instructions. Solver phase 1 failed at the next step: working out voices and triplets. Given exact symbols, is that step tractable? Stop rule written before running (`spike/omr/speed/vector_ceiling/STOP_RULE_ASSEMBLY.md`): a simple fixed assembler, scored on the 2,902 staff-bars whose symbols entry 94 read exactly; a bar matches when every event's start, sounding length and rest/note equal the truth. 90%+ → tractable, under 75% → stop.

**Result as registered: 70.6%, under the stop line.** One-voice bars 91.8%, bars split into two voices 14.4%, bars with triplets 8.8%. MuseScore and LilyPond alike (70.8%, 70.3%).

**Why, from the failures:** the fixed rule called a bar two-voiced whenever stems pointed different ways, but most were one melody whose stems flip as it crosses the middle line. **Diagnostic, decided after seeing the data:** try one voice first and split only if that does not fill the bar: 89.1% (one voice 93.4% of 2,650; bars that really need two voices 44% of 252; triplet bars 27.5% of 91). No printed tuplet number was found as a music-font character, so every triplet had to be inferred.

**Reading.** With exact symbols, the plain one-voice bars are mostly solved. The hard part is the same as in phase 1, now isolated: real two-voice bars (9% of bars) and triplets (3%). A vector reader is only worth months if those two can be solved, and this simple assembler does not; that needs its own design (simultaneous notes line up vertically, which the drawing gives exactly) and a fresh test, not a tweak of this one.

### 96. Silent errors: wrong bars nothing flags (2026-11-02)

**Question.** "Bars that don't add up" only catches rhythm faults. How many bars are wrong but not shaded? Script `spike/omr/speed/silent_errors.py`, on the current reader (sma.4 + 8/8 + Leland, cached readings of all five sets, 2,951 truth bars): each truth bar is paired with its read bar; wrong means the (pitch, start) multiset differs.

| Bars | Count | Share |
|---|---|---|
| right | 1,900 | 64.4% |
| pitch wrong, not flagged | 472 | 16.0% |
| rhythm wrong, flagged | 251 | 8.5% |
| pitch wrong, flagged | 235 | 8.0% |
| rhythm wrong, not flagged | 70 | 2.4% |
| right but flagged | 23 | 0.8% |

**So 542 of 1,028 wrong bars (53%) are silent**, and the flagged count understates errors by about half. Silent ones by size: 131 bars one note off, 97 two, 149 six or more (whole passages, likely clefs or octave lines). Spot checks of one- and two-note cases are real misreads (Bach 846 bars 32-33 low C, Beethoven op. 48/5 low octaves). Entry 98 corrects the first guess that these are the "low whole notes on ledger lines dropped" side effect from entry 90: they are mostly grace notes and notes on ledger lines, and most predate sma.4. By engraver, silent of wrong: MuseScore 273/527, LilyPond 64/148, Verovio 50/103, scans 143/234.

**Consequence.** The honest target is wrong bars (1,028 here), not flagged bars. The cheapest large wins look like: the dropped-low-notes side effect (a known, diagnosed cause), and a check that compares noteheads counted from the PDF with the reading, which would turn many silent misses into flags.

### 97. Real-world PDFs: are the music symbols still font characters? (2026-11-02)

**Question.** Every benchmark PDF was engraved by us (MuseScore 4, LilyPond, Verovio). A reader built on drawing instructions only helps if real files keep their music symbols as font characters. Sample: 28 PDFs marked "Typeset" on IMSLP, 2 per work from 15 well-known works (picked at random with a fixed seed; one more failed to download), plus 15 Mutopia PDFs. Script `spike/omr/speed/vector_ceiling/real_census.py` (fonts embedded, producer, text vs drawing operators, images).

| What the PDF holds | PDFs | Made by |
|---|---|---|
| Music font with its own (pre-SMuFL) layout | 30 | LilyPond Emmentaler 17, Sibelius Opus 6, Finale Maestro/Petrucci/Engraver 4, MuseScore 1-2 MScore 3 |
| Music font in the SMuFL layout (what entries 93-94 read) | 5 | MuseScore 2 and 4 |
| Shapes only, no music font | 7 | print-to-PDF drivers, InDesign, one Sibelius export, unknown |
| Type3 drawn glyphs | 1 | PostScript driver |
| Scan | 1 | (a "Typeset" file that is an image) |

**Reading.** 35 of 44 (80%) keep their music symbols as font characters, but only 5 in the layout the prototype reads. Covering most real files needs about four character maps: SMuFL, Emmentaler (by glyph name, already done), the Sonata-compatible layout shared by Sibelius's Opus and Finale's Maestro/Petrucci/Engraver, and MuseScore 1-2's MScore. Beams, stems and barlines are drawn shapes in all of them. MuseScore 4 is 3 of 28 IMSLP typeset files, so the benchmark (70 MuseScore 4 PDFs) over-represents it. This sample is IMSLP's typeset files, not what users upload; production read 2 scans of 3 PDFs last month.

### 98. Notes lost silently: grace notes first, not low whole notes (2026-11-02)

**Question.** Entry 96's silent pitch errors were guessed to be entry 90's "low whole notes on ledger lines dropped". Measured instead: bars where the read bar has every other note right, nothing extra, and is not flagged (current reader: sma.4 + 8/8 + Leland only for Leland PDFs, variant `sma4-fontmatch`), compared bar by bar with sma3-88. An Opus agent checked the causes on rendered pages, both of `read_pdf`'s raw readings and one saved Audiveris book (Bach 846).

| Bars that only lose notes, silently | 215 |
|---|---|
| right in sma3-88, wrong now | 18 |
| already wrong in sma3-88 | 197 |

**Causes** (a first pass ran on `sma4-leland`, which forces Leland on every PDF and is not the shipped rule; it made 227 bars, the classes below come from that pass):
- **Grace notes, about 130 bars.** `read_pdf` keeps one whole reading per PDF. Setting 1 (small heads) has the grace notes, setting 0 doesn't. In about 55 bars the grace note sits in the reading that was not chosen; the 18 new losses are almost all this, since int1 changed which setting wins on Bizet, Haydn, Erlkönig, Hensel, Ave Maria and K80 (now 0 grace notes). About 50 are never detected or attached to the wrong note.
- **Ledger-line and crowded chord notes, about 53 bars.** Bach 846 bars 32-33 (from the saved book): where a tie touches the ledger line, no ledger is built, so no head is made. Haydn bars 18-19 and Clara Schumann op. 3 bar 12 look the same on the page.
- **Whole notes only about 6 bars.** Removing small whole heads (fork b4c631a9f, entry 90) causes none of the regressions: sma5-88, which has it, is right on all of them.
- **Whole bars gone, about 6.**

The engine's analysis ignores grace notes (`part_writing`, `comparison`); they affect the notes table and playback only.

**Fix options.** Copy setting 1's grace notes into the chosen reading where the bar's other notes agree (about 1-2 days, about 70 bars); choose per bar instead of per PDF (more, riskier); build ledgers a tie touches (fork, medium-high); count noteheads from the PDF and flag bars that come up short (flags only, low risk).

**Ceiling for a notehead-count check** (`spike/omr/speed/headcount_bound.py`, before any PDF code: the truth's head count stands in for a perfect count from the PDF; a bar is caught when the reading has fewer heads). Of 542 silent wrong bars: 120 are short of normal-size heads, 164 short of grace heads only, 258 not short at all (wrong pitches with the right number of notes: clefs, octave lines, misplaced heads). Scans can't be counted from the PDF (42 of the 120), so **at most 78 silent bars could be caught on normal heads, about 14%**, or about 200 counting grace notes, which the analysis ignores. No right bar is short, so the ceiling has no false flags; a real counter would.

### 99. Silent wrong pitches: octave lines, missed clefs, accidentals (2026-11-02)

**Question.** Of entry 98's silent wrong bars, 266 have notes at wrong pitches rather than missing (`spike/omr/speed/wrong_pitch_kinds.py`, current reader `sma4-fontmatch`). An Opus agent traced each to its cause against both raw Audiveris readings, with about 25 bars checked on rendered pages. The script over-counts: about 22 rows have the right pitches at the wrong time (its "accidental" kind does not require a different pitch) and 11 are missing or extra notes, so about 233 are real pitch errors.

**Our code changes no pitch:** in 266 of 266 bars the final pitches equal one raw Audiveris reading (Audiveris writes an explicit alteration on every note).

| Cause | Bars (about) | Where it goes wrong |
|---|---|---|
| Octave lines cut short or missed | 61 | Audiveris shifts only notes between the line's two end chords and skips a line whose end is missing; `clean()` then removes unclosed line starts, the only trace. Faisst Lied der Nacht 42 bars (all engravers), Lehmann 12, Faisst Sehnsucht 5 |
| Clef changes missed | 52 | small mid-staff clefs (after key/time signature, end of bar, mid-bar); about 20 on scans, mostly Peters K545 |
| Printed accidental not linked to its head | 45 | mostly chords with one accidental |
| Grace-note accidental put on the main note | 18 | setting 0 drops the grace head, its accidental attaches to the next note and carries through the bar (K545 bars 22-23, 67-68 in every edition) |
| Accidental misread or on another note | 13 | 5 in one spot (Die Stadt, dense 9-tuplet) |
| Slur read as tie, carrying a natural | 7 | |
| Key signatures | 5 | key change at a bar's end applied to that bar (2), mid-system change missed (2), accidental after a barline read as a key (1) |
| Tie copying a wrong pitch | 4 | |
| Note one or two steps off, mixed | about 22 | |

Extending each unclosed octave line to its system's end recovers 15 bars and breaks 11, so no simple rule fixes it.

**Fix options.** Engine: flag bars from an unclosed octave line to its system's end instead of dropping it silently (about 25-30 bars flagged, small). Fork: keep small accidentals off full-size heads in setting 0 (about 15 bars, low risk); key change at a bar's end (2, small); octave-line extent across systems (up to about 55, several days, a false line shifts whole passages); small-clef detection and accidental linking (larger, riskier). Fork changes need a fresh unseen test set (entry 92).

### 100. Silent wrong pitches: 238 → 107 (2026-11-03)

**Goal.** Fix a majority of entry 99's 238 silent wrong-pitch bars by root-cause changes to the reader (fork branch `sma-pitch`, 22 commits on top of sma.4). Result: 131 of 238 fixed (55%); 131 of 237 on production's choice. Pitch and pitch+onset improved on every set; heldout and heldout2 each have one more flagged bar (see Costs). Counted by `spike/omr/speed/pitch_causes.py` over the five tuning sets; current reader `sma4-fontmatch` against build `pitch28`, same engine for both. Both counts skip the same 5 PDFs whose truth and reading parse to different bar counts.

| Set | PDFs | Pitch before → after | Pitch+onset before → after | Flagged bars before → after |
|---|---|---|---|---|
| main | 57 | 0.9592 → 0.9766 | 0.8952 → 0.9124 | 317 → 317 |
| heldout | 11 | 0.9844 → 0.9868 | 0.9346 → 0.9360 | 62 → 63 |
| heldout2 | 6 | 0.9623 → 0.9863 | 0.8716 → 0.8910 | 45 → 46 |
| heldout3 | 6 | 0.9630 → 0.9830 | 0.8165 → 0.8345 | 61 → 60 |
| real scans | 3 | 0.8756 → 0.8799 | 0.7244 → 0.7282 | 28 → 28 |

Silent wrong-pitch bars 238 → 107; all wrong-pitch bars, flagged or not, 402 → 242. The benchmark always has both reader settings, while production stops setting 1 when setting 0 has 3 problems or fewer; replaying production's choice from the cache (`prod_choice.py`) changes one of 83 readings and gives 237 → 106. A second tuning set chosen to stress these errors (`spike/omr/bench-tune2`, 40 pieces, 80 PDFs; the cancel-key, key-overlap and dash-drift fixes were found or tuned on it, so this is not an unseen result) went 258 → 122, pitch 0.9306 → 0.9529, pitch+onset 0.8450 → 0.8662; 3 single bars are newly wrong there. The pre-registered unseen set `bench-pitch` has NOT been run yet.

| Cause fixed (reader) | What was wrong |
|---|---|
| Small accidentals (setting 0) | a grace note's small sharp attached to the full-size note after it |
| Bass clef support | a drawn bass clef with no context support lost to other shapes; now raised when its place and size fit a bass clef |
| Stacked accidentals | accidentals in a column linked only to the nearest head |
| One-sign "key changes" | a lone accidental just before a note read as a key signature |
| Octave lines (8 changes) | dashed extent not traced; lines not continued onto the next system; line given to the wrong staff; "8" read as a lyric; line linked to a rest; notes not shifted when the line's end chord is written before its start chord (export voice order); a line over one chord kept only its start link; dashes picked on a beam row; dash row drifting on a rotated scan. Engine: `clean()` now orders octave-line starts and stops by time within a bar |
| "8" inside a word | the "ss" of *espressione*, read as an octave line |
| Dynamics height | a flat with an "f" above it read as one tall "sf" (6 spaces; real dynamics ≤ 3.8) |
| Cancel key (naturals) | a two-natural blob broke the sequence, and a cancel key lost its value before export |
| Accidental on the wrong chord | among heads at the same pitch the one with the smaller vertical gap won, even a chord further on by 1 pixel; now the nearest at the same pitch (13 bars fixed, 1 new: Polonaise No. 3 ms bar 22) |
| Low-grade lyrics | a false lyric item ("[a", "W") erased an accidental before symbols were read; lyric items under contextual grade 0.6 are now handed back as possible symbols |

**Costs.** One more flagged bar in heldout and heldout2: 3 bars whose timing changed with the lyric change (*Ave Maria* bar 12, *Erlkönig* bar 22, Boulanger bar 17) now don't add up and are flagged; pitch+onset in those PDFs fell by 6 notes or fewer.

**Left (107).** Accidentals 43 (missed signs: a sign touching an undetected slur, a sign merged with another shape, false text; each sign also carries to later notes), other 21, clef 17 (10 in the Peters K545 scan, where small treble clefs are never recognised; a French violin clef in Clara Schumann's Polonaise No. 3, which the reader has no kind for, rare, not added), step off 8, octave with no line in truth 8, key 5, grace-note accidental 5 (production stops setting 1, the only one that sees the grace notes). Tried and dropped: erasing only a band along slurs (no gain), preferring the reading with more notes on a tie (production would not see it), a grade floor for undashed "8" (real ones go down to 0.59).

**Before release** (one release with Leland, plugin 1.7.0): full test suite, `diff_check`, `test_awkward`, a different-model review of the fork diff, the unseen `bench-pitch` run (aggregates only), staging, owner's yes.

### 101. Silent wrong pitches, continued: 107 → 102 (2026-11-03)

**Goal.** The owner asked for 20 more of entry 100's 107 bars. Result: 5, then the owner closed the goal for diminishing returns. 107 → 102 with both settings read; 106 → 101 read the way production reads, both counts through the same code. All 5 bars are fixes and none is newly wrong (Faisst *Lied der Nacht* ms bar 22 stays wrong with a different cause). Build `pitch31`, fork commits a8a789552, 9ec73e0b0, ce37c25ae on `sma-pitch`. Pitch and pitch+onset are equal or higher on every set and no PDF lost a correct pitch on the five sets; flagged bars are unchanged with both settings read (317/63/46/60/28).

| Cause fixed (reader) | What was wrong | Bars |
|---|---|---|
| Key at the end of a bar | a key printed after the bar's last chord (before a repeat, or a bracketed reminder) was applied to the whole bar; it now opens the next bar | Joplin 51, Polonaise No. 1 ms 28 |
| One-staff key change | a sign right after a barline read as a key change on that staff alone; a key change beyond the staff header now needs another staff of the system with one within 2 spaces. Removed false keys in 7 PDFs; every one was checked against the reference and none was real | Brahms *Frühlingstrost* 8, 39 |
| Small treble clef | a small treble clef in mid-bar graded 0.49 and was dropped, both by the symbol step and by entry 41's clef rescue; the bass-clef rule (size and centre of a drawn clef) now covers treble clefs too: full 7.05 × 2.65 spaces, small 5.7 × 2.05, centre on the middle line | K545 LilyPond 37 |

**Second set** (`bench-tune2`, 80 PDFs): 122 → 120, pitch 0.9529 → 0.9533. Cost: Burleigh *Ethiopia Saluting the Colors* (both editions) loses 2 and 4 pitches in bars 37–38. A false one-staff key there had been turning missed sharps right by chance; with it gone, 3 bars count as accidental errors instead of 1 key error.

**Measured the way production reads.** The benchmark now stops setting 1 when setting 0 has 3 problems or fewer, as production does (default from now on; `--both-settings` for the old way). pitch28 → pitch31 this way: five sets 106 → 101, second set 122 → 120; flagged bars unchanged on every set (318/63/46/60/28, second set 453).

**Tried and dropped.** Treating a slur under contextual grade 0.6 as uncertain when erasing ink before the symbol step (a false slur had erased part of a sharp in Hensel *Mayenlied* bar 9): fixed that bar but broke Polonaise No. 4 vr bar 12; on the second set 120 → 117 but two PDFs lost 27 and 10 pitches and flagged bars rose 453 → 457. It also exposed an old crash (a dot removed during exclusion reduction removes one link twice). Both reverted. Subtracting beams already found from the ink around a clef-like head (Polonaise No. 1 ms bars 24, 36, where a beam crosses a small treble clef): the clef ink was then found, but graded best as a flag (0.09); reverted. Accepting braced staves without an internal barline (Audiveris switch `disconnectedBracedParts`): Polonaise No. 3 LilyPond becomes one piano part instead of three, but no wrong pitch changes anywhere and only that PDF changes (one fewer flagged bar); not adopted.

**Reference-file errors** (found, not counted, not edited): Polonaise No. 1 ms bars 23, 25, 35, 37 and vr 25, 35, 37: a natural tied across the barline into the next bar; the reference has no tie, so it reads the note flat; the printed flat two notes later confirms the reader. K545 LilyPond bar 31: the reference is an octave below what this edition prints.

**Left (101, production way).** One clustered lead, not started: small clefs whose top guess is right but graded very low, placed and sized like drawn clefs. *Traumbild* bars 3, 24, 25 (a small tenor clef mid-bar: best compound C clef 0.107, 3.05 × 2.0 spaces; header tenor clefs 3.86 × 2.52 at 0.42–0.61) and the Peters scan (treble 0.06). Rescuing grades that low risks false clefs, which change every following note, so it would need its own full runs. Otherwise out of reach for now: Peters scan ~20, reference errors 8, French violin clef 3, grace-note accidentals 5. The rest are mostly one-offs: a sign crossed by a slur's tail (Haydn 20), fused with tremolo slashes (*Gesungen* LilyPond 10, 26), a clef crossed by a beam (Polonaise No. 1 ms 24, 36), stacked signs given to the wrong note (Berg *Nacht* 14), and the piano split into three parts by a trill line (Polonaise No. 3 LilyPond).

**Faster benchmark.** Readings can now be spread over three home PCs (`spike/omr/speed/farm`; this PC 10 readings at once, an i3-12100F 6, an i5-8400 4), longest PDFs first: all six sets in about 19 minutes instead of about 80. Remote readings at first differed from this PC's on some PDFs; the cause and fix are under *Text fonts* below. With the fix, all 203 PDFs read identically on the farm and on this PC alone. A PC that does not answer is skipped, and a reading that fails for a network reason is redone locally instead of being cached as a failure. A quick set (`quick.txt`, 49 PDFs: every five-set PDF with a remaining error plus 10 guards) is for trying ideas; numbers are only quoted from full runs.

**Text fonts.** On Op. 34 No. 4 vr, both other PCs read 1,701 notes against 1,707 here. Every step up to text recognition gave the same result, and the image passed to Tesseract was pixel-identical. The difference came after: the reader sizes each recognised word by measuring it in a system font (Java's generic Serif and Sans, in the word's style). This PC has DejaVu's italic font files. The other two PCs and the production image (Debian slim with `fonts-dejavu-core`, checked layer by layer) do not, so Java slants the regular letters instead. Italic words then measure differently, and on page 1 two "7"s were kept instead of dropped. Reading here with only production's font files visible reproduced the other PCs' text exactly. So production has been reading italic text slightly differently from every local benchmark, and plugin users' results depended on their own fonts. Fix (fork 2b1b05571): the reader bundles DejaVu Sans, Serif and Sans Mono in all four styles (licence included; the jar grows 5.8 → 8.7 MB) and measures text with them only. After the fix, page 1 reads identically on this PC, on pc1 and with production's fonts only. Every set gives the same result as before here, since these are the same font files this PC already had.

**Release checks (build `5.11.0-sma.5` = `sma-pitch` 2b1b05571).** A different-model review of the fork diff found three robustness issues, fixed in cf2daea4f: a key change was cancelled against the wrong key, octave-line ink reads lacked a bounds check, and a chord without a center could crash the trailing-key check. One more change was tried after review and dropped: sizing small accidentals by their staff's spacing cost pitches in 8 PDFs. Five sets: 101 silent bars, flagged bars 318/63/46/60/28; second set flagged 453; identical on the farm and on this PC alone, PDF by PDF. Unseen set `bench-pitch` (40 PDFs, aggregates only, first run): pitch 0.9397 → 0.9457, pitch+onset 0.8707 → 0.8778, flagged bars 152 → 154, one PDF fails to read in both. On the release jar: full suite 1,246 passed, `diff_check` pdfwarn 0 of 80 changed. In `test_awkward`, 195 passed and one analysis-model test timed out under parallel load; rerun alone, all 11 of those tests passed in 7 s. They don't use the PDF reader. The reader label moves to `5.11.0-sma.5`, so earlier cached readings are not reused.

- **Staging, reader 5.11.0-sma.5 (2026-11-03, revision 00071):** startup clean (only the usual deprecation warnings). Mutopia Beethoven Op. 18 No. 4/iii (5 pages) sent as ChatGPT does: read in 82 s (OMR 68 s), first setting accepted with no problems, no errors.
- **Production, reader 5.11.0-sma.5 (2026-11-03, revision 00043):** startup clean, no errors logged. The same Beethoven PDF read in 132 s (OMR 109 s, against 68 s on staging; not investigated). Through the public domain, a test client's first call for a new read errored after about 125 s, on that PDF and on Chopin Op. 10 No. 1. Sending the same file again returned the result (1 s and 16 s). The domain is behind Cloudflare, which is the likely cut-off, not confirmed. Not new in this release: entry on 2026-11-01 saw ChatGPT re-send at 125 s. Plugin 1.7.0 not released yet.

### 102. Printed flats lost on old LilyPond PDFs, a regression in 5.11.0-sma.5 (2026-11-03)

**Problem.** The owner compared the production card of Beethoven Op. 18 No. 4/iii (Mutopia, LilyPond 2.8.5) with the print. Printed flat signs in the reading: previous reader 46, sma.5 2; 51 notes lost their flat. Entry 100's rule lets a sharp, flat or natural under 2.15 spaces link only to a small head. This font's normal flats are 41-44 px at interline 21, so they counted as grace-size, found no head and were removed. None of the benchmark sets had such a font (flat signs 222 before and 224 after on LilyPond PDFs), so nothing showed it.

**New set.** `bench-oldly`: 20 Mutopia PDFs from LilyPond 2.8-2.12 with OpenScore or DCML references, chosen by a rule written before any reading.

**Fix (fork cb7eef15d, reader sma.6).** A sign is grace-size only if it is also under 0.85 of the upper quartile of its shape's heights on that sheet, so size is judged against the score's own font. Lowering the limit to 1.5 spaces was tried first and lost 22 notes net on the main sets; judging within one system lost more than judging across the sheet; also accepting a small head beside the sign changed nothing and was removed.

| | sma.4 | sma.5 | sma.6 |
|---|---|---|---|
| `bench-oldly` correct pitches of 29,405 | 26,567 | 26,675 | 26,765 |
| `bench-oldly` flagged bars | 195 | 196 | 196 |
| This Beethoven, printed flats | 46 | 2 | 49 |
| Five sets, silent wrong-pitch bars | | 101 | 106 |
| Second set, silent wrong-pitch bars | | 120 | 120 |

**Cost, accepted by the owner.** Five main-set PDFs lose 17 notes (K545 LilyPond 8, Cornelius *Auf eine Unbekannte* 4, C.P.E. Bach H186 in two editions 2 each, Polonaise No. 3 LilyPond 1): grace-size signs that do not stand out from the page's larger signs. Flagged bars are unchanged on the main sets. `bench-oldly` has now been read three times for totals, so a fresh unseen part is needed before later fixes.

**Review (Sonnet, static read of cb7eef15d).** Three points, none changed the release. A sign not yet in a graph compares its height with itself, so it never counts as small; that path is only adding a sign by hand in the desktop editor, which our reading does not use. A sheet with one sign of a shape, or only grace-size signs of it, does the same, so a lone cue flat may link to a normal head when no small head is in reach. Each call scans the sheet's signs of that shape; its cost was not timed separately.

### 103. Octave lines: the search stopped on "va", and signs read as words (2026-11-03, not released)

**Problem.** On Chopin Op. 10 No. 1 (Mutopia) most printed octave lines came out too short: 43 of 255 notes under them were moved up. The search for the dashed line looked 3 spaces past the "8" and landed on the letters "va". 12 of 42 lines were read as text such as "8va------", so no line existed at all.

**New set.** `spike/omr/bench-octave`: 12 Mutopia piano PDFs that print a sign with a dashed line, chosen by a written rule before any reading, 90 signed lines. Scored against the lines in the PDF's own drawing data, half tuning and half unseen by hash. The older sets cannot test this: octave lines appear on 7 of 83 PDFs and those engravers mostly already worked.

**Fix (fork 95778bd83).** The search now looks 6 spaces past the sign. A word starting with 8, 15 or 22 becomes an octave line only if a real dashed line follows it. Words made only of a line's dashes are removed.

| Signed lines | sma.6 | fix | out of |
|---|---|---|---|
| Unseen half: found | 33 | 35 | 38 |
| Unseen half: end within one space | 0 | 34 | 35 found |
| Unseen half: notes moved under the line | 87 | 801 | 870 |
| Tuning half: found | 44 | 44 | 44 |
| Tuning half: notes moved under the line | 285 | 702 | 708 |
| Notes moved outside a printed line | 0 | 0 | |

Chopin: lines 31 (longer search only) to 38 of 42, notes 43 to 223 of 255. Six older sets, 103 PDFs: correct pitches and pitch with timing unchanged on every PDF.

**Limits.** 8 of the 90 signed lines landed near no read staff and were not scored; the cause was not checked. The unseen half is partly seen: per-piece counts were read and one piece (Pease, Amaryllis) was opened to debug the line list, which had stopped at the join where one line is drawn in two pieces. 4 Chopin lines stay missing because OCR garbled the sign ("81161"). "Lines read with no printed line" rose by 3 on each half; the tuning half's three are real short lines too short for the list, the unseen half's were not opened.

**Review (Sonnet, of the first commit).** Dashes read as separate words stayed behind as text: fixed, as a class, by the removal above. Left as is, since a dashed line must follow: a lyric or chord name starting "8-" could convert, and "80" passes the word test (it is how "8va" is sometimes misread). The final commit was not reviewed separately.

**Status.** Local fork only. Full test suite, `test_awkward` and `diff_check` NOT RUN on this build.

### 104. A review of the reading work, and what it changed (2026-11-04, not released)

**Question.** Should the reader repair bars that do not add up by thinking like a musician? An Opus review (`spike/omr/review-2026-11-04/musician-logic-review.md`, with rules and scripts beside it, about US$20-22 by its own estimate, over the US$10 limit) tested that first. When exactly one edit made a bar add up, it was right 0 of 47 times, and a right edit existed in only 11% of wrong flagged bars. Adding up is not evidence. Harmony checks barely beat chance (AUC 0.50-0.62). Checks against firm conventions did work. The owner adopted its order.

**Claude on crops (blind, 24 wrong flagged bars).** 9 exact against 0 for the reader, notes right 216 to 367 of 493, 3 bars made worse; between its go and stop lines. About US$0.09-0.30 per bar. Owner decision: only in the user's own chat, only where we doubt a reading, shade kept. Not built.

**Scorer (`spike/omr/speed/whole_bars.py`).** A bar is exact when pitch, onset, printed value, printed rests and ties all match, per part and staff; a failed PDF counts all its bars as wrong. A reference scored against itself gives 100% on 16 scores.

**Crashes (fork).** Two PDFs gave no music. A failed sheet now loses that page, not the book. Competing flags on a stem counted together (25 candidates, 37 flags) until a duration overflowed, because our tuplet code reads durations before reduction: they now count once. A metronome whose letters have no location has no glyph. Removing a symbol survives links removed by its own removal; the octave change exposed this on Faure's C'est l'extase. The benchmark caught a partial first reading stopping the second, so a skipped page now lets the second reading run.

**Lost last flat (fork).** `minFlatTrail` 0.7 to 0.5. Three old LilyPond PDFs gain 396 right pitches; none of 183 lose any. The review suggested judging against the file's own flats; this constant was enough.

**Part joining (fork).** A system with the same part, staff and line layout as the known parts holds those parts, whatever OCR read as names. Wrong part count 33 to 13 of 183.

**New warning (`engine/read_pdf.py`).** Shade a bar when notes in different voices line up at different times, or share a time more than 2.5 spaces apart. On references it fires on 0.03% of bars. Unseen set, measured with the check removed from the baseline: 55 flags on unshaded bars, all right, no false flags, 29% of silent timing errors. An earlier reading of 0.8% was a measuring mistake (the bars were already shaded). The user-facing sentence changed; it needs the owner's look.

**Bar 16 (fork c1a864c06).** A stemless head shares a slot with a nearby head only when they touch. Chopin Op. 10/1 bar 16 is now right. Tightening `maxAdjacencyXGap` to 0.2 was tried first: same-time bars 671 to 675, timing worse on four sets, dropped. The narrow rule moves that count only 671 to 668 and costs 4 notes of 183 PDFs, so it fixes this bar and not a general class; the review's stop rule for that class failed.

**Retiming (not built).** Re-timing chords from a complete voice, through `speed/retime_test.py`: +0.30 point of pitch with timing, 232 bars, one set -0.09. Between go (+0.5, no set down) and stop (+0.2). Owner decided on 2026-11-04 to skip it.

| 183 PDFs, tuning sets | sma.6 | now |
|---|---|---|
| Bars exact, parts kept apart | 47.9% | 55.2% |
| Bars exact, parts pooled | 54.1% | 62.2% |
| Notes, pitch | 96.1% | 98.0% |
| Notes, pitch and timing | 89.4% | 91.1% |
| PDFs failing | 2 | 0 |
| Wrong part count | 33 | 13 |
| Wrong bars with no warning | 69.9% | 55.0% |

| Unseen set, 40 PDFs (aggregates only; before bar 16) | sma.6 | now |
|---|---|---|
| Bars exact | 54.3% | 68.3% |
| Wrong part count | 9 | 0 |
| Wrong bars with no warning | 72.1% | 59.8% |
| Notes, pitch / with timing | 95.1 / 88.5% | same |
| PDFs failing | 1 | 1 |

**Real scans (`spike/omr/bench-olimpic`, 40 single systems).** 9.9% of bars exact, notes 70.0% and 51.1%, 6 failing, unchanged by this work. Short and sometimes tiny systems, and 36 of 40 time signatures were inferred, so this overstates the gap on full pages. It is below the review's 40% line where scan work outranks the rest; owner to decide.

**Review (Sonnet).** A book where every page failed reported success: fixed, the step now fails when no page is left valid. Left as is: the parallel path in `reachBookStep` still fails the whole book (not used by default); `invalidate()` can throw inside the catch, no worse than before; the flag overlap test could undercount a tall flag box next to a real stacked flag (no case found in 183 PDFs); the column check compares voices on different staves (0.03% on references).

**Text by meaning (`engine/read_pdf.py`).** Text is kept or dropped by what it means, and expression words and dynamics printed as lyrics in a part that is not sung become directions. A part counts as sung when split syllables are at least a fifth of its lyrics. Dynamics found 78.6% to 83.5% and right 76.6% to 77.6%, measured by applying the clean-up to cached readings. Footer text such as "www.LilyPond.org" stays as lyrics.

**Split bars (fork bc9eb26b3).** A bar printed across a line break, with no closing barline and two parts that fill one bar, now takes one bar number, as the second half of a repeat already did. Chopin Op. 10/1 gives 5/X5 and 18/X18. On 183 PDFs one reading changes (Clara Schumann's polonaise, bar X43, which ends two bars from the reference's count instead of three); no score moves, wrong bar count stays at 29 of 183, and no flag changes. It corrects numbering, not notes. The two halves stay two measures in the file.

**Lost rests (not applied).** In Beethoven Op. 18/4 iii bar 8, removing staff lines clips the rest's thin tail (4 rows of 48), the classifier scores it 0.09-0.35 instead of about 0.95, and the weak-grade filter deletes it. A patch restoring that ink cut lost rests from 94 to 17 and 112 to 28 on two exposed old LilyPond PDFs, but on the rule's 20 test PDFs it found 1 of 119 lost rests, added 7 false ones, raised flagged bars from 123 to 131 and lowered exact bars from 71.15% to 70.5%. So the cause is specific to that font and other PDFs lose rests some other way, not traced. Rejected under its rule. The repeat at bar 8 of that movement stays wrong because the two halves cannot sum without the rest.

**Ties, wider setting (rejected).** Raising `maxTieIntersection` from 0.25 to 1.0, on 83 PDFs: exact bars 67.0 to 66.9, 62.5 to 61.1, 53.4 to 52.4 and 63.6 to 63.0, with one set up 47.9 to 48.6; bars that do not add up rose on three sets. In the current reading 2,563 of 3,625 true ties are found with 907 extra, and 341 of 8,246 paired bars (4.1%) are wrong only by ties.

**False ties (fork 7b4503617).** A curve over staccato dots, or a piece of "Ped." or a tuplet bracket, linked to two same-pitched heads was taken for a tie; the two places that decide a same-staff tie never checked that the curve reaches the heads. Each end must now lie within 0.9 interline of its head (on 11 PDFs: true ties at most 0.8, 89 of 116 false ones at 0.9 or more). Exact bars 55.20% to 56.53%, every set up, no PDF down, 84 of 110 bars gained outside the evidence PDFs. Extra ties 907 to 537, lost ties 1,062 to 1,058, so lost ties remain: 660 have a wrong or missing note at an end, 66 cross a page and none of those are read. Pitch unchanged, timing 91.09 to 91.13, flagged bars 1,461 to 1,453. Cost: a false tie sometimes fed timing, so removing it can move notes (Erlkonig bar 12, 9 of 9 notes timed right to 5 of 9; pitch-and-timing bars on that set 80.68% to 80.23%). Reviewed by Sonnet, no defects. Passed the rule written before the change.

**Voices and triplets (tests only, on entry 95's assembler with exact symbols; script `spike/omr/speed/vector_ceiling/voices_triplets.py`).** Baseline reproduced: 2,586 of 2,902. Voices by the stem rule: 44.4% of two-voice bars, unchanged, under the 55% stop line, so voice work is not built. The rule detects well (220 of 266 true multi-voice bars, 27 of 2,636 one-voice) but all 252 bars already split by stems; timing within the voices is what fails. A design placing notes by column is untested. Triplets by beat columns: 27.5% to 44.0% of triplet bars, between the lines (stop 40%, go 60%), owner to decide; 13 other bars go wrong, overall 89.1% to 89.2%, 27 of 2,811 non-triplet bars get a false group. Solo lines not tested. Not a gain for today's reader either way.

**False marks (fork dbe09b8a6).** Counting only notes with right pitch and onset, 2,087 false marks read, not the review's larger counts (`barparse.py:138` reads only the first `<notations>` block, which hides real marks; not fixed). Of 200 labelled by hand, text ink was about half and only 54 of 103 sat on real PDF text, so masking text ink, the review's idea, was not built: it cannot help scans and misses "Ped." and LilyPond digits drawn in music fonts. The cause fixed: a staccato or tenuto was accepted up to 5 spaces from its chord. The limit is now 2. False marks 2,087 to 1,457 (-30%, -34% without 3 PDFs printed from another edition, the rule's figure), true marks 10,005 to 10,015, exact bars 56.53% to 56.59%, pitch and timing unchanged, read time unchanged within noise. About a quarter of the sample (real marks the reference lacks, fermata dots) cannot be reached this way. One rejected dot became an augmentation dot (p-op26n04--vr bar 23, -10 timed notes); dotted notes rose 6,925 to 6,934, how many are right unchecked. Wrong bars with no warning 1,604 to 1,607. Reviewed by Sonnet, no defects.

**Final build (`aud-marks1`, fork dbe09b8a6, not released).** 183 PDFs: exact bars 47.9% to 56.6%, pooled 54.1% to 63.8%, wrong bars with no warning 69.9% to 53.7%, pitch 98.0%, timing 91.1%. Unseen set, 40 PDFs, aggregates only: exact 54.3% to 70.3%, wrong bars with no warning 72.1% to 57.1%, pitch 95.1%, timing 88.5%, 1 PDF failing, wrong part count 0. Full suite with this reader: 1,281 passed, 0 failed, 4 skipped, 2 expected failures. `diff_check pdfwarn` against main compares engine code over cached readings, not this reader: 41 of 80 inputs gain warned bars, 127 added and none removed, from the new warning. Its other areas NOT RUN.

**sf.** After the clean-up, across 183 PDFs, 818 `sf`-type dynamics are read against 825 in the references, with none left as words or lyrics (a count, not matched by position).

**Owner decisions, 2026-11-04.** The new warning wording and extra shading stay, false alarms accepted (examples shown were rendered locally, not in the apps; of 40 PDFs each gaining one shaded bar, 34 bars were really wrong and 6 were right). The false-tie fix stays. The old-LilyPond rest patch is skipped. Scanned paper is next; photographed music is out of scope for now. Release later.

**Limits.** The review's bars and sets are now used bar by bar, so the next change needs a fresh unseen set. Runs in this entry were on this PC alone, except part of the octave work. One PDF, p-op26n04--ms, varied between benchmark runs but not when read alone, so a load effect remains in the numbers.

### 105. The first call: Cloudflare's 125 seconds, not ChatGPT's (2026-11-04, not released)

**Correction to entry 86.** It says ChatGPT gives up on a call after about two minutes. The cut-off is Cloudflare, in front of our public address: an HTTP 524 at 125.2 s on a 7-page PDF while the server finished at about 200 s, and the same kind of call direct to Cloud Run returned normally after 237 s. Only Cloudflare's Enterprise plan can raise the limit. The server sends nothing until a read ends, so any longer read loses its first reply.

**Size.** 15 of 25 new reads on production since 11 October ran past the limit, some possibly our own tests. 12 of the 15 show a re-send at about 125 s; about 9 got a result within 15 minutes, matched approximately.

**Fix on branch `sse-keepalive` (`json_response=False`, staging test only).** Tool calls answer as an event stream with keep-alive pings. A Worker test showed pings pass Cloudflare at 151 s. ChatGPT on staging, one request each with the card shown: 79-121 s on five PDFs of 4-8 pages. Claude: short calls only, under a second, with the player shown; sound NOT RUN.

**Limits.** No single test has ChatGPT, pings and Cloudflare together past 125 s, so the last check is on production after release. The branch's full suite and review have not run. Production reads looked about twice as slow as staging on a few reads that day, though their settings match (Op. 10/12: 171 s of reading against 88 s); not explained.

### 106. Scanned paper: what is wrong, and a target of 75% (2026-11-04, not released)

**Owner's target.** Above 75% of bars exact on real full-page flat scans. Photographed music is out of scope. Clean PDFs are at 56.6% (tuning) and 70.3% (unseen), so this asks for more than clean PDFs give today; small fixes will not reach it. Findings: `spike/omr/review-2026-11-04/scan-diagnosis.md`.

**Is the test fair?** Partly. `bench-olimpic` (now 80 single systems, half unseen): 12.9% exact, pitch 72.9%, timing 55.0%, 11 failing. The same inspect half goes 14.5% to about 20% with true page sizes. Supplying time signatures changes nothing. Five real full-page scans: 55.7%. Same music, real scan against clean PDF: Chopin 46.2% and 84.6%, Mozart 35.6% and 76.7%. The `--scan` PDFs in `bench` are renders made to look scanned (pitch 98.5%) and measure nothing about scans.

**Causes, 198 wrong bars of 326.** Heads missing or extra 43, no reading 29, clefs 27 (5 are reference errors), onsets 22, accidentals 15, rests 14, octave 14, keys 10. Painting in one bass clef took right pitches from 53 to 101 of 115; painting in rests on one PDF took timed notes from 30 to 40 of 48. The reader does no pre-processing of scans; deskew was mixed (+1.8, -2.7), binarizing gained nothing, scaling at most +3.

**Heads.** 97 missing: black head with no stem 21 (`SigReducer.java:765`), ledger discarded so the pitch is never scanned 16 (`LedgersPostAnalysis.java:299`), right place but wrong alteration 16, lost exclusion 15 (`SIGraph.java:1282`), no candidate 11, wrong pitch or bar or not exported 12, seed conflict or low grade 6. No single cause dominates. A wider ledger filter gives +7 and -3 of 243 bars on scans; clean PDFs 1,376 to 1,380 of 1,914, with 5 PDFs each down a bar, not inspected, so not applied. Stem changes fixed no bars. The earlier guess of +5-10 points does not hold: about +1 by estimate.

**Crash (fork, on `sma-pitch`).** A page whose durations were all a half or longer wrote `divisions` 0, which raised ZeroDivisionError in `engine/score.py`. The page's divisor now always covers a quarter. 1 of 14,018 cached readings had this. The new test fails on the old reader and passes on the new one; five readings with unusual divisions are unchanged. That PDF reads 4 bars, none exact, 10 of 20 pitches, and nothing is flagged.

**Test set, blocked.** `spike/omr/bench-scan` holds a random draw of 60 pieces matched to the exact IMSLP edition, split before reading, and one PDF. IMSLP forbids automated access in `robots.txt`. At the owner's direction I drove the owner's browser anyway, opening 58 pages then 10 download pages within seconds, and that triggered IMSLP's site-ripping ban on the owner's connection. My pacing caused it. All further files come by hand after the ban ends; IMSLP is not to be automated.

**Clefs traced, and two earlier figures corrected.** Of the 27 clef bars above, 16 are real reader errors, not 22: 11 are reference or edition differences or a clef counted in the neighbouring bar, and on `6984553-p2-s1` only 2 bars are the reference's fault, not 5. Of the 16: 6 first-of-system bass clefs whose knob is never joined to the arc (`ClefBuilder.java:719`), 5 small mid-staff bass clefs lost, 3 knobs read as note heads, 2 false clefs on chords. The best candidate retries with a wider gap only when a staff has no header clef and also sets `maxLineOffset` to 0.8. On 43 scan PDFs, 326 bars: exact 128 to 132, pitch 3396 to 3455, none worse. On 60 clean PDFs: exact 1480 to 1480, pitch and timing +3, no PDF lost anything; that mostly tests the offset, since the retry should fire rarely and its firing was not counted. The wider gap everywhere failed (two PDFs lost 18 to 16 and 38 to 31), and a bass check on note heads failed (Grieg 41 to 32). Worth about 1 point, not my earlier guess of 3-6, and 1.5 and 0.8 were the first values tried on these same PDFs. Not applied to the reader. NOT RUN: test suite, `test_awkward`, `diff_check`, unseen half, other clean PDFs. Details: `spike/omr/review-2026-11-04/scan-diagnosis.md`.

### 107. Scanned paper: a second reader, not released (2026-11-04)

**Tried.** homr, the neural reader passed over in entry 31, alongside the current reader on scans. For each staff of each bar: if the notes differ, take homr's unless only the current reader's staff adds up; if the notes agree, keep the current reader's unless only homr's adds up. No reference is used. Spike code only; nothing in `engine/`, nothing deployed.

**Result, real merged files.** Five real pieces, 11 pages: exact 141 to 174 of 253 (55.7 to 68.8%); requiring ties too, 139 to 173 (68.4%); requiring grace notes too, 127 to 161 (63.6%). Pitch 89.2 to 94.9%. The owner's goal, 65% of the way from 55.7 to 75, is 68.2%. Mozart gives over half the gain, which fails the rule written beforehand, and one piece moves the score about 10 points. Single-line scans: inspect half 14.5 to 49.4%, unseen half 11.2 to 47.2%, and most of that is homr alone, not the merge. homr's training data includes the source of those references, so treat them as a ceiling.

**My first figure was overstated.** I reported 68.4% from merged files that had lost accidentals, ties, rests and key changes. An Opus review found this: homr writes no accidentals, ties or beams, and my cleaner deleted real rests and key returns. Corrected and rescored; baselines rescored the same way. It also showed my three-part explanation of the drawing crash was wrong: adding the staff count and handling rests in chords prevents the crash on all 85 files without the third change, but the segfault itself was never traced.

**Limits.** Every scan scored is piano-style. On clean several-part PDFs homr alone gets 14.4% against 50.8%, so the merge is switched off for several parts and tomorrow's songs may gain nothing. Clean PDFs, 60: current 53.6%, homr alone 21.3%, so homr does not replace the current reader. On the page: homr's bars have flags, not beams; the current reader's false key changes remain.

**Cost.** Cloud Run job, 4 vCPU, 4 GiB, since deleted: 14-46 s a page, mean 26.6, peak 1.2 GB, about US$0.003 a page at list rates. About US$0.35 a month on an assumed 120 pages; about US$13 at the daily limit, 2.6 times the target, and production has run 1.6-1.9 times slower than staging. Memory with both readers and the server together not measured. Claude users read in their own sandbox and get no gain unless homr runs there: 728 MB, not tested.

**Licence, for the owner.** homr's code and weights are AGPL-3.0. Its FAQ says every released checkpoint includes a dataset marked non-commercial on one copy, and calls the carry-over an open legal question.

**Flagged by the review, not yet corrected above:** the unwarned baseline 69.9 in 104 is the old engine (63.5 on today's), while the unseen 72.1 is today's; "about 20% with true page sizes" in 106 is 16.9 on the review's count; exact bars ignore grace notes; the catch path at `Page.java:206` still returns 0 and `engine/score.py:139` is unguarded; the OLiMPiC PDF in `tests/data` has no credit. The review's "12 fork commits exist only under /tmp" is wrong: they are in the local mirror, not on GitHub. NOT RUN: test suite, `test_awkward`, `diff_check`, real voice-and-piano scans, both readers in the server path. Details: `spike/omr/review-2026-11-04/opus-review.md`, `scan-two-readers/RULE.md`.

### 108. Usage report counted staging and overstated "since launch" (2026-11-05)

**Problem.** `tools/usage_report.py` read logs from every Cloud Run service, so its daily rows included staging and our test runs. Its "ChatGPT users since launch" counted only permanent codes, which began on 2 Nov; users before that have daily codes that can't be linked.

**What we did.** The log query now reads only the production service, and the line says "since permanent codes began on 2026-11-02". The total stays at 6.

**Before and after, ChatGPT users per day:** 1 Nov 6 to 5; 4 Nov 2 to 1. Both now match the production log lines grouped by code. Claude drafts on 24 Oct went from 971 to 1.

**True total since launch:** still unknown. There are 6 permanent codes and 12 daily codes from 31 Oct to 2 Nov, so 6 to 18 people, not counting ChatGPT calls from 28 to 30 Oct, which logged no code.

### 109. Reader sma.6 released, and what CI had not been testing (2026-11-05)

**Released.** Production revision `sheet-music-analysis-00044-v72` runs reader 5.11.0-sma.6 from entry 102, the fix for the lost flats, and plugin 1.7.1 points at it. Production users had the bug from 2026-11-03 until this deploy.

**CI failed first, not because of the reader.** Seven draft tests failed with `.venv-agnn/bin/python` missing. The runner's Python moved from 3.11.17 to 3.11.18, and the model cache key did not include the Python version, so the restored environment was still used. The likely cause is its interpreter link pointing at the old version; the link itself was not inspected. The key now includes the version.

**A gap found on the way.** CI's reader was still sma.4, so sma.5 and the first sma.6 run were never tested with the reader they shipped. CI now uses sma.6: 1234 passed, 14 skipped, 2 expected failures. The workflow's reader must change with `Dockerfile.base` and `skill/scripts/read_pdf.py`.

### 110. Two-page card and event-stream answers released (2026-11-05)

**Released.** The two-page PDF card and the event-stream answers from entry 105, on owner's yes. `text-meaning` is left out; it was not in the release list. Plugin 1.7.2 only drops the unused `tall` card code from its engine copy.

**Checks.** Sonnet review: one bug, `tools/load/drafts.js` could not parse an event stream, fixed; the parser was run on a sample answer, no k6 run against a server. Full suite on a local sma.6 reader: 1 failed, 1247 passed, 4 skipped, 2 expected failures; the failure, `test_draft_analysis_checks_typed_answer`, was a model timeout under parallel load and passes alone (10 of 10 in its file). `test_awkward`: 196 passed, 2 expected failures. Staging, direct to Cloud Run: a 5-page Beethoven PDF read in 119 s, caption "first 2 pages", `content-type: text/event-stream`. 
**Production, revision `sheet-music-analysis-00045-6px`.** Startup clean, no error lines. An MCP client through the public address read Beethoven Op. 10 No. 1/i from Mutopia in 145 s with no error, past Cloudflare's 125 s limit; two shorter PDFs took 92 s and 89 s. The caption read "first 2 pages". 

**ChatGPT itself, 2026-11-06, revision `sheet-music-analysis-00046-cdp`.** The published app in real ChatGPT read Beethoven Op. 10 No. 1/i, from Mutopia: one `/mcp` call of 149.6 s with status 200 from `openai-mcp/1.0.0`, log line platform chatgpt, the card drawn with the first 2 pages, about 2 min 36 s in all. So the event stream carries a real ChatGPT read past Cloudflare's 125 s limit.

**Section fix, revision `00046`.** Plugin 1.7.3 and production carry the section fix from the entry above. Beethoven Op. 49 No. 1/ii through the public address: 160 s, no error. A PDF that really splits was not sent through the production server.

**First section only: later movements were dropped (branch `first-section`, not released).** `audiveris_read` kept `scores[0]`, so when the reader wrote several `.mxl` files the rest vanished with outcome "done". The reader splits for two separate reasons, both in `Book.createScores`: an indented system starts a movement, and an invalid page breaks the score. Fix: `indentations=false` in both settings, so the reader's own part matching gives one score, and `join_movements` for what is left, which is the invalid-page break the switch cannot remove. `READER` bumped to r9 so truncated cached readings are not served.

Measured with baseline launcher marks1. Quick set, 49 clean PDFs: 0 split; first-only, keep-all and switch gave identical exact, pitch and timing per PDF (exact 60.4, pitch 97.7, timing 89.6). Choir book, 13 pieces: pitch on the four short pieces with keep-all 62.7, 80.6, 73.1, 73.2; with the switch 66.3, 80.6, 73.1, 73.3, which reproduces the earlier switch figures. Exact bars stay at 0.1% and bar counts stay wrong (148 for 71 on piece 1); that is a separate fault. Real multi-movement PDFs, first 8 pages, bars kept by first-only against all files: Chopin Op. 6 75 of 239, Op. 67 59 of 256, Op. 68 72 of 242, Beethoven Op. 49/2 122 of 243; Debussy Suite did not split. With the switch all of that music is in one file. On the book, setting 1 still split on invalid pages with the switch on (5 pieces, part layouts differing on 2), which is why the switch alone is not enough.

**Fork attempt.** Removing the invalid-page break from `Book.createScores` (local fork branch, b5de7b142, on 378e4fd6d) did not stop the split: all five book pieces that split on an invalid page under setting 1 still wrote 2 or 3 files, because `Book.updateScores` has its own page-by-page gathering. Changing that as well is more than a small change, so the join stays. Bars with the fork build and with the join were equal on all five: 94, 144, 37, 113, 172.

**Wider measurement.** bench-oldly and bench-tune2, 100 PDFs, against marks1 with `whole_bars`: exact 39.4 and 60.7, pitch 98.0 and 97.7, timing 95.0 and 88.9, all unchanged, and 0 PDFs changed in exact, pooled, pitch, timing, unwarned or bar count. One clean PDF split under setting 1 (p-webern-anton-2-noch-zwingt-mich-treue--ms, invalid page 2) and its chosen reading was unaffected. Median read seconds were lower than the baseline's (oldly 139.6 to 96.7, tune2 82.9 to 50.9) but the baseline ran under a different load, so this says only that no large slowdown appeared. `tools/reading_coverage.py` lists the four first-only book readings (5 of 71, 27 of 63, 3 of 38, 11 of 95) and none of 113 readings after the fix. bench, heldout and bench-real beyond the quick list were not re-read with the switch.

**Limits.** The join's padding for differing part layouts was checked by rendering 17 saved real readings, not scored. Timing was not compared under equal load.

**Review (Sonnet), one bug.** Parts were matched through a one-way iterator, so an extra voice in a later section walked past the piano and the piano became a second part, silent for 123 bars. A passed-over part now stays available; on the choir fixtures there is one piano with notes in all three sections, and a stray ninth voice remains for the eighth voice the reader found only in section 3. The existing test passed despite the bug, so it now checks this. Full suite before this one-line correction, on reader sma.6 (checksum matches the pin): 1251 passed, 4 skipped, 2 expected failures; after it, `test_read_pdf` and `test_awkward`: 235 passed, 2 expected failures. Chopin Op. 67 in the Joseffy scan read as one score of 56 bars, the second mazurka starting after a double bar with its own key and metre; its pickup shares number 31 with the bar before. NOT RUN: a multi-section PDF through the staging server (no public address; a signed link was refused); the switch on the other benchmark sets.

### 111. ChatGPT listing, version 1.1.0 prepared (2026-11-06)

**Checked on OpenAI's dashboard.** Version 1.0.0 is published and listed publicly, with no review in progress. The cached descriptions of `render_analysis`, `read_pdf`, `draft_analysis` and `correct_bars`, reviewed 2026-11-02, match production word for word, which supersedes the "old 32-bar tool text" note in the entries above. Schemas and `rate_analysis` were not compared.

**What is out of date is the public listing text:** it offers MusicXML only, says each page shows up to 32 bars, and quotes 71% against 78% on 12 pieces. The site says 67% against 71% on 30 unseen pieces.

**Prepared.** `openai-plugin/plugin.json` 1.1.0 adds PDFs to the description and capabilities and a reviewer test case with a public Mutopia PDF, which read on production in 99 s with the right card. Uploaded as a draft, no findings in OpenAI's automatic check; the owner made the declarations and submitted it on 2026-11-06. Status: in review, estimated completion 2026-11-07. Version 1.0.0 stays live until then.

### 112. The Claude directory's credential hold, traced to environment reads (2026-11-06)

**The problem.** The Claude directory holds v1.7.3 for "Uses a credential from the user's machine" (`MCP_FORWARDS_CREDENTIAL_ENV`), pointing at `.claude-plugin/plugin.json`. The plugin has no credential: `.mcp.json` is only the server address, and the connector needs no key.

**How it was traced.** The rule is not documented, so each version's findings were compared with its code. v1.0.0 had no `engine/read_pdf.py` and no finding. v1.2.1 added the file, which reads `os.environ`, and the `plugin.json` finding appeared. v1.4.0 to v1.7.0 also had an SVG namespace URL in that file and a second finding on the file itself. v1.7.3 dropped the URL for another reason and the second finding went. `os.environ.setdefault` in `render.py` raised nothing. This is a correlation across versions, not the rule's definition, and it cannot separate the two reads, which always shipped together.

**The fix.** The shipped code reads no value from the environment; what remains is `os.environ.setdefault("FONTCONFIG_FILE", ...)` in `render.py`, which points the engine at its own fonts. The reader gets a fixed environment rather than a copy of the caller's, so it no longer sees any secret the caller holds. The engine's default reader path is a constant; `tools/robustness.py` and the tests read `AUDIVERIS` themselves, and the skill already passes its path. Two checks were added: the reader is not given the caller's variables, and no skill or engine script reads a value from the environment.

**Not known until the next scan.** Whether the hold clears. A reviewer is still required either way. The warnings on the PDF reader download, the fonts and the listing fields stay.
### 113. Carried state: seven defects found by audit, fixed on `fix-state-machines` (2026-11-06)

An audit of state that carries across calls, bars and voices found these. Each was reproduced on `main` before its fix; none was reported by a user. Released the same day as plugin 1.7.5 and production revision 00047, which also carries 1.7.4's reader environment. On staging revision 00078, the Chopin Op. 28 No. 4 PDF read in 62 s through that environment, and the rating came on the third of three renders in one chat.

- **Ledger hints judged a bar in the wrong clef.** Each bar and staff kept one clef, the last one read, and Verovio writes a clef that opens the next bar at the end of this one. Over the 61 corpus scores, 666 of 49,749 notes were checked against the wrong clef. Clefs now follow the notes, layer by layer. In all 27 corpus bars with a clef change and several layers, Verovio repeats the clef in every layer that has notes. Six scores change, all false runs: Haydn *She never told* 2-4 becomes 2-3 in three variants and 1-3 becomes 1-2 in the fourth; Schubert *Die Stadt* (raw reading) loses 3-4 and 24-25; Haydn 104 loses 192-194.
- **A tie broke on the same pitch in another voice when played.** Ballade Op. 23 goes from 5203 to 5200 notes: three written ties that were struck again now hold. No other corpus score changes.
- **Replacing a bar after a unison left one loose tie.** Only a constructed score shows it; the corpus has no unison ties across voices.
- **A key change inside a bar applied to the labels before it.** Only a constructed score shows it; the corpus has no mid-bar key.
- **`continue` on an octave line lost the line's start** in `clean`. Only a constructed score shows it; none of the tracked scores has one. `export.py` treats `continue` as a shift too, but left alone: all candidates for a label sit on one staff at one onset, so the choice cannot change.
- **A dead model worker was reported as slow, or as `BrokenPipeError`.** Both are now `DraftError` "stopped before answering".
- **Rating counter and the other machine's outcome.** The per-chat count is now conditional on the object's generation: four renders at once used to count as one and never reach the third. A saved busy or limit result returned by the other machine was logged as `user_error`; it now logs as busy or limit. The message users see was already right, so the audit's first description of this as a wrong answer was too strong.

Reproduced and left as they are by the owner's decision: the rating may return after `chats/` expires, as a chat idle over a day restarts its count, rather than keep those records longer; and a machine that dies during a read blocks that PDF for up to 900 s, as the marker must outlive the longest read (entry 86 quotes 300 s; the code has since become 900 s).

Checks: full suite with Audiveris 5.11.0-sma.6, 1266 passed, 4 skipped (no ring codes), 2 xfailed. `tools/diff_check.py --base main` typed, pdfwarn, export and render: no changes. A second model reviewed the diff.

### 114. Reader 5.11.0-sma.7 and the reading work of entries 103-107, prepared for release (2026-11-06, not released)

**What it carries.** Branch `release-reader-next` is `reader-next` merged with `main`, with both sides kept: from `main` the section fix, the fixed reader environment and entry 113; from `reader-next` the warning for notes that do not line up, text read by meaning, the skipped-page rule and the new wording. The reader is built from fork commit 378e4fd6d, 12 commits over sma.6, all on GitHub branch `sma-pitch`. The `read_pdf_work` log line gains two numbers, `bars` and `bars_shaded`. `READER` is `5.11.0-sma.7-best2-tuplet-rests-eight-leland-ocr-r9`, so readings saved under sma.6 are not served again.

**Checks.** Full suite with the sma.7 jar: 1300 passed, 3 failed, 4 skipped (no ring codes), 2 expected failures. The 3 failures were the draft model not answering within 180 s while another job loaded the machine; all 3 passed when run alone. `tools/diff_check.py --base main`: typed 191, export 6, render 28 and part writing 80 inputs unchanged; pdfwarn 41 of 80 inputs changed, 127 bars gained a warning and none lost one. That area runs the engine over saved readings, not the new reader. `tests/test_awkward.py` alone: 196 passed, 2 expected failures. A different model from the one that wrote them read the engine and server changes and the pin change and found no defect. One note from that reading: in a part where fewer than a fifth of the lyric syllables are split, a lyric word that begins like an expression mark ("dimly", "dolce") becomes a direction. The test bodies were not read.

**Three pages against the originals, full size, sma.7.** Every shaded bar had a real misreading. Each page also had wrong bars with no shading, none of them new in sma.7:
- Chopin Op. 28 No. 4: bar 11 loses a dotted half note, and in bar 16 the sharp of a turn is read as a double sharp on the note.
- Chopin Op. 10 No. 1: in bar 30 an octave line is cut short, so the second group is an octave low.
- Mozart K. 545, scan: in bars 1-4, 22, 29-30 and 33 the left hand's change to treble clef is missed and every note there is a thirteenth low (bar 1 reads E2 B2 G2 B2 for C4 G4 E4 G4).

Against sma.6 on the same pages: the Prelude and the Mozart read the same notes with the same shading. Op. 10 No. 1 gains its octave lines in about 45 bars that sma.6 read an octave low, and numbers 79 bars, as printed, instead of 81.

**Not done.** Publishing the jar on GitHub, the plugin build (`dist/` still names sma.6), CI, staging and production all wait for the owner. Until the jar is published, the download addresses in `Dockerfile.base`, the CI workflow and the skill do not exist.

### 115. What a ChatGPT user gets after a PDF read (2026-11-06)

**Question.** In the production logs of 3 to 6 November, four people outside our own testing uploaded a PDF. Three got a successful read in 44 to 110 s and made no further call; one of them came back the next day, read the same PDF again and again went no further. The fourth reached a marked page. All four people who uploaded MusicXML since 31 October reached a marked page. Why do PDF users stop? A fifth PDF "user" who stopped was our own test: the owner's ChatGPT account is one permanent code, now left out of counts.

**Method.** Two new chats in ChatGPT with the published app on production, each with the PDF attached and "Can you analyse the harmony of this piece?". Staging cannot be used for this: it refuses ChatGPT with 403.

| | Chopin Op. 28 No. 4, one page read | Mozart K. 545, scan, 4 pages |
|---|---|---|
| Wait for the read | 46 s | 97 s |
| After "Go ahead" | 63 s, 42 marks drawn | about 80 s, 79 marks drawn |

**What the user sees.** The card with the reading fills the screen, and the sentence asking the user to check it and say "Go ahead" is below the card. Neither reply passed on the notice, which names the shaded bars and says why they are shaded. For the scan ChatGPT wrote "The score-reading step has been initiated, but I haven't received a verified transcription to analyse yet", with the finished reading shown above it. In an earlier test the same day (Beethoven Op. 10 No. 1, 7 pages, 284 bars, 149 s) it asked the user to "compare the app's recognized notation against the original, particularly the notes, rhythms, accidentals, and rests". After "Go ahead", both chats called `read_pdf` again, which showed the same card a second time from the saved copy, and called `draft_analysis` twice. The cause of the repeats was not found.

**What it means.** The flow works from end to end. But a person who asked for an analysis waits one to two and a half minutes and is then given a proofreading job, in words ChatGPT chooses, with the instruction off the screen. That fits the three who stopped; it is not shown to be their reason. Nothing was changed: analysing straight after the read changes an approved tool description and is the owner's decision. The read's log line now records bars read and bars shaded (entry 114), so reading quality can be set beside who stops.

### 116. Reading judged by whether the analysis changes (2026-11-06)

**Question.** "Bars exact" asks for ties, rests and printed values to match. Does a gain there change the analysis?

**Method (`spike/omr/speed/analysis_match.py`).** For each benchmark PDF the draft model runs on the reading and on the true score, and the two drafts are compared the way `eval/run.py` compares a draft with an expert: the share of the piece, by duration, where key, chord and bass all agree. It is reported two ways, as in entry 85: as read (bars paired by number) and lined up (each read bar matched to the true bar with the same notes). No chat model is called. A true score against itself gives 100% on 181 of 183; one reference (2 PDFs) cannot be drafted and is left out.

| 183 tuning PDFs, reader build marks1, 176 scored | As read | Lined up |
|---|---|---|
| Key, chord and bass | 0.70 | 0.76 |
| Key | 0.91 | 0.92 |
| Root | 0.79 | 0.85 |

Five readings stop the draft model because a voice runs past the barline; a user would get the notes table with no draft. The five real scans in the sets score 0.50 as read and 0.64 lined up.

**Did the reader work move it?** From the sma.6 baseline (`pitch39`) to marks1, on the 174 PDFs scored under both, lined up rose from 0.728 to 0.764. Of that +0.036, +0.030 comes from three old LilyPond PDFs whose last flat came back (entry 104). On the other 171 the gain is +0.006, while bars exact per PDF rose from 0.535 to 0.630. Across PDFs, the change in bars exact and the change in this measure correlate at 0.16.

**Where the analysis is lost.** In the 15 largest losses: bar numbers shifted in 8 (four misread pickups, a lost pickup, a lost bar, a split bar, extra bars), a wrong or missing time signature in 3, triplets read as plain values in 2, wrong pitches in 1, and 1 or 2 where a few wrong notes changed the model's key over long stretches. The causes were judged from bar lengths and not checked against the printed pages.

**Entry 85's three scans** reproduce: Beethoven 0.36 as read and 0.72 lined up, Bach 0.34 both ways, Grieg 0.76 both ways.

**Limits.** The measure is agreement with the model's own draft of the true score, not with experts. One PDF's figure is good to about ±0.05 and can swing more when a few notes change the model's key; the pooled figure is good to about ±0.03. Grace notes count here and not in bars exact, and 617 of 1,439 are read. NOT RUN: the 40-PDF unseen set and the single-system scans.

**What it means.** Since sma.6, the reader work that changed the analysis was the key-signature fix. For the analysis, the reading errors that matter most are bar numbers at pickups, time signatures, key signatures and bars that overflow. Ties, rests and printed values matter little.

### 117. The test suite ran the draft model in every worker, each with 48 threads (2026-11-06)

**Challenge.** The full suite kept all 20 cores busy for 12 minutes and, when other work ran beside it, three draft tests failed with "AnalysisGNN did not answer in time".

**Cause.** Each test worker that reached a draft test started its own copy of the draft model, and each copy started 48 threads. With 11 to 13 copies the threads fought each other: the model's own work, 45 seconds when run once, took 2,611 seconds.

**Fix.** `tests/conftest.py` sets the model to one thread, and the 16 tests that use the model carry one `xdist_group` mark, so `--dist loadgroup` (now in `pyproject.toml`) sends them to a single worker. On one score, one thread gave the same labels as 48 (confidences differ in the fourth decimal) and was no slower.

| Full suite, 20 workers | Wall time | CPU seconds | Model copies | Model seconds | Failures |
|---|---|---|---|---|---|
| Before | 12:16 | 12,050 | 13 | 2,611 | 3 |
| One thread | 8:23 | 6,035 | 11 | 216 | 0 |
| One thread, grouped | 8:11 | 6,116 | 1 | 45 | 0 |

A fourth run, grouped, with no measuring attached and less other work on the machine, took 5:48: 1303 passed, 4 skipped, 2 xfailed.

**Memory did not change.** Peak use stayed near 22 GB in every run. At the peak of the fourth run the PDF reader's Java processes held 10.2 GB (12 running, up to 19 at once) and about 8 GB sat in 23 Python processes that are almost certainly the 20 test workers (not checked by process id). The draft model held 0.8 GB. Using less memory would mean fewer workers or fewer PDF readings at once; neither was tried.

**Limits.** Wall times were taken while other jobs ran on the machine, so only the CPU and model figures compare cleanly. A new test that uses the model without the mark still passes but loads a second copy; nothing checks for that.

### 118. A ChatGPT model as reviewer, and whether the draft model earns its place (2026-11-06)

**Question.** The public 67% was measured with Opus as reviewer, and every real user is on ChatGPT. What does a ChatGPT model score, and does the draft model help once the reviewer has the note table (entry 60 said no, on 3 pieces)?

**Method.** `eval/review.py` now sends the same review prompt to a `gpt-` model through `codex exec` (branch `eval-chatgpt-reviewer`). Each arm reviews the passages of the 30 held-out pieces (54 passages, 1,182 bars) with the draft in the prompt or with the note table alone. Every arm is one run. Cost is estimated subscription usage.

| Reviewer | Draft | Pieces | Key, chord and bass (30 / same 20 pieces) | First replies rejected | Cost | Seconds per passage |
|---|---|---|---|---|---|---|
| Draft alone | – | 30 | 0.481 / 0.484 | – | – | – |
| Opus, medium (2026-10-24) | with | 30 | 0.670 / 0.671 | 6 of 54 | $25.59 | 148 |
| Opus, medium | without | 30 | 0.680 / 0.684 | 13 of 54 | $30.95 | 192 |
| gpt-6.1-sol, Codex default effort | with | 30 | 0.638 / 0.627 | 34 of 54 | $0 | 97 |
| gpt-6.1-sol, Codex default effort | without | 20 | – / 0.672 | 19 of 39 | $0 | 88 |
| Sonnet (3 pieces) | with | 3 | 0.544 | 0 of 5 | $1.64 | 177 |
| Sonnet (3 pieces) | without | 3 | 0.601 | 0 of 5 | $2.04 | 120 |

**Without the draft minus with it, piece by piece.** Opus, 30 pieces: +0.010 (95% interval −0.032 to +0.054). gpt-6.1-sol, 20 pieces: +0.045 (+0.009 to +0.084), or +0.034 (+0.001 to +0.069) leaving out one piece whose with-draft passage never produced a valid answer.

**What the saved runs show about the draft.** The review fixes 0.24 of the music and breaks 0.05. The draft's confidence is calibrated, but labels at confidence 1.00 are right 0.62 of the time against 0.75 after review. The GPT reviewer follows the draft's wrong keys. The draft is about 17% of the prompt. In production, a draft call that runs the model takes a median 12.9 s, of which 10.4 s is starting the model and 0.5 s is the model; 5 of 41 ChatGPT draft calls failed or fell back.

**Why first replies are rejected.** In 43 of the 46 GPT cases with a saved error, and 8 of Opus's 13, the model put `staff` inside a region's `start` or `end`. The method text (`skill/SKILL.md`) says to give a region its `staff`, the annotation spec lists a region's fields as `start`, `end`, `label`, and the schema has `staff` on the region itself. Not fixed here. ChatGPT also receives the tool's schema, so the rate in the product may be lower; not checked.

**Limits.** One run per arm, so the 0.04 run-to-run spread is the earlier Opus figure, not measured for gpt-6.1-sol. The OpenAI no-draft arm stopped at 20 pieces when the ChatGPT plan's limit was reached: no Dvořák, Mozart, Schumann or Tchaikovsky and 1 of 4 Bach pieces. The Opus with-draft run used the method text of 2026-10-24 (1,129 words) and the no-draft run today's (1,391 words), so that pair also mixes prompt versions; the OpenAI pair does not. Codex's default effort is listed as low and ChatGPT's own default is Medium, which was not run. NOT RUN: second runs for spread, a smaller OpenAI model, the last 10 OpenAI no-draft pieces.

**What it means.** With the note table in the prompt, the draft is not shown to raise accuracy for any reviewer tried, and for the ChatGPT model it probably lowers it. A ChatGPT model at low effort with the draft, which is what the product sends today, scores 0.64 where the site says 67%. The part-writing check and the student check still read the draft's chords, so the model cannot simply be removed.

### 119. Is there a measure where experts agree and we do not? (2026-11-06)

**Question.** The owner finds "we score 0.67 and experts score 0.71" hard to explain, and asked for a measure on which experts agree with each other at 0.85-0.90 and which shows our real shortfall.

**Method.** Saved runs only, no model calls. About 20 measures were computed the same way for expert against expert (151 pairs), our Opus review with and without the draft (30 held-out pieces, 1,182 bars), the draft alone, and plain Sonnet and plain Opus (3 pieces). The scripts reproduce `compare()` on every piece and `ceiling.json` to 0.001. They are not committed; a copy is in `out/scoring-research-2026-11-06/`.

**A correction.** Entries 65 and 66 say our chords account for 0.71 of the notes against the experts' 0.90. That figure was measured over the whole piece, while a review labels only its passages, so its last chord was stretched over every bar after them. Inside the scored bars the figures are: experts 0.900, Opus with the draft 0.881, without 0.901, draft 0.841.

| Measure | Experts | Opus with / without draft | Draft | Plain Opus (3 pieces) | Plain Sonnet (3 pieces) |
|---|---|---|---|---|---|
| Key, chord and bass (*full*) | 0.711 | 0.670 / 0.680 | 0.481 | 0.64 | 0.42 |
| *Function* | 0.830 | 0.768 / 0.792 | 0.666 | 0.73 | 0.53 |
| Same root | 0.911 | 0.869 / 0.897 | 0.779 | 0.87 | 0.65 |
| Same family (tonic, predominant, dominant) on each downbeat | 0.921 | 0.865 / 0.898 | 0.804 | 0.89 | 0.70 |
| Chord fits the notes | 0.909 | 0.881 / 0.901 | 0.841 | 0.88 | 0.76 |
| Chord changes the other reading also has within a quarter beat | 0.886 | 0.841 / 0.873 | 0.749 | 0.86 | 0.79 |

**Result.** No measure has experts at 0.85 or more and our Opus review 0.10 or more below them. The expert figure of 0.711 is weighted by bars and led by long Beethoven movements; per pair it is 0.79, chorales 0.87, Beethoven 0.65, Chopin 0.59. On our 13 pieces in styles that have expert pairs, with the expert figure matched to the same mix of styles, *full* is 0.677 for experts against 0.689 for us with the draft and 0.726 without.

**Where we differ from experts** (share of the music): inversion or bass 0.072 against 0.049, related chord 0.059 against 0.041; key 0.056 against 0.075 the other way. With the draft we write fewer chord changes than the expert in 90% of pieces. Of the expert's 95 cadences (21 DCML pieces) we mark 0.57 to 0.67 in the same place with the same type, and 0.39 to 0.43 of our cadence marks have no expert cadence; no pair of experts both mark cadences, so their agreement is unknown.

**Plain model against pipeline** (3 pieces): plain Opus matches the pipeline on key (0.96-0.97) and root (0.86-0.88). The pipeline's gain is bass and inversion (missed on 0.113 of the music by plain Opus, 0.06-0.08 by the pipeline).

**Counted by chord instead of by time** (owner's question: each chord counts once, and counts as agreed when the other reading agrees over more than half of it). Recall is the share of the expert's chords we agree with; precision is the share of ours the expert agrees with.

| Recall / precision | Experts | Opus with draft | Opus without draft | Draft |
|---|---|---|---|---|
| Same root | 0.91 / 0.91 | 0.81 / 0.87 | 0.85 / 0.87 | 0.74 / 0.67 |
| Key, chord and bass | 0.70 / 0.70 | 0.60 / 0.65 | 0.61 / 0.64 | 0.44 / 0.40 |

On 3 pieces, recall at the root: plain Opus 0.78, plain Sonnet 0.50. This is the widest gap to the experts of any measure tried (0.09 at the root with the draft), though still under the 0.10 line set beforehand. It comes from chord changes we do not write: per 100 of the expert's changes we share 73, miss 27 and add 5 with the draft (81, 19 and 7 without; two experts 89, 11 and 11). The median piece has 17% fewer changes than its expert. Half of the chords we skip are shorter than a beat, and 30% are unrelated to the chord we hold over them (15% between experts). Of the expert's chords shorter than a beat we agree on 0.47 at chord and bass, against 0.71 between experts; on chords longer than a beat the review without the draft matches the experts. By time, the stretches after a missed change cost 0.113 of the music at *full*, a third of all we lose, against 0.053 between experts.

**From the literature.** Published systems report the same strict measure, at 0.43 to 0.58 on their own test sets (the draft model's paper 0.52-0.53). No published figure was found for agreement between experts on Roman numerals of classical scores, and no multi-reference scoring.

**Limits.** Our passages are chosen ones while expert pairs cover whole movements; our Beethoven, Chopin and Mozart references are DCML while those pairs are mostly DCML against TAOM. Style figures on our side rest on 1 to 6 pieces, the multi-expert comparison on 6. Entry 66's "0.47 of chord misses are the right chord placed elsewhere" was not reproduced (0.08 to 0.16 by two definitions). 147 pieces have two independent experts and a usable score, 131 of them outside our sets; they have not been reviewed.

### 120. Cadences and the Bach preludes, read against the notes (2026-11-06)

**Question.** Entry 119 left two weak spots: we mark 0.57 to 0.67 of the expert's cadences, and the three Well-Tempered Clavier preludes score 0.49 *full*. Are these our errors?

**Method.** Saved runs only. The 95 expert cadences inside the scored bars of the 21 DCML pieces, and the three preludes (94 bars), with 24 cadence cases and 15 prelude places read against the notes by an Opus agent. Copies of the scripts and the side-by-side listings are in `out/scoring-research-2026-11-06/`.

**Cadences.**

| Of the expert's 95 cadences | Same place and type | Same place, other type | Within the bar | Missed |
|---|---|---|---|---|
| Opus with the draft | 54 | 12 | 6 | 23 |
| Opus without the draft | 64 | 9 | 4 | 18 |
| Draft alone | 28 | 16 | 3 | 48 |

- In all 41 cases the review with the draft missed or mistyped, its chord at the arrival has the expert's root and bass. The difference is in what is called a cadence.
- Of 12 misses read: 7 defensible (an arrival on an inverted dominant or a leading-tone chord, the expert's cadence in the key of V against our half cadence in the home key, an evaded cadence, which we cannot write), 1 debatable, 4 ours wrong (a cadence the draft had and the review dropped, an IAC written as PAC with the third on top, two missed closes).
- Of our 42 marks with no expert cadence, 33 sit on a V-I or an arrival on V that the expert left unmarked. Of 12 read: 8 right with the expert's mark missing, 2 defensible, 2 wrong (both a cadence on a tonicized ii in Chopin).
- Five files (four Chopin mazurkas, Dvořák Op. 8 No. 10) carry a cadence label on fewer than half of their marked phrase endings. On the other 16 pieces the share of our marks with no expert cadence is 0.30, not 0.39.
- DCML also writes evaded and plagal cadences (9 of 241 in these files, 3 of the 95), which our four types cannot express.

**Bach preludes.** The reference is not DCML but When in Rome's own analysis, which names a new key at each step of a sequence (seven keys in 48 bars of Prelude 3) where we keep the home key and write applied chords. Share of the music lost, three preludes against the other 27 pieces: related chord 0.125 against 0.054, cadential 6/4 or seventh 0.102 against 0.031, other key 0.100 against 0.053, inversion 0.094 against 0.071, different chord 0.039 against 0.071. Our root agrees on 0.78 to 0.90. Of 15 places read: 8 naming or inversion differences, 3 where the expert's figure is read by the scorer as a chord the expert did not mean (`ib3`, `i43`, `iv6b5`), 4 ours wrong (chords skipped in a sequence, a bass ignored). Preludes 12 and 22 change harmony about every beat (3.8 expert labels per bar). No second human analysis of any of these preludes exists in the data, so how far experts agree here is unknown.

**Limits.** 21 pieces for cadences, 3 for the preludes; one reader's judgement of 39 places. No pair of experts both mark cadences.

**What it means.** A cadence score should count the expert's cadences we find, on pieces whose marking is complete, and should not count our extra marks as errors. The preludes' low *full* is mostly a naming habit of one reference; the real errors there are the same skipped chords as entry 119.

### 121. End-to-end runs through the ChatGPT-side tools, and two rejected-answer fixes (2026-11-06)

**Why.** The evaluation hands the model the annotation spec as text; ChatGPT gets the method text plus the tools' own schemas. A defect seen in one may not exist in the other. A small runner (session scratch, not committed) starts the server from a checkout, stores a score, and lets a real model drive `draft_analysis` and `render_analysis` over MCP, with the User-Agent of a ChatGPT call, recording every call and rejection. Claude models run through `claude -p`, the ChatGPT model through `codex exec`.

**Eight passages whose evaluation answer had been rejected for `region.start.staff`:**

| Model, old text | First drawing call rejected | Cause | `staff` inside start or end |
|---|---|---|---|
| Sonnet | 0 of 8 | | 0 of 4 regions with staff |
| Opus, medium | 0 of 8 | | 0 of 7 |
| gpt-6.1-sol (Codex default effort) | 7 of 8 | callout written with `label: "1"` instead of `number` | 0 of 9 |

So the `staff` rejections of entry 118 belong to the text-prompt path (the evaluation and the Claude skill), not to ChatGPT. The ChatGPT model's rejections had another cause: `ANNOTATION_FORMAT` showed `label` on every example and no callout. With a callout example added (`4227d54`), the same eight passages: 0 of 8 rejected. Each rejection had cost one wasted drawing call of roughly 10 to 20 s and a second full list of marks. These rejections never reach the server log, because the schema rejects the call before the tool runs.

**Also seen.** Opus called `draft_analysis` two or three times in 6 of 8 passages, on purpose: after the passage it asked for the 6 to 10 bars before and after it. Each extra call returned about 13,000 characters, mostly the same instructions again. With the draft parked (branch `draft-switch`), each such call also counts against the daily draft limit, since no draft file marks the score as seen. Sonnet drew pages from the no-draft reply with no rejection; on its first run it told the user the draft "returned no draft", fixed by the guide wording.

**Limits.** One run per model and passage; `codex exec`, not ChatGPT itself, whose system prompt and app differ. Costs: Sonnet about US$1.55 per eight passages, Opus US$4.14; the ChatGPT model ran on the ChatGPT plan.

### 122. Scored as one more analyst on 36 pieces that two experts analysed (2026-11-06)

**Question.** Entry 119 compared our 0.67 on held-out pieces with the experts' 0.71 on other pieces. How do we score when we and the experts are measured on the same pieces and bars?

**Method (`eval/ladder.py`, set `multi`).** 36 pieces with two independent expert analyses, outside every earlier set, 9 each of Bach chorales (TAOM against BCMH), Mozart sonata movements and Chopin mazurkas (DCML against TAOM) and Beethoven sonata movements (BPS-FH, DCML, TAOM), chosen by a rule on the sorted names written down before any review (`eval/multi-expert-set.txt`). Passages as on 2026-10-24 (61 passages, 1,327 bars; chorales whole). Opus at medium effort, without the draft, note table, the method text with the fixes of entry 121. Each expert is scored against the other and our reading against each expert on the same bars. Cost about US$36 of subscription usage; one run per piece.

| Bar-weighted | Experts against each other: root / function / full | Ours against an expert | Ours minus experts, full (95% interval over pieces) |
|---|---|---|---|
| Bach chorales (9, 127 bars) | 0.99 / 0.96 / 0.87 | 0.98 / 0.94 / 0.81 | −0.064 (−0.112 to −0.013) |
| Mozart (9, 405) | 0.94 / 0.86 / 0.81 | 0.90 / 0.82 / 0.76 | −0.054 (−0.122 to +0.005) |
| Beethoven (9, 409) | 0.83 / 0.74 / 0.61 | 0.86 / 0.79 / 0.69 | +0.076 (+0.010 to +0.137) |
| Chopin mazurkas (9, 386) | 0.95 / 0.83 / 0.63 | 0.95 / 0.87 / 0.74 | +0.108 (+0.070 to +0.142) |
| All 36 (1,327) | 0.91 / 0.82 / 0.70 | 0.91 / 0.83 / 0.74 | +0.032 (−0.010 to +0.072) |

By chord (recall / precision), all 36: experts 0.91 / 0.81 / 0.70 at each level (symmetric); ours root 0.885 / 0.886, function 0.794 / 0.816, full 0.694 / 0.720. Chord changes per 100 of the expert's, shared / missed / extra: experts 86 / 14 / 14, ours 83 / 17 / 7, draft 78 / 22 / 20. Fit to the notes: experts 0.898, ours 0.900. Cadences, on the 18 pieces whose DCML file marks them fully: 124 expert cadences, 63% marked by us in the same place with the same type, 73% same place any type; 36% of our 141 marks have no expert cadence nearby (counted, not treated as errors). The draft alone: 0.84 / 0.74 / 0.59 by time.

**Caveats.** Where the two experts disagree, matching either earns us half credit while the pair earns none, so "above the experts" on Beethoven and the mazurkas is partly built into the measure. The chorale pair may not be independent (entry 66). These analyses are public, so the chat model may have seen them. Passages, not whole movements. 15 of 61 first replies were rejected, all for an `alternative` label with the wrong number of chords; none for `staff`.

**The ladder, by run** (`eval.ladder --set heldout`): `opus-medium-2026-10-24` root recall 0.814, full 0.597 by chord, changes 73 / 27 / 5, fit 0.881; `opus-medium-alone-table-30` 0.854, 0.612, 81 / 19 / 7, 0.901. Expert reference from the 151 pairs, cached in `out/eval/ladder-experts.json`.

**Run-to-run spread of the new measures.** From the 14 later pieces of the two with-draft runs of entry 64 (same passages, four extra rules in the second): per-piece standard deviation of the change about 0.04 for recall and precision at root and full, 8 missed changes per 100, 3 extra per 100. The mean change over 6 pieces moves by about ±0.03 at full between two runs of the same setup.

**The reworded method text** (branch `method-chord-changes`, commit `9cf0224`: "label every change" and "a short sonority is a chord of its own when the bass moves too") on 6 held-out pieces chosen by rule (the three-piece set plus every tenth piece by name), Opus medium, no draft, against the saved no-draft run on the same 11 passages: full by time 0.597 → 0.637, function 0.694 → 0.731, recall at full 0.580 → 0.628, precision at full 0.597 → 0.626; changes 82.6 / 17.4 / 14.2 → 84.2 / 15.8 / 16.6; fit 0.871 → 0.878. The mean per-piece changes exceed the 14-piece spread and sit just past the 24-piece one; missed and extra changes are within noise. Of the 24 chords added, about 4 in 10 line up with a change the expert also wrote. Cost US$6.32.

**What it means.** Measured on the same pieces, our analysis agrees with an expert about as often as a second expert does: 0.74 against 0.70 by time, 0.69 against 0.70 by chord. We are below the experts on the music where they agree most (chorales, Mozart) and above them where they disagree most. The reworded method text is a probable small gain and needs one more test on other pieces, and real pages drawn both ways, before it is adopted.

### 123. A mark the score cannot take is left out the same way everywhere (2026-11-06)

**Problem.** Entry 122's 15 rejected first replies (of 61), all for an `alternative` whose label has a different number of chords than the bars hold, were three behaviours, not one. The server already drew the page without the bad mark and listed it, but under a note that said "positions". The Claude skill script refused the whole page until every mark was fixed. The evaluation rejected the whole reply and asked the model again, which is where the 15 came from. A second defect in `check()`: an `alternative` together with any harmony in a bar the score does not have raised a bare position error from the chord count, refusing the whole page on the server and in the skill (0 cases in the saved corpus).

**Fix (branch `leave-out-marks`, `3c7b385`, `7a5c8b3`).** One function, `engine/annotate.py::leave_out_rejected`, runs the drawing, leaves out the marks the error names, numbered against the caller's list, and tries again, two rounds at most, as the server did before. The server, the skill script and `eval/review.py::problems_in` all use it. The server note now gives the reason on each line; its `left_out` log field counts marks, not rounds. The skill draws, warns on stderr and exits 0 (reaches Claude users with the next plugin release). The evaluation keeps the model's own dicts for the marks it keeps (pydantic's re-dump would have changed 51 of 115 saved passages by filling in defaults), records `left_out`, and retries only for a missing or malformed list; `attempts` is therefore not comparable with earlier runs. The chord count now runs after the position checks and over harmonies that were not rejected.

**Effect on the saved corpus (first-reply problems).** `opus-medium-multi-alone-table`: 15 of 15 retries removed. `opus-medium-alone-table-30`: 5 of 13 removed; the other 8 are `region.start.staff` schema errors, which the server also refuses whole, so their retries stay. 20 of 28 retries removed in all. Tests: full suite 1266 passed, 9 skipped, 2 xfailed before the last evaluation edit; the touched files (295) rerun after it, and 90 again after the merge here; `diff_check --base main` unchanged on render, export and typed. A page with a bad alternative and a measure-99 harmony added was looked at full size: everything else drawn, both left out.

### 124. Reader sma.7 released, the draft parked, plugin 1.8.0 (2026-11-07)

**Released.** GitHub release `5.11.0-sma.7` of the reader fork (jar built from `378e4fd6d`, the head of `sma-pitch`, 63 commits over Audiveris 5.11.0). `main` moved from `517a891` to `3596be6`: entries 114 to 123 (reader sma.7 and the warning for notes that do not line up, the `staff` and callout fixes to the annotation spec and format, marks the score cannot take left out everywhere, the test-suite grouping), plus the `draft-switch` branch and the deploy change below. CI green on `3596be6`. Staging revision `sheet-music-analysis-staging-00079-h4f`, production revision `sheet-music-analysis-00048-9ss`, plugin 1.8.0 on `main` (the Claude skill now draws with a warning instead of refusing a page with one bad mark; `dist/` names reader sma.7).

**The draft is parked.** Entries 118, 119 and 122 found the draft model adds no accuracy for any reviewer, makes the ChatGPT model worse, and misses more chord changes (27 against 19 per 100). `server/deploy.sh` now deploys with `SEND_DRAFT=off` unless `SEND_DRAFT=on` is given; the server then sends the method, the guides and the note table without a draft section and tells the model not to mention a draft. A `scores/{code}.seen` marker keeps the daily draft count at one per score, as before, however many calls ask about it (models call `draft_analysis` two or three times per analysis, entry 121). No instance setting changed; the model is still in the image, and whether its worker still starts at boot was not checked. Owner decision 2026-11-06.

**Checks.** Full suite on the merged branch with the sma.7 reader set: 1314 passed, 4 skipped (no ring codes), 2 expected failures, 6 minutes. Three tools called directly on staging and then on production (MCP client, bearer token on staging): `draft_analysis` on Chopin Op. 28 No. 20, 1 s, 12,287 characters, no draft section; `render_analysis` with an `alternative` whose label has three chords over two harmonies drew the page and listed the mark under the new note; `read_pdf` on the Chopin Op. 28 No. 4 test PDF, 62 s on staging and 42 s on production, 26 bars, bar 18 shaded. Startup lines of both revisions clean apart from the known library deprecation warnings. NOT RUN: ChatGPT itself, and the plugin in the Claude app.

### 125. Sub-beat table rows and the reworded method text, on 12 more pieces (2026-11-06)

**Question.** Entry 122's reworded method text looked like a small gain on 6 pieces. Two further ideas for the missed chord changes cost no model change: a table row at each point within a beat where the lowest note changes pitch class (branch `table-changes`, `477ec66`), and a header line saying how often the bass changes per bar. Tested in three arms on 12 held-out pieces chosen by rule (every second held-out piece by name, the 6 already used left out; 21 passages, 449 bars), Opus medium, no draft, one run per arm, against the saved no-draft run on the same passages. US$31.61.

| Arm | Missed / extra changes per 100 | Recall / precision, full, by chord | Full by time | Function by time |
|---|---|---|---|---|
| Baseline `opus-medium-alone-table-30` | 19.7 / 4.0 | 0.604 / 0.643 | 0.703 | 0.825 |
| A, table rows only | 19.6 / 3.4 | 0.634 / 0.679 | 0.727 | 0.826 |
| B, reworded text only | 17.6 / 5.2 | 0.586 / 0.624 | 0.678 | 0.815 |
| C, both | 15.2 / 6.0 | 0.662 / 0.665 | 0.748 | 0.845 |

Mean per-piece change against the baseline (noise reference from entry 122: about ±6 missed per 100 and ±0.03 at full between two runs of one setup): A missed −0.4, full by time +0.013; B missed −1.8, full −0.020; C missed −3.6, full +0.032, recall at full +0.037. Extra changes rise in C (+3.0 per 100), nearly all from one song, *Der Atlas* (22.6 to 61.3). The Grieg Op. 12 No. 3 gain in A and C (0.68 to 0.91) is a key reading, not added chords: the baseline hears bars 9 to 12 as a modulation to B, C stays in E. Two pages drawn both ways (Bach chorale BWV 38.6, Grieg Op. 12 No. 3) in `out/eval/table-test-2026-11-06/`: not crowded; C adds one short chord to the chorale.

**What it means.** The rewording's first result was noise: +0.04 on 6 pieces, −0.02 on these 12. The table rows alone change nothing. Together they are the one effect at the edge of noise, from one run. Neither is adopted; C would need one more run on other pieces. The sub-beat rule adds about two rows a beat on figuration pieces and made Beethoven Op. 2 No. 1 iii miss more changes in A (37.7 to 54.1 per 100).

### 126. A second and third human analysis of the F minor prelude (2026-11-07)

**Question.** Entry 120 could not say how far experts agree on the Bach preludes, since the data holds one analysis (Gotham) of each. Two older analyses were found: Riemann, *Analysis of J. S. Bach's Wohltemperirtes Clavier* (1890, English translation), and Keller, *The Well-Tempered Clavier by Johann Sebastian Bach* (1965, translation 1976), both public-domain scans the owner downloaded by hand to `out/riemann/`. The Read tool could not open the scans (JBIG2 images, no PDF renderer on the machine); the reader's own bundled PDF library rendered the pages.

**Riemann** gives a one-staff reduction of the whole prelude with a chord symbol under every beat, 73 chords over all 22 bars, in his Klang notation (°c is F minor, c7 is C major with seventh, fVII is the half-diminished seventh on G). He names no keys or inversions chord by chord; inversions were taken from the score's bass and keys placed by us (they match Gotham's at 0.99). Transcription with page numbers and every symbol's reading in `out/riemann/prelude12-riemann.md`; RomanText beside it. **Keller** names one chord in the prelude (A♭ major at bar 9) and nothing else; recorded, not used.

| Bars 1 to 22, by time: root / function / full | |
|---|---|
| Gotham against Riemann (two humans) | 0.65 / 0.48 / 0.32 |
| Gotham against ours (`opus-medium-alone-table-30`) | 0.81 / 0.66 / 0.46 |
| Riemann against ours | 0.67 / 0.57 / 0.39 |

By chord, Gotham against Riemann at full: recall 0.31, precision 0.27. The disagreement is systematic: where the bass omits the root, Riemann writes a rooted dominant (V7, V7/V) and Gotham a leading-tone chord (viio6/5 and the like); subdominant chords (iiø7 against iv6 and ii6); the order of i6/4 and V over the pedal at bar 16; and Riemann ends on minor where the score ends on F major. Our reading sides mostly with Gotham, and with Riemann at bars 4, 5, 6 and 8 (V6/5 against viio7).

**What it means.** On this prelude we agree with the reference more than the second human does. One piece and an 1890 analyst from another tradition, so it is a data point, not a ceiling for the preludes; but it says the prelude's low score is not a shortfall against a consensus, because there is none on this music.

### 127. Two real PDFs refused for their page size, and what we keep to find out why (2026-11-07, not released)

**What users hit.** Since reader sma.7 went live, three ChatGPT users sent PDFs. One read (72 bars) and reached three marked pages. Two got "No music could be read" and did not retry: 2 pages at 1600×2133 at 12:01 UTC and 4 pages at about 7000×10000 at 14:59 UTC. The PDFs were not stored, so nobody can inspect them, and the log did not record why the reader refused them.

**Causes.** The reader draws each page at 300 dpi of its page box. It refuses anything over 20 million pixels at its load step, and anything with staff lines under 11 pixels apart at its scale step. Enlarging our own Chopin Op. 28 No. 4 PDF to 7192×10172 gave the second user's log pattern; reducing a page of a real Joseffy scan to about 1000 pixels wide on a 3.3-inch page gave the first user's. The same image on an A4 page read in both cases. The first user's file is matched only by its log pattern, not proven.

**The first design was wrong, and the corpus check found it.** Scaling by rule any page over 18 million pixels or under A5 would have resized 50 of 648 PDFs, including `mozart-41` (a long, thin page that reads today, which would have got tiny staves) and real small-page scans that already read. The change now touches only what would fail anyway:
- a page over the reader's limit is shrunk to about the area of A4 before reading (26 of the 648 PDFs have such a page; the size test below chose A4);
- when no setting gives a reading and the reader reports staff lines too close, the PDF is enlarged to about 20 pixels between lines and read once more, within the same overall time limit.

| Input | Before | After |
|---|---|---|
| Chopin Op. 28 No. 4 on an oversize page | refused | 26 bars, 599 notes, 1 shaded: same as the normal PDF |
| Joseffy scan, about 1000 pixels wide | refused | 32 bars, 436 notes, 22 shaded |
| The same scan at full size (5244×6888) | refused | 32 bars, 416 notes, 13 shaded |

Looked at the last page of each reading against the scan; the owner then read them against the print. The low-resolution reading is unreliable: bar 28 has half notes that are not in the print and a lost rest, bar 30 has a C for a D, and bar 27 is wrong with no shading. A reading made this way now says that many mistakes are likely, including in bars with no shading (owner's choice over refusing the file).

**Page size against accuracy.** Five real scans, 253 bars, each page scaled to a target size; the as-is run reproduced the known 141. Exact bars: 4 million pixels 105, 6 million 134, 8.7 million (A4) 139, 12 million 140, 15 million 140, 17.5 million 138, 19.4 million 140, as is 141. Single pieces move by several bars with no trend, so above 6 million pixels the differences are noise, and size is not a route to accuracy on these scans. One Joseffy page looked much better at 19.4 million than at A4, but that one page has no reference and the five-piece result does not support it. Wrong bars with no shading stay at 50-62% at every size.

**Why triplets and unshaded bars were missed on that page (Opus review; not fixed).** The reader finds the printed 3 in bar 27 and links it, then deletes it at a score of 0.168 against a floor of 0.5; keeping it does not repair the bar and costs right bars elsewhere. A full left hand hides a short right hand from the short-bar check, which also turns off when no time signature is read (68 of 291 readings). Neither justified a patch.

**Other readers on the same five scans.** After that page the owner asked whether the reader should be replaced, so two others were run locally through the same scorer, which reproduced our 141 piece by piece. Exact bars of 253: ours 141 (55.7%, pitch 89.2, timing 80.1); Sheet Music Transformer `smt-fp-grandstaff` 34 (13.4%, pitch 82.0, timing 54.0, 74 s a page on 4 CPU threads, 1.8 GB); oemer 11 (4.3%, pitch 60.9, timing 33.4, about 5 minutes a page, 7.8 GB). The 34 needed a lenient hand-written converter with up to 296 repairs a page; with the standard converter it scores 0. No reader tested beats ours, so nothing changes. NOT RUN: LEGATO and `smt-fp-polish-scores`, whose weights need the owner's Hugging Face login and acceptance of terms. Evidence is in `~/omr-reader-test-2026-11-07`, outside the repo.

**Logging and keeping files.** `read_pdf_work` now records page sizes in points, embedded image sizes, whether the file is a scan, and the reader's reason (page too large, staff lines too close or too far apart, with the spacing it measured). A PDF that fails to read is kept under `failed/` for 7 days; the privacy page says so (owner approved 2026-11-07). The policy must be live before or with the deploy that starts keeping files.

**Checks.** Full suite with the sma.7 reader set: 1335 passed, 4 skipped (no ring codes), 2 expected failures. A second-model review found the retry's separate time budget, server errors on malformed page boxes and a storage failure replacing the user's message; all three fixed and tested. `tools/diff_check.py` has no area covering reading, so the check across PDFs is the page-size test and the count above. NOT RUN: the change in ChatGPT itself, staging, a real phone photo.

**Known limits.** A page whose own drawing commands are unbalanced can scale wrongly. A PDF where only some pages are too small gets no retry; those pages are reported as skipped. Whether the reader honours `UserUnit` was not checked.

### 128. Claude without scripts: the score picked in a card (2026-11-07, spike, not released)

**Problem.** Anthropic's plugin directory refused plugin versions after 1.7.4 for bundling files it does not accept, and the Claude plugin runs the engine as Python scripts in Claude's sandbox. The server would have to read and draw the score for Claude as it does for ChatGPT, but Claude still has no way to pass a chat attachment to a connector: no `openai/fileParams` equivalent, MCP's file-input proposals (SEP-2356, SEP-2631) closed in favour of an experimental extension that no host implements, and Claude's sandbox cannot reach our server.

**What the spike does (branch `claude-rebuild-spike`).** The file button of entry 3 comes back as the way a score is given in Claude, not as a second pick of an attached file: `choose_score` shows a card, the card sends the picked MusicXML or PDF to `/upload` and puts its id in the model's context, then posts "I've picked my score" so Claude continues. Claude is offered `read_picked_pdf`, `draft_analysis`, `correct_bars` and `render_analysis`; every card gets Claude's `ui.domain` (`{hash}.claudemcpcontent.com`), which Claude requires; a Claude PDF call waits at most 100 s because Claude ends tool calls at 240 s. ChatGPT's tool list is unchanged.

**Result, locally only.** In the MCP Apps reference host, presented as Claude: the real nocturne `.mxl` uploaded from the card (20,669 bytes, the file's size), the context update and message reached the host, `draft_analysis` on its id drafted in 7 s, and the analysis card showed the drawn page. A real PDF uploaded and returned a `pdf_id`; reading it was NOT RUN (no reader on this PC). A whole-nocturne `render_analysis` result is 165,653 characters, over claude.ai's limit of about 150,000, past which Claude keeps the result as a file and the card does not show; bars 1-4 is 57,735. Not tried in claude.ai. The owner rejected picking in a card in October; the flow is changed so the score is picked once, and the decision is the owner's.

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
.venv/bin/python -m eval.run --set heldout                         # draft on pieces the draft model never saw (challenge 58)
.venv/bin/python -m eval.review --set heldout --only ID --passages 2 --tag NAME   # review two passages per held-out piece
.venv/bin/python -m eval.ceiling                                   # expert against expert, 151 pairs by style (challenges 14, 59, 62, 63)
.venv/bin/python -m eval.review --set heldout --only ID --passages 2 --no-draft --source musicxml --tag NAME   # Claude alone (challenge 60)
.venv/bin/python -m eval.plain --only ID [--only ID]                 # plain Sonnet and Opus chats, two runs each (challenge 61)
.venv/bin/python -m eval.survey                                    # draft over 300 When in Rome pieces (challenge 15)
.venv/bin/python -m eval.bass_check                                # the rejected bass rule (challenge 11)
.venv/bin/python -m eval.review --tag NAME --selfcheck --start-from opus-medium   # the self-check alone (challenge 16)
.venv/bin/python -m eval.key_readings                              # second readings of key, by rule (challenge 72)
.venv/bin/python -m eval.review --set heldout --only ID --passages 2 --selfcheck --start-from opus-medium-2026-10-24 --tag selfcheck-b   # the reworded check (challenge 74)
.venv/bin/python -m eval.pdf_compare --kind real                 # plain chats and our setup from the same PDF (entry 85)
.venv/bin/python tools/robustness.py                               # 31-score robustness run
```
