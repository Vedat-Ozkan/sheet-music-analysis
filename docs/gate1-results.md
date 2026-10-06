# Gate 1 results

Observations from running `docs/gate1-checklist.md`. Server-side facts come from `out/spike/calls.log`.

## Claude (claude.ai web)

**Prompt 1, sample analysis as inline image (2026-10-01)**

- The tool call succeeded: one `sample_analysis` call, user agent `Claude-User`, 89 KB PNG returned inline (about 119,000 base64 characters, under the 150,000 limit).
- The image was **not shown in the reply**. Claude gave "View as PNG" and "View as PDF" links instead; the PNG link opened.
- Claude did receive the image: its summary named the P, N and APP labels and the 4–3 and 7→3 arrows, none of which are in the tool's text.
- Not yet checked: whether the image is visible when the tool-call row is expanded.
- Side finding on file input: with the `.mxl` attached, Claude reported its contents "came through empty". A compressed `.mxl` attachment is not readable by Claude as text.

**Prompt 2, sample analysis in a card (2026-10-01)**

- The card rendered in the conversation: the full annotated page at the width of the chat column, with the caption and a "Download PDF" link under it. The image loaded from the server's address, so the card's content-security settings work.
- The card grew to the full height of the page (four systems), which is taller than the window; Claude overlays a scroll-down button.
- The card's header shows the raw tool name (`sample_analysis_card`), so production tool names need to read well.
- Claude's reply repeated a PDF link and again noted that the attached `.mxl` was not read.
- Not yet checked: whether "Download PDF" inside the card opens the file.

**Prompt 3, engrave from the attached `.mxl` (2026-10-01)**

- The attachment could not be passed to the tool. Claude never called `engrave_score`; the only call that reached the server was `get_upload_link`.
- Claude could open the file inside its own sandbox (it reported "a valid compressed MusicXML archive with one score inside"), then tried to send it to the server from the sandbox. That attempt was blocked and never reached the server, so the sandbox cannot reach an arbitrary host.
- Claude recovered on its own by offering the upload page and asking for the code.
- Conclusion: on Claude, a chat attachment does not reach a connector. The routes left are the upload page, a file picker inside a card, or a public link.

**Prompt 4, upload page and code (2026-10-01)**

- The upload page worked: the owner uploaded the `.mxl`, got the code, pasted it into the chat, and Claude called `engrave_score` with that code and bars 1–8.
- Two more ways the page surfaces on Claude appeared here:
  - the tool-call row carries a small thumbnail of the returned image;
  - Claude embedded the PNG link as an image, which claude.ai shows as a "Show Image" box that loads on click.
- PNG and PDF links were given as before.
- Not yet checked: what "Show Image" displays when clicked, and what the thumbnail opens.

**Prompt 6, a real analysis of bars 1–8 (2026-10-01)**

- Claude called `draft_analysis` with the upload code (6.4 s on the server, 3,634 characters returned) and, 41 seconds later, `render_analysis` with 42 annotations. The render succeeded on the first call; no validation errors came back.
- The Claude run as a whole was judged to work well.
- Not recorded: screenshots of the reviewed page and commentary, and what "Show Image" and the tool-row thumbnail display when clicked.

**Summary for Claude**

| Question | Answer |
|---|---|
| Score in, from an attachment | Does not reach the connector |
| Score in, through the upload page and a code | Works |
| Page out, as a tool image | Seen by Claude, not shown in the reply; thumbnail on the tool row |
| Page out, in a card | Works, shown in the conversation |
| Page out, as links | Works; an embedded PNG link becomes a click-to-load "Show Image" box |
| Draft, review, render loop | Works with tool descriptions alone |

## ChatGPT (chatgpt.com web, Plus plan)

Setup: there was no Developer mode toggle under Settings > Security and login on this account. The connection was created at chatgpt.com/plugins through Add > Create MCP App. The server sees ChatGPT as `openai-mcp/1.0.0 (Codex)`.

All prompts ran in one conversation with the `.mxl` attached (2026-10-01, 22:30 to 22:32). The owner sent the transcript as text, so what was visible in the chat is not yet confirmed.

| Prompt | Server log | ChatGPT's reply |
|---|---|---|
| 1, sample as inline image | `sample_analysis`, inline | Summary, "Download PDF", "View full-size image" |
| 2, sample in a card | `sample_analysis_card` | "Opened Show sample analysis (card)" |
| 3, engrave the attachment | `engrave_score`, source `score_file`, 20,652 bytes | "Engraved bars 1–8 of your attached score", PDF and PNG links |
| 5, engrave from a link | `engrave_score`, source `score_url` | PDF and PNG links |
| 6, real analysis | `draft_analysis` (from the link, 4.8 s), then `render_analysis` twice, 37 annotations each | A download link for the annotated score and a three-point commentary |

