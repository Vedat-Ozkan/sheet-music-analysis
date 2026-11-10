# Directory listings (draft for the owner's approval)

Text for the Claude directory forms and the ChatGPT plugin ZIP. Keep it consistent with the website, readable by someone with very basic music knowledge, and honest about the weak spots (borrowed chords sometimes read as a key change; Debussy-style music gets looser descriptions).

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

**One-liner** (Claude, up to 200 characters; 165):

> Harmonic analysis drawn on the score. Attach or link a MusicXML file or a PDF and get the chords, cadences and phrases marked on the engraved page, with a short explanation.

**Description** (Claude up to 2,000 characters, ChatGPT up to 4,000; about 1,979):

> Sheet Music Analysis marks up a piece of music the way a theory teacher would pencil it in. Attach a score as a MusicXML file (.mxl or .musicxml, which MuseScore, Sibelius, Finale and Dorico can all export) or a PDF of printed music, and ask what is happening in the music. A PDF is read first, and bars that may be misread are shaded so you can check them.
>
> You get the engraved score back, as an image and a PDF, with:
> - every chord labelled with a Roman numeral, and coloured bands showing its job: home (tonic), moving away (predominant) or pulling back home (dominant);
> - cadences, the musical commas and full stops, boxed, and brackets showing where each phrase begins and ends;
> - melody notes that don't belong to the chord circled and named;
> - arrows where the way one note moves to the next matters;
> - numbered circles that match a short written explanation in the chat.
>
> The chat model analyses the music from a beat-by-beat table of its notes, our software checks how the parts move in music for two to four parts, and the analysis is drawn on the engraved score. It agrees with an expert 99% as often as experts agree with each other. We tested it chord by chord on 36 pieces, each analysed by two experts: for every chord an expert wrote, we checked whether our analysis named the same chord, in the same key, with the same note in the bass. It matched 69% of an expert's chords, and one expert matched 70% of the other's. This was measured with one chat model writing the analysis; others have not been tested the same way and may do less well. Treat it as a well-read study partner, not an answer key: it is least reliable where experts also disagree, such as music in a major key that briefly borrows chords from the minor, and music like Debussy's that doesn't follow the usual chord patterns.
>
> Ask for one layer at a time (harmony, voice leading or form) when a page gets busy. Ask for a whole piece and you get it back as one PDF. No account or sign-in needed.

