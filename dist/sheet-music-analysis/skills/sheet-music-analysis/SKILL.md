---
name: sheet-music-analysis
description: Analyse the harmony of sheet music and draw the analysis on the engraved score. Use when the user attaches or mentions a score, as MusicXML (.mxl, .musicxml) or a PDF of printed music, and asks for a harmonic analysis, Roman numerals, chord functions, cadences, phrase structure, non-chord tones, voice leading, key areas or modulations, or asks what is happening in a passage of a piece, or asks to hear it played. Produces an annotated score as PNG and PDF plus a short written commentary, and with the connector a small piano player in the chat. For music students and composers; classical repertoire from Bach to the early twentieth century, including modal and impressionist music.
---

# Sheet music analysis

You analyse a score the way a composer or theory teacher would, then have it drawn on the engraved page. You never draw: you write an annotation list that says what to mark and where in the music, and a script engraves it.

The user's attached score is a file in your sandbox; the scripts read it from there. Do not ask the user to upload it again, and do not use the connector's `draft_analysis` or `render_analysis` tools: those exist for hosts that cannot run this skill.

The scripts are in this skill's `scripts/` folder, next to this file (`${CLAUDE_SKILL_DIR}/scripts/`); run them from the skill's folder or by their full path.

## Steps

1. **Set up once per conversation.**

   ```bash
   pip install verovio resvg-py cairosvg pikepdf pillow fonttools pydantic
   ```

   **A PDF of printed music** is read first:

   ```bash
   python3 scripts/read_pdf.py SCORE.pdf --out-dir OUTPUT_FOLDER --name score
   ```

   It reads the notes from the pages (about half a minute a page; the first run also downloads the reader), engraves what it read, and prints what to show the user. Show those pages and its message, then wait: the reading can contain mistakes. Only after the user says to go ahead, use the `score.musicxml` it wrote as SCORE in every step below. If the user says a bar was misread, or you can see one is and are confident what it should be, run `model_notes.py` on `score.musicxml` for those bars, correct its output (keep every voice of each bar and every staff), save it as BARS.txt and run

   ```bash
   python3 scripts/correct_score.py OUTPUT_FOLDER/score.musicxml BARS.txt --out-dir OUTPUT_FOLDER --name corrected
   ```

   Show the redrawn bars it prints and ask the user to confirm against their copy; if you proposed the fix, say so. After they confirm, use `corrected.musicxml` as SCORE.

2. **Read the notes.** Run the table script on the user's file, for the passage chosen as the method below says.

   ```bash
   python3 scripts/notes_table.py SCORE --measures 1-8
   ```

   Each row is one beat: the lowest note, the pitch classes sounding, and every note as `pitch@beat`. Use these exact measure numbers, beats and pitches in your annotations. Work on at most 32 bars at a time; for a longer piece, go passage by passage. The render script refuses a page of more than 32 bars.

3. **Get the model's draft, if the connector is there.** If a tool named `draft_from_notes` is available (the sheet-music-analysis connector), run

   ```bash
   python3 scripts/model_notes.py SCORE --measures 1-8
   ```

   and pass its output, exactly as printed, as the tool's `notes` argument. The tool returns a neural model's draft: chords with confidences, cadences, phrase ends and possible non-chord tones. The draft is a starting point, right about half the time on full chord labels; check each line against the table from step 2. If the tool is not available, skip this step and analyse from the table alone.

4. **Analyse**, following the method below.

5. **Write the annotation list** as a JSON file. The format is in `references/annotation-spec.md`; a complete example is `references/example-annotations.json`.

6. **Render.** Write the files to the folder you use to deliver files to the user.

   ```bash
   python3 scripts/render_analysis.py SCORE annotations.json --measures 1-8 --out-dir OUTPUT_FOLDER --name analysis
   ```

   For one layer of the analysis, add `--view harmony`, `--view voice_leading` or `--view form`. Add `--piano` to draw the same annotation list on a two-staff piano reduction of the passage, with instrument cues where the tune changes hands; write the list for the original score as usual. The reduction needs `pip install music21` once first. If it lists annotations that do not match the score, fix exactly those and run again. Look at the PNG yourself before showing it: labels should sit where you meant them.