- **The attachment reached the tool directly.** ChatGPT passed the attached file through `openai/fileParams` and the server downloaded it. No upload page was needed.
- The review was substantive: ChatGPT merged the model's sub-beat chords, corrected inversions, and read the E–B♭–D♭ over F in bars 2 and 6 as an incomplete vii°7/ii resolving to ii on beat 4.
- Screenshots (same day) show what was visible:
  - Prompts 1, 3, 5 and 6: **no image in the conversation**, only links ("Download PDF", "View full-size image", "Download the reviewed annotated score"). Unlike Claude there is no thumbnail and no click-to-load box.
  - Prompt 2: **the card showed the page in the conversation**, as on Claude: full chat width, capped height with a scroll button, caption and "Download PDF" underneath. ChatGPT adds an expand control and a "CSP off" badge (the account's "Enforce CSP for custom apps" setting was off).
  - Timings shown by ChatGPT: 16 s, 9 s, 12 s, 8 s, and 1 m 8 s for the full analysis.

## Both platforms side by side

| | Claude | ChatGPT |
|---|---|---|
| Score in, from an attachment | No | Yes |
| Score in, through the upload page | Yes | Not needed |
| Score in, from a public link | Not tried | Yes |
| Page out, plain tool image | Not shown (thumbnail on the tool row; links) | Not shown (links only) |
| Page out, card | Shown in the conversation | Shown in the conversation |
| Draft, review, render with tool descriptions only | Works | Works |

On both, the card is the only route that puts the page in the conversation itself.

## Decisions (owner, 2026-10-01)

- **Display:** the finished analysis is shown in a card on both platforms.
- **Getting a score in on Claude:** no upload page with a code to paste ("this code thingy is, very weird. don't do weird workarounds"). Replaced by a file button shown in the chat (`choose_score`); the card sends the file to the server and tells Claude to continue. Built and tested at the server level; not yet tried inside Claude.
- **Getting a score in on ChatGPT:** the attachment, as it already works.

## File button on Claude (2026-10-01, 22:48)

- With the `.mxl` attached and "Analyse bars 1–8 of the attached score…", Claude called `choose_score` within seconds and the card showed a "Choose score file" button.
- Picking the file opened the system file dialog filtered to MusicXML types; the card uploaded it (server log: 20,652 bytes from the owner's browser) and showed "Received chopin_nocturne_op9_no2.mxl".
- The card then posted a message into the chat on the owner's behalf ("I chose the score file … Its score_id is B674B6. Please continue with what I asked.") and Claude continued by itself with `draft_analysis` seven seconds later.
- Two things learned on the way:
  - Claude keeps a card's HTML by its `ui://` address and does not fetch it again, so the address must change whenever the HTML does.
  - A card must report its height as soon as it loads; waiting for the handshake reply left it at zero height.
- To polish: the card is taller than its content, and the posted message exposes the internal score id.

## Revision after the owner tried the file button (2026-10-01, late)

Verdict on picking the file a second time: rejected, because the user has already attached the file to the chat and should not have to pick it again; the goal is a route with no such trade-off.

What other extensions do, from Claude's documentation: tools that work on an attached file (Anthropic's PDF, Word and Excel skills) run as skills inside Claude's sandbox, where the attachment already is; connectors are for data that lives in an online service. No documented feature passes a chat attachment to a connector.

New design for Claude, built and tested outside Claude, not yet tried in it:

- A **skill** runs the engine in the sandbox on the attached file: note table, then render to PNG and PDF.
- The skill prints a **compact note list** (about 1,300 characters for 8 bars, 5,800 for the whole nocturne) which Claude passes to the connector's `draft_from_notes` tool, so the neural model still drafts. The model's predictions from the note list match those from the file on every note of the nocturne.
- The **connector** stays in the listing for discovery and still serves ChatGPT, where attachments reach the server directly.
- The file button remains only as a fallback for Claude users who have the connector without the skill.

## Plugin (skill plus connector) on Claude (2026-10-01, 23:06)

- The owner installed the plugin, attached the `.mxl`, and ran the analysis prompt through `/score-analysis`. Verdict: accepted.
- No second upload. The skill read the attachment in the sandbox; Claude passed the 1,292-character note list to `draft_from_notes` unchanged (server log: 3.9 s) and reviewed the draft (its commentary says where it overruled the model).
- The reply came about a minute after the prompt: five numbered points matching the callouts on the page, an overall summary, and one reading it flagged as debatable.
- Display: Claude showed the PNG as a thumbnail, the PDF as a downloadable file card, and the annotated page in its side panel. No card from the connector is involved on this route.

## Decisions as they stand

- **Claude:** plugin = skill (reads the attachment, renders in the sandbox) + connector (neural draft from a note list). Files are shown by Claude's own file display.
- **ChatGPT:** the server takes the attachment directly and shows the page in a card.
- **Fallback on Claude without the skill:** the file button.
- **Author:** Vedat Ozkan. **Licence:** MIT.
