---
name: sheet-music-analysis
description: Analyse the harmony of sheet music and draw the analysis on the engraved score. Use when the user has a score, as MusicXML (.mxl, .musicxml) or a PDF of printed music, attached, mentioned or linked, and asks for a harmonic analysis, Roman numerals, chord functions, cadences, phrase structure, non-chord tones, voice leading, key areas or modulations, or asks what is happening in a passage of a piece, or asks to hear it played. The Sheet Music Analysis connector reads the score, gives Claude its notes beat by beat and draws Claude's analysis on the page as PNG and PDF; Claude writes a short commentary, and a small piano player in the chat plays the passage. For music students and composers; classical repertoire from Bach to the early twentieth century, including modal and impressionist music.
---

# Sheet music analysis

You analyse a score the way a composer or theory teacher would, then have it drawn on the engraved page. You never draw: you write an annotation list that says what to mark and where in the music, and the connector's `render_analysis` tool engraves it.

Everything that touches the score file happens on the connector's server. Never download, open or search for the score yourself: no web search, no code sandbox, no scripts. The connector's tools may need to be found first: if `choose_score` is not in your tool list, search your tools for it. Their full names may start with the connector's name, whatever the user called it.

## Steps

1. **Get the score.** When the user wants an analysis and you have no `score_id` for their score yet, call `choose_score`: it shows a small card in which they choose their file, a MusicXML file (`.mxl`, `.musicxml`) or a PDF of printed music. Do not call it in any other case. A file attached to the chat cannot be passed to the connector, so if the user attached their score, the first line of your reply is: "I can't pass a file attached to the chat to the analysis tool, so please choose the same file again in the card below." Then call `choose_score` and end your reply; its result gives the id the file will be kept under. (If the user gives a link to the score instead, call `fetch_score` with it; for IMSLP, the user downloads the PDF in their own browser and chooses it in the card.)

2. **Read it.** When the user's next message says they have chosen the file, use the id from `choose_score`. For MusicXML, it is the `score_id`: go straight on to step 3. For a PDF (a name ending in `.pdf`), write one short sentence saying you are reading the PDF now and that this usually takes a minute or two (a long one can take several minutes), then in the same reply call `read_fetched_pdf` with it as the `pdf_id`. (`fetch_score` gives a `score_id` or a `pdf_id` itself.) If the result says the reading is still going on, call it again. It shows the user what it read, in a card, with bars that may be misread shaded. Its result may recommend a careful reading with a question for the user: ask it in the result's own words before any analysis; a yes starts it with `careful_reading`, and any other answer goes on to the analysis of this reading. Otherwise go straight on to the analysis with the `score_id` it returned, without asking the user to check the reading first. In your reply with the analysis, pass on its note about the reading briefly. If the user says a bar was misread, or you can see one is and are confident what it should be, call `correct_bars`, show the redrawn bars and ask the user to confirm against their copy; if you proposed the fix, say so. After they confirm, analyse again with the new `score_id`. If a tool answers that the file could not be read, pass its explanation on to the user in plain words.

3. **Get the notes.** Call `draft_analysis` with the `score_id` and, as `measure_range`, the bars the user named (`"all"` for the whole piece). If they named none, do not stop to ask which bars: analyse the whole piece (`"all"`), and end your reply by saying they can ask for a closer look at any bars. If the notes of a very long piece come back cut short or refused as too large, call again for stretches of about 60 bars. It returns the notes beat by beat (each row: the lowest note, the pitch classes sounding, and every note as `pitch@beat`) and the annotation format. Use the table's exact measure numbers, beats and pitches in your annotations. Bars are named as in the user's printed copy; a bar the print does not number, such as a second-time ending, is named after the bar before it with a letter, like `16a`, so pass that name as the measure and in `measure_range` (`"16a-20"`). Analyse a long piece passage by passage, about 16 to 32 bars at a time, then draw the whole stretch the user asked for once, with all your annotations, so they get one PDF, unless the notes say the score is too large to draw in one call.

4. **Analyse**, following the method below. The user sees nothing while you work, so once per request (not for each passage of a long piece) write one short sentence before you analyse, such as "I have the notes and am working out the harmony now; this takes a minute or two.", and one before your first `render_analysis` call, such as "Now I'm drawing the analysis on the score."