7. **Reply** with the annotated page shown to the user (the PNG), the PDF offered as a download, and the commentary.

   For a score with more than four staves (orchestra, band, a large ensemble), draw the original score first. Then, once per conversation, offer the same passage as a piano reduction, which is easier to read. If the user says yes, run the render again with `--piano`.

   If you are Claude Sonnet or Claude Haiku, end your first analysis in the conversation with this one sentence, and do not repeat it later: "For the most accurate analysis, use Claude Opus." If you are Opus or do not know which model you are, leave it out.

## Playing the music

When the user wants to hear the music, call the connector's `play` tool; a small piano player appears in the chat. It plays any score you have, including the reading of a PDF, with the tempo, dynamics, pedal and ornaments marked in it; a PDF reading may miss some of these, so it can play without pedal or ornaments. If play answers that a tempo word's speed is unclear, ask the user how fast they want it and call play again with `tempo` in quarter notes per minute. Play the analysed passage: pass the `play_id` printed at the end of the draft from step 3. Only when the user asks for other bars or the whole piece, or there is no draft, run `model_notes.py` for those bars and pass its output, exactly as printed, as `notes`; this takes longer, because the whole note list goes through the chat. Without the connector, offer the MIDI file from step 6 instead.

## Method

<!-- From here to the end is also sent to ChatGPT with each draft (server/app.py); keep it free of sandbox steps. -->

Work in this order. Each step narrows the next.

0. **The passage.** If the user named bars, use them. If not, ask which bars they want, suggesting the first 8 or 16, before analysing anything. At most 32 bars per page; a longer stretch goes passage by passage.
1. **Key and key areas.** Start from the key signature, the first and last bass notes and the cadences. Decide the local key of each stretch. A new key needs a cadence or a sustained stay; a chord or two borrowed from another key is a tonicization (`V7/ii`), not a modulation.
2. **Harmonic rhythm.** Decide how often the harmony really changes, usually once or twice a bar, sometimes every beat. Follow the bass. One row of the table is not one chord. When a passage returns, label it at the same rate as the first time. A bar that opens with a single line or bare octaves (a lead-in, a scale, an arpeggio) still has a harmony from its downbeat: the chord its notes outline, or for a lead-in the chord it leads into. Do not carry the previous chord over it.
3. **Function before labels.** For each harmony decide what it does: tonic (T), predominant (PD) or dominant (D). Then choose the numeral that says so.
4. **Filter non-chord tones.** This is where a naive reading fails. Melody notes and figuration that do not belong to the harmony are passing (P), neighbor (N), suspension (S), appoggiatura (APP) or anticipation (ANT) notes. A chord that appears for a fraction of a beat is usually one of these in disguise. A harmony over a held bass note keeps its own root; mention the pedal.
5. **Inversions from the true bass.** In broken-chord textures the bass is the lowest note of the pattern, usually on the beat, not whatever sounds lowest a moment later. A bass note held by the pedal or a tie is still the bass after its printed length ends: do not change the chord because the key is released.
6. **Phrases and cadences.** Mark where each phrase starts and ends and how it ends: PAC, IAC, HC or deceptive (DC). Name repeated or varied phrases (a, a′, b).
7. **Voice leading.** Mark one or two resolutions that matter: a chordal seventh falling, a leading tone rising, a suspension resolving.
8. **What is unusual.** Find the two to four moments a listener would notice: a deceptive turn, mixture, a Neapolitan or augmented sixth, a delayed resolution, a chromatic bass. For each, say what was expected and what the composer did instead. These get numbered callouts.

Check yourself: every numeral's pitches must be in the table for that beat (allowing for the non-chord tones you named). The numeral must spell the notes as they are: a dominant seventh on the tonic is `V7/IV`, not `I7` (which has a major seventh), and a ninth must be the one printed in the score. If you are unsure between two readings, choose the simpler one and say so in the commentary.

## Music that is not common-practice tonal

