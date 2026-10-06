# Directory listings (draft for the owner's approval)

Text for the Claude and ChatGPT directory forms. Keep it consistent with the website, readable by someone with very basic music knowledge, and honest about the weak spots (borrowed chords sometimes read as a key change; Debussy-style music gets looser descriptions).

## Shared

| Field | Value |
|---|---|
| Name | Sheet Music Analysis |
| Website | https://sheetmusicanalysis.com |
| Documentation | https://sheetmusicanalysis.com/docs.html |
| Privacy policy | https://sheetmusicanalysis.com/privacy.html |
| Terms | https://sheetmusicanalysis.com/terms.html |
| Support | support@sheetmusicanalysis.com |
| Icon / logo | `site/icons/logo-1024.png` |
| MCP server | https://mcp.sheetmusicanalysis.com/mcp (no sign-in) |

**One-liner** (Claude, up to 200 characters; 158):

> Harmonic analysis drawn on the score. Attach a MusicXML file and get the chords, cadences and phrases marked on the engraved page, with a short explanation.

**Description** (Claude up to 2,000 characters, ChatGPT up to 4,000; about 1,300):

> Sheet Music Analysis marks up a piece of music the way a theory teacher would pencil it in. Attach a score as a MusicXML file (.mxl or .musicxml, which MuseScore, Sibelius, Finale and Dorico can all export) and ask what is happening in the music.
>
> You get the engraved score back, as an image and a PDF, with:
> - every chord labelled with a Roman numeral, and coloured bands showing its job: home (tonic), moving away (predominant) or pulling back home (dominant);
> - cadences, the musical commas and full stops, boxed, and brackets showing where each phrase begins and ends;
> - melody notes that don't belong to the chord circled and named;
> - arrows where the way one note moves to the next matters;
> - numbered circles that match a short written explanation in the chat.
>
> A computer model trained on hundreds of expert analyses drafts the analysis; the chat model then checks it against the actual notes and corrects it. On 12 well-known pieces checked beat by beat against experts' analyses, 71% of beats matched after the review (experts match each other on about 78%). Treat it as a well-read study partner, not an answer key: it is least reliable where experts also disagree, such as music in a major key that briefly borrows chords from the minor, and music like Debussy's that doesn't follow the usual chord patterns.
>
> Ask for one layer at a time (harmony, voice leading or form) when a page gets busy. Each page shows up to 32 bars; longer pieces are analysed passage by passage. Free, no account, no ads.

**Categories** (Claude, one to five; pick from the portal's list): Education; whichever of Music / Arts / Creative the portal offers.

## Claude

Only the plugin is listed: the owner does not want the connector on its own in Claude, where it would need a file button. The server shows Claude only `draft_from_notes`, which the plugin's skill calls.

**Carousel screenshots**, if the plugin form asks (3–5 PNGs at least 1000 px wide, the response only, each with its prompt):
1. "Analyse the harmony of bars 1–8 of this nocturne": the full page.
2. "Just the harmony, please": the harmony view.
3. "How do the voices move in bars 5–8?": the voice-leading view.
4. "Show me the phrase structure": the form view.

## Claude: plugin form

- **Repository:** `Vedat-Ozkan/sheet-music-analysis`, path `dist/sheet-music-analysis`, branch `main`.
- **Personal data:** none collected. The plugin sends our server a list of the notes in the passage (pitches, timings, staves), not the file; the list is not stored.
- **Third-party services:** our own server at mcp.sheetmusicanalysis.com, hosted on Google Cloud, behind Cloudflare.
- **Retention:** note lists are not stored.
- **Age-appropriateness:** suitable for general audiences, including students under 18.

## ChatGPT: submission form

- **Name** (30 characters): Sheet Music Analysis (20).
- **Description:** the shared description above.
- **Test file for reviewers:** https://sheetmusicanalysis.com/samples/chopin-nocturne-op9-no2.mxl

**Should use the app** (prompt → tools → what the user sees):

1. [attach the sample] "Analyse the harmony of bars 1–8 of this." → `draft_analysis`, then `render_analysis` → the engraved bars 1–8 with numerals, coloured bands, cadences and numbered circles, plus a commentary.
2. [same chat] "Now show only the harmony." → `render_analysis` with view `harmony` → the same bars with chords and bands only.
3. [same chat] "What happens in bars 9–16?" → `draft_analysis`, then `render_analysis` → bars 9–16 annotated, with a commentary.
4. [same chat] "Show the phrase structure of bars 1–16." → `render_analysis` with view `form` → phrase brackets and cadences.
5. "I have a MusicXML score I'd like analysed." (no attachment) → `choose_score` → a file button; after a file is picked, the analysis as in 1.

**Should not use the app:**

1. "What is a Neapolitan sixth chord?" → answered from general knowledge; no tool call (no score is involved).
2. "Here's an MP3 of my piece, can you analyse it?" → no tool call; explains that the app needs a MusicXML score, not audio.
3. "Analyse the whole of this 120-bar sonata movement on one page." → `render_analysis` refuses more than 32 bars per page; the reply offers to go passage by passage instead.

- **Demo video:** a screen recording of cases 1–5 and one of the negative cases in ChatGPT, uploaded as an unlisted video.