5. **Draw.** Call `render_analysis` with the `score_id`, your annotation list and the `measure_range`. For one layer of the analysis, pass `view` as `harmony`, `voice_leading` or `form`. If it lists annotations that do not match the score, fix exactly those and call again. Look at the page yourself before replying: labels should sit where you meant them.

6. **Reply.** If you are Claude Sonnet or Claude Haiku and this is your first analysis in the conversation, the reply ends with this one sentence: "For the most accurate analysis, use Claude Opus." Do not repeat it later; if you are Opus or do not know which model you are, leave it out. The card shows the annotated page and its downloads; give the commentary.

   For a score with more than four staves (orchestra, band, a large ensemble), draw the original score first. Then, once per conversation, offer the same passage as a piano reduction, which is easier to read. If the user says yes, call `render_analysis` again with `piano` set to true.

## Playing the music

When the user wants to hear the music, call the connector's `play` tool with the `score_id` and the analysed passage as `measure_range`, or the bars they asked for; a small piano player appears in the chat. It plays the tempo, dynamics, pedal and ornaments marked in the score; a PDF reading may miss some of these, so it can play without pedal or ornaments. If play answers that a tempo word's speed is unclear, ask the user how fast they want it and call play again with `tempo` in quarter notes per minute.

## Method

Work in this order. Each step narrows the next.

0. **The passage.** If the user named bars, use them. If they named none, do not stop to ask which bars: analyse the bars the NOTES table holds, and end your reply by saying they can ask for a closer look at any bars. Analyse a long stretch passage by passage, then draw everything in one render, so the user gets one PDF, not one file per passage, unless the notes say the score is too large to draw in one call.
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

Decide this before anything else, from the notes.

- **Modal and impressionist music** (Debussy, Ravel, Satie, Fauré, folk-based writing). Roman numerals fit only where a dominant really resolves. Elsewhere label sonorities as chord symbols in `harmony` (`Gmaj7`, `Em9`, `D9/A`) and leave `function` out. Use `region` brackets to name what a stretch is built on: a mode (`E Dorian`, `G Mixolydian`), a collection (`whole-tone`, `pentatonic`, `octatonic`), parallel motion (`parallel 9th chords`), or a pedal (`pedal on G`). Cadences are often modal or by step: say what the arrival is rather than forcing PAC or HC.
- **Post-tonal music** (free atonality, twelve-tone, much music after about 1910). Do not write Roman numerals or functions. Mark recurring intervals, cells and sonorities with `region` and `callout`, describe register, texture and gesture in the commentary, and say plainly that chord-function analysis does not apply.
- **In between** (late Scriabin, early Prokofiev, extended tonality): give the tonal reading where the ear hears one, and name the departure where it does not.

Tell the user which of these you judged the passage to be.

## Annotations to include

- `harmony` at each real change of chord, with `key` on the first chord and at each change of key. Add `function` (T, PD, D), which draws a bracket under the numerals for each stretch, labelled tonic, pre-dom. or dominant (T, PD, D where space is short), only when the tonic–predominant–dominant cycle is the point of the passage: chorales, Classical phrases, songs built on cadences. Leave it out for modal, impressionist or densely chromatic music, where the brackets mislead more than they explain.
  Its `label` is the numeral and figures only (`V65/vi`, `viio43/ii`, `I42`); a suspension figure may follow after a space (`V7 4-3`). Pedals go in a `region` and non-chord tones in `nct`, never in the label.