Decide this before anything else, from the notes, not from the model's draft. The draft model was trained on Bach through the Romantics; on later music it still returns confident-looking Roman numerals, and they mean little.

- **Modal and impressionist music** (Debussy, Ravel, Satie, Fauré, folk-based writing). Roman numerals fit only where a dominant really resolves. Elsewhere label sonorities as chord symbols in `harmony` (`Gmaj7`, `Em9`, `D9/A`) and leave `function` out. Use `region` brackets to name what a stretch is built on: a mode (`E Dorian`, `G Mixolydian`), a collection (`whole-tone`, `pentatonic`, `octatonic`), parallel motion (`parallel 9th chords`), or a pedal (`pedal on G`). Cadences are often modal or by step: say what the arrival is rather than forcing PAC or HC.
- **Post-tonal music** (free atonality, twelve-tone, much music after about 1910). Do not write Roman numerals or functions. Mark recurring intervals, cells and sonorities with `region` and `callout`, describe register, texture and gesture in the commentary, and say plainly that chord-function analysis does not apply.
- **In between** (late Scriabin, early Prokofiev, extended tonality): give the tonal reading where the ear hears one, and name the departure where it does not.

Tell the user which of these you judged the passage to be.

## Annotations to include

- `harmony` at each real change of chord, with `key` on the first chord and at each change of key. Add `function` (T, PD, D), which colours the music behind the staves, only when the tonic–predominant–dominant cycle is the point of the passage: chorales, Classical phrases, songs built on cadences. Leave it out for modal, impressionist or densely chromatic music, where the colours mislead more than they explain.
  Its `label` is the numeral and figures only (`V65/vi`, `viio43/ii`, `I42`); a suspension figure may follow after a space (`V7 4-3`). Pedals go in a `region` and non-chord tones in `nct`, never in the label.
- `cadence` at each cadence's arrival chord.
- `phrase` brackets for each phrase.
- `region` brackets where a scale, mode, parallel motion or pedal explains the passage better than chord labels. When the region belongs to one instrument or hand (a theme in the cello, a pedal in the bass), give its `staff` so the bracket sits at that staff, and keep the label short (`theme`, not `theme in the cello`).
- At most one row of brackets: never a `phrase` and a `region` over the same bars. Keep whichever says more about the passage and put the other in the commentary.
- `nct` for the non-chord tones worth showing: a handful, not every one. Circle accented ones (suspensions, appoggiaturas), and the first instance of a figure that gives the passage its character (a recurring anticipation, a sighing appoggiatura); mention the later instances in the commentary. Never circle passing or neighbor notes inside a scale run or running figuration: they are the run, not an event in it. Before writing a label, check where the note goes: if the next chord holds the same pitch it is an anticipation (ANT), not a neighbor.
- `voice_leading` for one or two resolutions.
- `callout` numbers 1, 2, 3… at the unusual moments, matching your commentary.

Keep the page readable. If a passage would be crowded, render separate views (harmony, voice_leading, form) instead of one page with everything.

## Commentary

Write it after the page, as numbered paragraphs matching the callouts, then one or two sentences on the passage as a whole.

- **For a student** (the default): explain each label the first time it appears, show the reasoning ("the bass rises by step, so this is a passing chord"), and keep to what is on the page.
- **For a composer** (when the user says they write music, or asks how or why it works): skip the definitions, focus on what is unusual, compare with the expected version, and name the technique so it can be reused.
- **Name positions as a musician would**, never with the decimal beats from the tables: "the downbeat of bar 13", "the last eighth of beat 2" or "the sixth eighth note" in 6/8, 9/8 or 12/8, "the second half of beat 3" in simple time.

Do not claim more certainty than you have. Automatic and human analyses both differ on details; where a second reading is reasonable, name it.

## Limits

- The draft model knows common-practice tonal music. For later styles the analysis rests on your own reading of the notes.
- Input is MusicXML or a PDF of printed music (scans work but are read less reliably). For a photo, handwriting or audio, say that a MusicXML file or a PDF is needed; MuseScore, Dorico, Sibelius and Finale can export either.
- The engraving is a fresh rendering of the user's file, not a picture of their original edition.
