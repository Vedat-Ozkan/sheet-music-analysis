# Revised plan: sheet-music harmonic analysis for Claude and ChatGPT

## Context

The 2026-10-01 handoff planned a Claude Code plugin that runs everything on the user's machine, with AugmentedNet as the draft model and OpenAI covered in two lines. Research on 2026-10-01 and the owner's answers change the shape of the project:

- **Goal:** a tool that Claude and ChatGPT reach for (and suggest) when a music student or composer asks for an analysis of a score, with real usage numbers for a resume, and analysis good enough to trust.
- **Owner decisions:** small hosting budget is fine; v1 is a comprehensive *classical* analysis (jazz is v2); MusicXML input first; AnalysisGNN is the v1 engine; quality before deadline; the owner wants to see real examples in both Claude and ChatGPT before any display/UI choice is made.

## What changed from the handoff

| Handoff said | Now |
|---|---|
| Local plugin; heavy ML runtime is the packaging risk | **Hosted MCP server** runs the engine. Model weight and compiled extensions stay on the server. Anthropic's directory also holds plugins containing model weights for manual review and blocks files over 5 MiB. |
| AugmentedNet now, AnalysisGNN later | **AnalysisGNN in v1** (cadences, phrases, sections, pedal points, non-chord tones; 0.530 vs 0.464). AugmentedNet is the fallback behind the same interface. RNHybrid (0.576, same repo) is the upgrade path. |
| Submit at platform.claude.com/plugins/submit, SHA-pinned | That form is retired. Submit at **claude.ai/directory/manage** (paid plan). Listings track a branch/tag and re-scan on each commit. |
| Plugins are a Claude Code thing | Directory listings appear in claude.ai chat (web, desktop, mobile), Cowork and Claude Code. **Only directory connectors are suggested in chat**; plugins and skills are not. |
| Codex: no self-serve directory | OpenAI renamed apps to **plugins** (July 2026); one directory serves ChatGPT and Codex; verified individuals can submit. **Custom GPTs retire 2026-12-11**, so no GPT. |
| PNG shown inline in chat | Works on Claude. **Unreliable in ChatGPT** (Sept 2026 forum reports). Decision deferred to Gate 1. |
| No metrics | Anthropic gives publishers installs, active accounts, retention and runs (90 days, CSV). OpenAI gives nothing, so count on the server. |
| Convert AugmentedNet to ONNX | Dropped as a v1 task. If the fallback is needed, re-implement its forward pass in numpy (tf2onnx has known GRU problems). |

## Architecture

```
Chat (Claude or ChatGPT) + bundled skill (analysis method)
   │ 1. draft_analysis(score)          → compact per-beat table + model draft
   │ 2. chat model reviews, corrects, writes annotation list + commentary
   │ 3. render_analysis(score_id, annotations, view) → page images + PDF
   ▼
Hosted MCP server (streamable HTTP, no login, rate-limited)
   partitura/music21 parse → AnalysisGNN draft → inject MEI <harm>/<fb>, colors
   → Verovio 6.x SVG (xmlIdChecksum + bounding boxes) → overlay (arrows, bands,
   brackets, callouts) → resvg_py PNG → img2pdf PDF
```

- The handoff's central contract is kept: the chat model emits an **annotation list** in musical positions; scripts draw.
- The chat model is the reviewer, so there is no LLM cost on the server.
- The skill carries the full method (function before labels, key areas, cadences, non-chord tones, voice leading, surprise, two zoom levels; student and composer roles). Tool descriptions carry a short version for users who connect without the skill.
- Views stay separate (harmony / voice leading / form) with numbered callouts tied to the commentary.
- Uploaded scores are deleted within 24 hours; only counts and hashes are kept.

Repo layout (the project directory is currently empty):
`engine/` (parse, model adapters, annotation schema, inject, render, overlay, export) · `server/` (MCP tools, storage, rate limit, counters) · `plugin/` (Claude plugin: `plugin.json`, `skills/<name>/SKILL.md`, `.mcp.json`; OpenAI package generated from it) · `site/` (landing, gallery, privacy, terms, support) · `eval/` · `tests/`.

## Steps

**0. Setup**
- Pick the permanent name (OpenAI limit 30 characters; the Claude slug cannot change; must be distinctive). Register a domain.
- Download the AnalysisGNN weights from Weights & Biases (`melkisedeath/AnalysisGNN/model-uvj2ddun:v1`).

