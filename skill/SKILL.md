---
name: sheet-music-analysis
description: Analyse the harmony of sheet music and draw the analysis on the engraved score. Use when the user attaches or mentions a MusicXML score (.mxl, .musicxml) and asks for a harmonic analysis, Roman numerals, chord functions, cadences, phrase structure, non-chord tones, voice leading, key areas or modulations, or asks what is happening in a passage of a piece. Produces an annotated score as PNG and PDF plus a short written commentary. For music students and composers; classical tonal repertoire.
---

# Sheet music analysis

You analyse a score the way a composer or theory teacher would, then have it drawn on the engraved page. You never draw: you write an annotation list that says what to mark and where in the music, and a script engraves it.

The user's attached score is a file in your sandbox; the scripts read it from there. Do not ask the user to upload it again, and do not use the connector's `choose_score`, `draft_analysis` or `render_analysis` tools: those exist for hosts that cannot run this skill.

The scripts are in this skill's `scripts/` folder, next to this file (`${CLAUDE_SKILL_DIR}/scripts/`); run them from the skill's folder or by their full path.

## Steps

1. **Set up once per conversation.**

   ```bash
   pip install verovio resvg-py img2pdf pillow fonttools pydantic
   ```

2. **Read the notes.** Run the table script on the user's file. If they named a passage, pass it; otherwise ask which bars they want, or take the first 8 to 16.

   ```bash
   python3 scripts/notes_table.py SCORE --measures 1-8
   ```

   Each row is one beat: the lowest note, the pitch classes sounding, and every note as `pitch@beat`. Use these exact measure numbers, beats and pitches in your annotations.

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

   If it lists annotations that do not match the score, fix exactly those and run again. Look at the PNG yourself before showing it: labels should sit where you meant them.

7. **Reply** with the annotated page shown to the user (the PNG), the PDF offered as a download, and the commentary.

## Method

Work in this order. Each step narrows the next.

1. **Key and key areas.** Start from the key signature, the first and last bass notes and the cadences. Decide the local key of each stretch. A new key needs a cadence or a sustained stay; a chord or two borrowed from another key is a tonicization (`V7/ii`), not a modulation.
2. **Harmonic rhythm.** Decide how often the harmony really changes, usually once or twice a bar, sometimes every beat. Follow the bass. One row of the table is not one chord.
3. **Function before labels.** For each harmony decide what it does: tonic (T), predominant (PD) or dominant (D). Then choose the numeral that says so.
4. **Filter non-chord tones.** This is where a naive reading fails. Melody notes and figuration that do not belong to the harmony are passing (P), neighbor (N), suspension (S), appoggiatura (APP) or anticipation (ANT) notes. A chord that appears for a fraction of a beat is usually one of these in disguise. A harmony over a held bass note keeps its own root; mention the pedal.
5. **Inversions from the true bass.** In broken-chord textures the bass is the lowest note of the pattern, usually on the beat, not whatever sounds lowest a moment later.
6. **Phrases and cadences.** Mark where each phrase starts and ends and how it ends: PAC, IAC, HC or deceptive (DC). Name repeated or varied phrases (a, a′, b).
7. **Voice leading.** Mark one or two resolutions that matter: a chordal seventh falling, a leading tone rising, a suspension resolving.
8. **What is unusual.** Find the two to four moments a listener would notice: a deceptive turn, mixture, a Neapolitan or augmented sixth, a delayed resolution, a chromatic bass. For each, say what was expected and what the composer did instead. These get numbered callouts.

Check yourself: every numeral's pitches must be in the table for that beat (allowing for the non-chord tones you named). If you are unsure between two readings, choose the simpler one and say so in the commentary.

## Annotations to include

- `harmony` at each real change of chord, with `function` (T, PD, D) wherever it is clear, and `key` on the first chord and at each change of key.
- `cadence` at each cadence's arrival chord.
- `phrase` brackets for each phrase.
- `nct` for the non-chord tones worth showing: a handful, not every one.
- `voice_leading` for one or two resolutions.
- `callout` numbers 1, 2, 3… at the unusual moments, matching your commentary.

Keep the page readable. If a passage would be crowded, render separate views with `--view harmony`, `--view voice_leading` and `--view form` instead of one page with everything.

## Commentary

Write it after the page, as numbered paragraphs matching the callouts, then one or two sentences on the passage as a whole.

- **For a student** (the default): explain each label the first time it appears, show the reasoning ("the bass rises by step, so this is a passing chord"), and keep to what is on the page.
- **For a composer** (when the user says they write music, or asks how or why it works): skip the definitions, focus on what is unusual, compare with the expected version, and name the technique so it can be reused.

Do not claim more certainty than you have. Automatic and human analyses both differ on details; where a second reading is reasonable, name it.

## Limits

- Input is MusicXML. For a PDF or a photo of a score, say that MusicXML is needed and that MuseScore, Dorico, Sibelius and Finale can export it.
- The engraving is a fresh rendering of the user's file, not a picture of their original edition.