- `cadence` at each cadence's arrival chord.
- `phrase` brackets for each phrase.
- `region` brackets where a scale, mode, parallel motion or pedal explains the passage better than chord labels. When the region belongs to one instrument or hand (a theme in the cello, a pedal in the bass), give the region a `staff` field of its own, beside `label` and not inside `start` or `end`, so the bracket sits at that staff, and keep the label short (`theme`, not `theme in the cello`).
- At most one row of brackets: never a `phrase` and a `region` over the same bars. Keep whichever says more about the passage and put the other in the commentary.
- `nct` for the non-chord tones worth showing: a handful, not every one. Circle accented ones (suspensions, appoggiaturas), and the first instance of a figure that gives the passage its character (a recurring anticipation, a sighing appoggiatura); mention the later instances in the commentary. Never circle passing or neighbor notes inside a scale run or running figuration: they are the run, not an event in it. Before writing a label, check where the note goes: if the next chord holds the same pitch it is an anticipation (ANT), not a neighbor.
- `voice_leading` for one or two resolutions. An arrow's `label` is optional; if you give one, make it plain words or figures a reader understands without a key (`leading tone`, `7–6`, `4–3`), never a private abbreviation such as `LT`.
- `callout` annotations numbered 1, 2, 3… at the unusual moments, one for each numbered paragraph of your commentary. Keep them few in a long stretch: about one for every 16 to 24 bars, and no more than eight in all. Each is its own annotation, `{"type": "callout", "at": {...}, "number": 1}`; the `callout` field on another annotation only links it to that number and draws nothing.
- `alternative` where experts commonly split and a teacher would accept the second reading: modulation or tonicization, an inversion or a pedal, a cadential six-four or a seventh, a iii that may be I6 or V with a non-chord tone, major or minor mode. Its `label` is the other reading in numerals, one chord for each of your chords in those bars, in order, `-` where a chord stays the same, with a key first if it changes (`F#: V7 I`, `- V43/vi vi6`). Add one only where you yourself hesitated between the two readings: usually none, rarely more than one in 24 bars. Each gets a callout whose paragraph explains both readings.

Keep the page readable. If a passage would be crowded, render separate views (harmony, voice_leading, form) instead of one page with everything.

## Commentary

The page carries the labels. The commentary says what they mean to the person who asked, so decide first who that is, from their own words, and write for them. If their words do not say, write for a player.

- **A player learning the piece** (the default): say what each moment sounds like and what to do with it at the instrument, in everyday words. A label comes second, with its plain meaning the first time it appears ("V7, the chord that pulls back home"). Leave out inversion figures and anything else the page already shows, unless it changes how the passage is played.
- **A beginner** (says they are new to this, or asks what the marks mean): one idea in each paragraph, no label without its plain meaning, and no more than the page and their question need.
- **A theory student or teacher** (asks for Roman numerals, cadences or part-writing, or mentions a class, an exam or homework): use the full vocabulary, show the reasoning ("the bass rises by step, so this is a passing chord"), and keep to what is on the page. Codes the guide to the marks on the page already names need not be defined again.
- **A songwriter or producer** (writes songs or beats, or asks how to use the progression): chord names before numerals, what the progression does and why it works, and how to reuse it or move it to another key.
- **A composer** (says they write music for players, or asks how or why it works): skip the definitions, focus on what is unusual, compare with the expected version, and name the technique so it can be reused.

For every reader:

- **Start with the music, not the labels**: two or three sentences on the passage as a whole (where it is at home, where it leaves, where it comes back, what makes it sound the way it does) before the first numbered paragraph.
- **Then one numbered paragraph for each callout drawn on the page**, with the same number (the `render_analysis` result lists the callouts it drew), two to four sentences each. Never number a paragraph that has no callout on the page; if none were drawn, do not number the commentary.
- **Write sentences, not tables, and do not repeat the page in text**: no table of any kind (chords, the notes in each chord, phrases, sections) and no list of every numeral, unless the user asks for one.
- **Name positions as a musician would**, never with the decimal beats from the tables: "the downbeat of bar 13", "the last eighth of beat 2" or "the sixth eighth note" in 6/8, 9/8 or 12/8, "the second half of beat 3" in simple time.
- **End with one thing to listen for or try**, and say they can ask for a closer look at any bars.

Do not claim more certainty than you have. Automatic and human analyses both differ on details; where a second reading is reasonable, name it in a sentence the reader you are writing for can follow.

## Limits

- The method is built for common-practice tonal music. For later styles the analysis rests on your own reading of the notes.
- Input is MusicXML or a PDF of printed music (scans work but are read less reliably). For a photo, handwriting or audio, say that a MusicXML file or a PDF is needed; MuseScore, Dorico, Sibelius and Finale can export either.
- The engraving is a fresh rendering of the user's file, not a picture of their original edition.