**1. Platform spike → Gate 1 (owner decides display and upload)**
- Deploy a throwaway MCP server with one tool that engraves an uploaded score with Verovio and returns it. No analysis yet.
- Connect it as a custom connector in Claude and in ChatGPT developer mode; test on web and mobile.
- Answer the two unknowns that decide the architecture:
  - *File in:* can a tool receive the attached .mxl? ChatGPT has `openai/fileParams` (one report of about 10% dropped calls). Claude has no documented mechanism. Candidates if it fails: an upload link returned by the tool, a file picker in an in-chat card, or running parse/render inside Claude's sandbox.
  - *Image out:* does the page render inline, and at what size? Claude caps tool results near 150k characters; ChatGPT may need an in-chat card or links.
- Show the owner screenshots of each working option on both platforms. Nothing about cards, links or upload pages is built further until the owner chooses.

**2. Engine spike → Gate 2 (owner approves the look)**
- Finish the AnalysisGNN install (torch-sparse, pyg-lib, gitpython) in a container; run it on the Chopin nocturne; record CPU time and memory. Target: under 30 s for a 40-bar piano piece (Claude's limit is 240 s per call).
- Write the annotation list spec (measure, beat, staff, note ID, type, label, view, role, callout number).
- Produce bars 1–8 by hand-written annotation list: numerals, function bands, one voice-leading arrow, cadence label, phrase bracket, PNG and PDF.
- If AnalysisGNN is too slow or the licence is refused, switch the adapter to AugmentedNet (numpy forward pass).

**3. Full classical engine**
- All agreed visual vocabulary for classical; three views; arrows across system breaks; collision avoidance.
- Draft `SKILL.md`; build the draft → review → render loop end to end in Claude.

**4. Accuracy → Gate 3 (owner approves the quality bar)**
- Score draft-only against draft + chat-model review on held-out pieces from When in Rome and DCML, and on Bach chorales.
- Run the same pieces through Second Ear and compare.
- Add `claude plugin eval` suites so skill edits can't regress silently.

**5. Package and submit → Gate 4 (owner approves name and listing text)**
- Site: landing page with a static gallery, docs, privacy policy, terms, support contact (both directories require these).
- *Anthropic* (claude.ai/directory/manage): list the **connector** (needed for in-chat suggestions) and the **plugin** bundling the skill. Tool titles, read-only hints, test access, no `bin/` folder, no weights in the plugin, `claude plugin validate --strict` plus the portal's own validation. State that rendering is deterministic engraving, since AI image-generation connectors are not accepted.
- *OpenAI* (plugin submission portal): individual verification, domain challenge file, plugin ZIP via the official Claude-plugin conversion, 5 positive and 3 negative test cases, a video walkthrough, four URLs, tool descriptions written as "Use this when…".

**6. Launch and measure**
- Server counters per platform: analyses run, unique sessions per week. Anthropic Usage tab for installs and retention. GitHub stars as a secondary signal.
- Outreach: theory teachers, r/musictheory and r/composer (check each sub's self-promotion rules first), MuseScore forum, MCP registries.
- Expectation: no published numbers exist for comparable tools. Without featured placement, tens to low hundreds of users a month is a reasonable guess; suggestions on Claude and outside traffic are what move it.

**v2:** jazz lens (public-domain 1930 standards such as "I Got Rhythm" and "Body and Soul", self-written lead sheets), PDF input (homr or Audiveris with a confirm-the-score step), RNHybrid.

## Risks

- **File hand-off from Claude chat to the server** is undocumented. Step 1 exists to settle it.
- **AnalysisGNN:** unfinished install, weights only on W&B, README says "under construction", no weights licence.
- **Recommendation is not guaranteed:** Claude ranks suggestions by usage; ChatGPT's in-chat suggestions and Free-plan access are reported only by secondary sources.
- **Review times** are unpublished on both sides.
- **Whole-score accuracy:** frontier models alone score about 38% on harmony from text, and the best draft model 58%. The review loop has to be measured (step 4), not assumed.

## Verification

1. `pytest` for engine units: annotation schema validation, MEI injection, overlay geometry against Verovio bounding boxes.
2. Golden-image test: the Chopin nocturne bars 1–8 render matches a stored PNG.
3. MCP Inspector against the local server, then a custom connector in Claude and developer mode in ChatGPT, each on web and mobile, with the Chopin file and one Bach chorale.
4. `eval/` accuracy script prints exact-label accuracy for draft-only and draft + review.
5. `claude plugin validate --strict ./plugin` and `claude plugin eval` pass; both portals' validators pass.

## Housekeeping

Two empty folders (`research_notes/Sheet music plugin plan revision/`, `reports/`) were created before plan mode started; remove or reuse them. The research findings exist only in this session, so the first execution step is to save them, with source links, to `docs/research-2026-10-01.md`.