**Categories** (Claude, one to five; pick from the portal's list): Education; whichever of Music / Arts / Creative the portal offers.

**Category** (ChatGPT, one): Education & Research.

## Claude

The connector is the product in Claude. Claude cannot pass a file attached to the chat to a remote server, so in Claude the user chooses their score file in a card (`choose_score`), which sends it to the server; a pasted link (a direct link to a MusicXML file or PDF, or a Google Drive or Dropbox share link) works too. From there Claude uses its own tools for the PDF (`read_fetched_pdf`, for a file chosen in the card or fetched from a link) and the same analysis tools as ChatGPT (`draft_analysis`, `render_analysis`, `correct_bars`). IMSLP links are not downloaded: Claude asks the user to download the PDF from IMSLP and choose it in the card. `play` gives a small piano player in the chat. The plugin (1.10.2) adds only a skill, one Markdown file, that tells Claude to show the card and use these tools; it runs nothing in Claude's sandbox. No Code execution setting is needed.

**Carousel screenshots**, if a form asks (3–5 PNGs at least 1000 px wide, the response only, each with its prompt):
1. "Analyse the harmony of bars 1–8 of this nocturne": the full page.
2. "Just the harmony, please": the harmony view.
3. "How do the voices move in bars 5–8?": the voice-leading view.
4. "Show me the phrase structure": the form view.

## Claude: connector form

- **Connection:** `https://mcp.sheetmusicanalysis.com/mcp`
- **Name:** Sheet Music Analysis
- **One-liner:** Harmonic analysis drawn on the score. Choose a MusicXML file or a PDF and get the chords, cadences and phrases marked on the engraved page.
- **Description:**

  > Sheet Music Analysis drafts a harmonic analysis of a piece of music: a Roman numeral for every chord, the cadences and phrase ends, and melody notes that don't belong to the chord. Claude analyses the music from a beat-by-beat table of its notes and explains it, and our software checks how the parts move in music for two to four parts. It can also check a student's own Roman numerals beat by beat.
  >
  > Ask for an analysis in the chat and choose your score in the card that appears: a MusicXML file (.mxl or .musicxml) or a PDF of printed music. Choosing it sends the file to our server, which reads the music from a PDF and shows it to you with bars that may be misread shaded, then draws the analysis on the engraved score. A link to the file also works: a direct link, or a Google Drive or Dropbox link shared so anyone with it can view.

- **Categories, docs, privacy, support, icon:** as in Shared above. Slug: `sheet-music-analysis` (permanent).
- **Use cases** (use case → example prompt; the score is chosen in the card):
  - Analyse the harmony of a passage → "Analyse the harmony of bars 1–8 of my Chopin nocturne."
  - Show only one layer of the analysis → "Now show just the harmony, without the voice leading."
  - Explain the phrases and cadences → "Where are the phrases and cadences in bars 1–16?"
- **Prerequisites:** none. No account or sign-in. The user chooses a MusicXML score (.mxl or .musicxml) or a PDF of printed music in the card, or pastes a link to one; a public-domain sample is at https://sheetmusicanalysis.com/samples/chopin-nocturne-op9-no2.mxl
- **Reads or writes:** reads only.
- **Company:** Sheet Music Analysis, https://sheetmusicanalysis.com.
- **Authentication:** none.
- **Data handling:** our own service; no health data; no sponsored content.
- **Test & launch:** no test account needed. Add this URL as a custom connector and ask "Analyse the harmony of bars 1–8 of my score", then choose the sample (download it from https://sheetmusicanalysis.com/samples/chopin-nocturne-op9-no2.mxl) in the card. Claude calls `choose_score`, `draft_analysis` and `render_analysis`, and the page is shown in a card. Pasting the sample's link instead runs `fetch_score` in place of the card.

## Claude: plugin form

- **Repository:** `Vedat-Ozkan/sheet-music-analysis`, path `dist/sheet-music-analysis`, branch `main`.
- **Files:** Markdown, text and JSON only (the skill, the manifest, the connector address, a readme and the licence), plus the icon. No scripts.
- **Personal data:** none collected. Our server receives the score the user chooses in the card, or downloads it from the link they give, and keeps it, and the pages it draws, for 30 days, then deletes them. It does not keep the link.
- **Third-party services:** our own server at mcp.sheetmusicanalysis.com, hosted on Google Cloud, behind Cloudflare.
- **Retention:** scores, drawn pages and PDFs that could not be read are deleted after 30 days.
- **Age-appropriateness:** suitable for general audiences, including students under 18.

## ChatGPT: plugin ZIP

OpenAI now takes a plugin ZIP rather than a form: the text below lives in `openai-plugin/plugin.json` (see the README), and is uploaded at platform.openai.com/plugins.

- **Name** (30 characters): Sheet Music Analysis (20).
- **Description:** the shared description above.
- **Test file for reviewers:** https://sheetmusicanalysis.com/samples/chopin-nocturne-op9-no2.mxl

**Should use the app** (prompt → tools → what the user sees):

1. [attach the sample] "Analyse the harmony of bars 1–8 of this." → `draft_analysis`, then `render_analysis` → the engraved bars 1–8 with numerals, coloured bands, cadences and numbered circles, plus a commentary.
2. [same chat] "Now show only the harmony." → `render_analysis` with view `harmony` → the same bars with chords and bands only.
3. [same chat] "What happens in bars 9–16?" → `draft_analysis`, then `render_analysis` → bars 9–16 annotated, with a commentary.
4. [same chat] "Show the phrase structure of bars 1–16." → `render_analysis` with view `form` → phrase brackets and cadences.
5. [same chat] "How do the voices move in bars 5-8?" → `render_analysis` with view `voice_leading` → bars 5–8 with arrows for the resolutions that matter.

**Should not use the app:**

1. "What is a Neapolitan sixth chord?" → answered from general knowledge; no tool call (no score is involved).
2. "Here's an MP3 of my piece, can you analyse it?" → no tool call; explains that the app needs a MusicXML score or a PDF, not audio.
3. "Transpose this score to D major and send me the new file." → no tool call; the app only analyses.

- **Demo video:** a screen recording of cases 1–5 and one of the negative cases in ChatGPT, uploaded as an unlisted video.
