# Changelog

What changed in Sheet Music Analysis, newest first. Numbers in square brackets, such as [149], are entries in `docs/engineering-log.md`, which has the detail, the measurements and the checks that were run.

How to read the version lines:

- **Server revision** is the numbered version of the hosted server (for example `00065-fjv`). Production revisions are tagged `prod-<revision>` in git from `prod-00057-bnh` on. Earlier revisions come from the engineering log; where a release has no revision, none was recorded.
- **Claude plugin** is the version in `plugin/.claude-plugin/plugin.json`. Dates for plugin versions up to 1.7.5 are the dates the version was committed; the log does not always record when each was published.
- **ChatGPT app** is the version of the app listing that OpenAI reviews.
- **PDF reader** is the build of the program that turns a PDF into notes, named `5.11.0-sma.N`.

Some terms: a **Roman numeral** names a chord by its position in the key (I is the chord on the first note of the scale, V the one on the fifth). A **cadence** is the chord pair that ends a phrase. **MusicXML** is the file format music programs use to exchange scores. A **scan** is a picture of paper music, as opposed to a PDF exported from notation software; scans are much harder to read. **Shaded bars** are bars the PDF reader is not sure it read correctly, drawn shaded so the user can check them.

## Unreleased

Merged into `main` after production revision `00065-fjv`, not deployed. Server revision, Claude plugin and ChatGPT app are unchanged (`00065-fjv`, 1.10.3, 1.4.0). PDF reader: still the `5.11.0-sma.8` build, with changed settings (below).

What users will get:

- Scores whose time signature is written as a sum, such as 3+2/8, are read correctly: beats, bar lengths and checks of typed numerals now work there, where before the signature was ignored or the check crashed. Scores saved in the UTF-16 text encoding are accepted [167] (#30).
- PDF readings: a bar split in two by a repeat sign or a double bar line keeps one bar number, so later bar numbers stay right [166] (#29).
- Five clean-ups of the PDF reader's output, made after three real users' PDFs (a snare drum part, a guitar part with tablature, a classical guitar piece): bars with no notes are shaded; staves with no notes are dropped; guitar fingering numbers are not turned into dynamics; a one-instrument score takes its part name from the heading; and when much of a reading is doubtful the user is told so [179] (#34).
- PDF reader settings: snare drum rolls are read as rolls (they were read as a triplet that shifted every bar number); left-hand guitar fingering is no longer read as a note dot, or the word "rit." as a loud dynamic; grace notes sitting further from their main note are found. A PDF whose beams are too thin for the reader is read a second time with a looser setting and the better reading is kept. Scans are not reread, because the reread did not help them and cost about 20% more reading time. Fingering numbers are removed from the MusicXML given to users [180] (#35).

Fixes and changes to how things work:

- The chat card hides an old card under a status line; the test for the page's guide to the marks checks its separators [165] (#28).
- Production answers only requests that come through our proxy, which carries the per-person upload limit; before, the server's own address could be called directly and skip it. A key shared by the proxy, a secret and the running server is set with `proxy/set-key.sh` (see `docs/runbook.md`) [168] (#31).
- Draft analyses and bar corrections are now counted in a shared daily limit of 300 (the busiest recent day had 18 drafts and 5 corrections). A correction with invalid bars now costs one. If reading a score fails because of a fault on our side, the user's score is given back (not counted) while the pages already made are kept [168] (#31).

## 2026-11-14: server 00065-fjv

Server `00065-fjv` (rollback `00064-tcs`), built from `3261be3`. Claude plugin 1.10.3. ChatGPT app 1.4.0, submitted to OpenAI that day and reported live by the owner on 2026-11-16. PDF reader 5.11.0-sma.8 (unchanged). The site was published the same day.

What users get:

- A **guide to the marks** at the foot of the drawn page: a small sample of each kind of mark drawn on that page (cadence codes such as PAC, the dotted and dashed brackets, the shading, the part-writing codes), listed only if the page uses them. Before this, those codes were explained nowhere on the page [162].
- Chat results name the callouts so the written commentary matches the numbers on the page; the card shows reading status; waiting sentences say what is being waited for [161, 163].
- The site gallery was redrawn with the guide, and the listing text says the chord's job is shown as a labelled bracket, not a coloured band [164].
- The "alternative reading" bracket ends where the alternative ends [162].

Fixes and changes:

- Fixes from a design review of the site and the chat cards, at phone, tablet and desktop widths in light and dark themes [161].
- Plugin 1.10.3 carries the new wording in its skill and readme [164]. ChatGPT held three `render_analysis` wording changes until OpenAI approved them.

## 2026-11-13: server 00064-tcs

Server `00064-tcs` (rollback `00063-qcs`), created 17:28 UTC. Claude plugin 1.10.2, ChatGPT app 1.3.0, PDF reader 5.11.0-sma.8 (all unchanged). The first production deploy tagged by the deploy script itself.

- Only messages written for the user reach the user as "your mistake". Before this, any stray error of one kind was reported as the user's fault; two real users' PDF reads had ended that way with no message. Faults in the server or the drawing step are now reported as ours [157] (#24).
- A runbook (`docs/runbook.md`) and `prod-*` tags from the deploy script record each release [156] (#23).

## 2026-11-13: server 00063-qcs

Server `00063-qcs` (rollback `00062-fzf`), created 16:18 UTC. Other versions unchanged.

- A scan too small to read says so. The case: a real band score whose staff lines were about 3 pixels apart in the picture (a sharp scan has at least 11). Enlarging cannot add detail that was never scanned, so the user is now told [155] (#22).

## 2026-11-13: server 00062-fzf

Server `00062-fzf` (rollback `00061-t27`), created 01:39 UTC. Other versions unchanged.

- In Claude, a card that has not been filled yet (the user has not chosen the file) now gets a plain answer, not a tool error. The Claude directory had shown a 23.1% error rate for `read_fetched_pdf` (3 of 13 calls in 30 days) because of this [154] (#21).

## 2026-11-12: server 00061-t27

Server `00061-t27` (rollback `00060-xv9`), created 18:48 UTC. The site was published too. Other versions unchanged.

- The per-person limit rose from 5 to **10 new scores a day**, and a score the same person sent before is free. Cause: a returning ChatGPT user sent five different files, then five more in the same turn, and was refused all five. No other person had used more than 6 new scores in a day since 13 October [153] (#20).

## 2026-11-12: server 00060-xv9

Server `00060-xv9` (rollback `00059-8sb`), built from `c114e23`. Other versions unchanged.

- **One person's PDFs are read one after another.** A real ChatGPT user (10 November) never got an analysis because their own repeated sends kept each other waiting; every "busy" answer was one user against themselves [151] (#18).
- A PDF attached in ChatGPT and sent again is read from our kept copy, not downloaded again; the copy is kept 30 days. Reads in progress are released when the server shuts down instead of blocking others for 15 minutes [151].
- When ChatGPT's attachment cannot be downloaded, the user gets a plain answer, and the status and host are logged [150] (#16).
- Site: gallery redrawn; help text says "bracket" instead of "coloured band"; privacy page says files are kept 30 days [152] (#17).

## 2026-11-10: server 00059-8sb, PDF reader sma.8, Claude plugin 1.10.2, ChatGPT 1.3.0

Server `00059-8sb` (rollback `00058-lxg`), built from `f8304ce`, about 18:30 UTC. **PDF reader 5.11.0-sma.8.** Claude plugin 1.10.2 (merged the same day with no server change, #13). ChatGPT app 1.3.0 published by the owner that day.

- **Student check asks which beat.** If a student types Roman numerals without beats ("iv V"), they are placed one per beat; if that is not possible the user is asked. Claude is told never to choose beats itself. Before, Claude invented "beat 3" in a two-beat bar [147] (#14).
- **The reader reads small clef changes.** A clef printed small in the middle of a line (for example a small treble clef in Mozart K. 545) was lost, which gave wrong pitches for the rest of the line without any shading [148].
- Readings cached under the earlier reader are not reused, so a PDF sent again is read once more [149].
- Site: a new "Add from a repository" install step and a link to the reader's source [149].
- Plugin 1.10.2: the readme and skill no longer describe the draft model (removed from the server in 00058), and the readme says the first 8 pages of a PDF are read [146] (#13).

## 2026-11-10: server 00058-lxg

Server `00058-lxg` (rollback `00057-bnh`), built from `a3429eb`. Claude plugin 1.10.1, ChatGPT 1.2.0, PDF reader sma.7 (unchanged).

- **Limits on new scores:** 100 a day for everyone together, 5 per person (per ChatGPT user; per device in Claude's upload card), and 30 uploads a day per internet connection in the proxy. A score is charged once, when it first arrives from outside; anything derived from it (drafts, corrections, re-reads of a cached PDF) is free. PDFs are always read without slurs; the slurs option was removed [142].
- **The draft model was removed from the server**, and the older Claude tools were kept only in a form that works without it. Since 2026-11-07 the draft was not sent to the chat model anyway. The check of a chorale's part-writing no longer uses the model's chords [143].
- **Student check tests each numeral against the notes.** Numerals typed without a key, or on a beat the bar does not have (for example beat 3 of a 6/8 bar, which has two beats), are handled instead of failing [143, 144].
- The Claude upload card adds "If your reply box is empty, type 'I've chosen it' and send that", for Claude Desktop [142].
- Recorded in [145].

## 2026-11-09: server 00057-bnh, Claude plugin 1.10.1

Server `00057-bnh`, created 06:24 UTC, tagged on `7243eb2`. Claude plugin 1.10.1 (merged at 06:51, no server change). ChatGPT app 1.2.0 and reader sma.7 unchanged.

- **PDFs of any length:** only the first 8 pages are read, and the reply says which. The old refusal of PDFs over 12 pages is gone. A new user's 27-page PDF had been refused on 2026-11-08 [137].
- **Files are kept 30 days** instead of 1 (failed PDFs: 7 days before). The privacy page, help page, readme and listing say so [138].
- **"Scan too small" warning** is now decided from the scan itself. Two 80 dpi scans had been read with no warning, one with 33 of 38 bars shaded [139].
- **"Suggest something"** control on the chat cards, so users can tell us what they want, not only what fails [140].
- Plugin 1.10.1: the readme says 30 days [141]. Recorded in [145].

## 2026-11-09: server 00056-j5d, Claude plugin 1.10.0

Server `00056-j5d` from `fd8133e` (about 05:50 UTC). **Claude plugin 1.10.0.** ChatGPT app 1.2.0. Site published.

- **In Claude, the user chooses the score in an upload card.** Claude cannot hand a chat attachment to a hosted tool, so a small card in the chat sends the chosen file straight to our server and one click starts the analysis. Links stay as a fallback [134].
- Merged just before the card (the log does not say which revision first carried them): a card that lets the user send us a failed call with one tap in ChatGPT ("Send this problem to us"; it sends only a reference number, nothing from the chat) [135], and ChatGPT analysing straight after a PDF read, with doubtful bars still shaded; before, ChatGPT stopped to ask the user to check the reading and three of four PDF users stopped there [136].

## 2026-11-07 to 2026-11-08: Claude plugin 1.9.0, ChatGPT 1.2.0

Server revisions for these dates were not recorded. **Claude plugin 1.9.0**, **ChatGPT app 1.2.0** (approved and published by the owner on 2026-11-08), PDF reader sma.7.

- **A drawing crash no longer stops the server.** A real scan (Ravel, *Oiseaux tristes*) crashed the drawing step on a beam made of nothing but spaces, ending the whole server for everyone on that instance. The drawing step now runs in two separate worker processes, so one crash costs only that call [129, 130] (#3, #4).
- **PDFs with odd page sizes** are read. Two real PDFs had been refused ("No music could be read"): one at 1600 x 2133 pixels, one at about 7000 x 10000. Failed PDFs are now kept to find out why [127] (#2).
- **The site's accuracy headline is by chord:** our analysis agrees with an expert 99% as often as experts agree with each other (0.6939 against 0.6974, on 36 pieces and 1,327 bars). The site gained a "How we tested it" page [131] (#5).
- **Plugin 1.9.0:** one plugin for both Claude's directory and our own marketplace. The skill no longer runs scripts in Claude's sandbox (the directory had refused 1.8.0 for its Python files); the user gives a link and a server tool downloads the score [132] (#7).
- Leftovers from superseded designs were removed or marked [133] (#6).

## 2026-11-07: server 00048-9ss, PDF reader sma.7, Claude plugin 1.8.0

Server `00048-9ss` (staging `00079-h4f`), `main` at `3596be6`. **PDF reader 5.11.0-sma.7** (63 changes on top of the upstream 5.11.0). **Claude plugin 1.8.0** (committed 2026-11-06). Recorded in [124].

- **The draft model is parked.** The server now sends the chat model the method, the guides and a table of the notes, with no draft section. The measurements: the draft added no accuracy for any reviewer and missed more chord changes (27 against 19 per 100) [118, 119, 122, 124].
- **A mark the score cannot take is left out the same way everywhere:** the page is drawn without it and the mark is listed with a warning, instead of the whole drawing being refused [123].
- The reader includes the octave-line ("8va") and sign-reading fixes of entries 103 to 107, and warns when notes do not line up [114].
- Accuracy measured on 36 pieces with two expert analyses (1,327 bars): agreement with an expert 0.74 by time against 0.70 between two experts [122].

## 2026-11-05 to 2026-11-06: server 00044 to 00047, Claude plugin 1.7.1 to 1.7.5

Server `00044-v72` (5 November), `00045-6px` (5 November), `00046-cdp` (dated 6 November in the log), `00047` (6 November; its full name was not recorded). **PDF reader 5.11.0-sma.6** from 00044. Claude plugin 1.7.1 to 1.7.5 (committed 5 to 6 November). ChatGPT app 1.0.0 (1.1.0 was prepared on 6 November [111]; its publication date was not recorded).

- **00044, reader sma.6:** printed flats on PDFs made with an old music font were being lost, a fault introduced by sma.5; production users had it from 2026-11-03 until this deploy [102, 109]. The tests had also not been using the same reader as production, and now do [109].
- **00045, long PDF reads reach the user.** The web front door in front of the server cuts a call after 125 seconds (not ChatGPT, as first thought). The result now arrives as an event stream that keeps the call alive; a PDF read took 145 s on production with no error. The ChatGPT card shows the first 2 pages [105, 110].
- **00046:** a multi-movement PDF no longer loses everything after the first movement. Plugin 1.7.3. Confirmed in real ChatGPT on 6 November (a 149.6 s read, card drawn) [110].
- **00047 (plugin 1.7.5):** seven carry-over defects found by audit and fixed, among them note-name hints judged against the wrong clef (666 of 49,749 notes of the test scores), ties and voices kept per voice, and keys that change mid-bar [113]. Plugin 1.7.4 gives the PDF reader a fixed environment, which is how the Claude directory's "uses a credential" hold was traced and removed [112].
- Plugin 1.7.2 drops an unused tall-card code path [110].

## 2026-11-03: PDF reader sma.5, Claude plugin 1.7.0

Production revision `00043` (the full name was not recorded), staging `00071`. **PDF reader 5.11.0-sma.5.** **Claude plugin 1.7.0.**

- Fewer silent wrong pitches in PDF readings: wrong pitches nothing flagged fell from 238 to 107 on the benchmark, then 102, through fixes for octave lines, missed clefs and accidentals [99 to 101].
- Bundled text fonts and symbol shapes for PDFs drawn with the Leland music font [92].
- This build lost printed flats on old PDFs; fixed in sma.6 [102].

## 2026-11-02: PDF reader sma.4, Claude plugin 1.6.0

Staging `00069`; the production revision was not recorded. **PDF reader 5.11.0-sma.4.** **Claude plugin 1.6.0.**

- 8/8 time signatures are accepted [90].
- A scan with a background fill still counts as a scan, and a scan's picture is found even when its resources are inherited from the page tree [90].
- Root-cause work on bars that "don't add up" in PDF readings, with a goal of under 100 flagged bars on the main benchmark [90].

## 2026-11-01: Claude plugin 1.5.0

Server revision not recorded. **Claude plugin 1.5.0.** **PDF reader 5.11.0-sma.3** (note heads and beams read about 1.5 times faster, same accuracy).

- **A whole piece comes back as one PDF.** The 32-bar cap on a page is gone; longer stretches are split into printable pages at phrase ends. The server moved to 4 virtual CPUs [87, 89].
- **PDF reading in claude.ai works:** pinned packages, and text-recognition data downloaded from a place claude.ai's sandbox allows [89].
- ChatGPT could not see the annotation format and never drew; the published tool descriptions now spell out every field in place [88].
- PDF reads were too slow for ChatGPT (every new multi-page read took 220 to 310 seconds; on 31 October two of four users left after one failed read). Reworked: a 900-second request limit, the starting call stays open for the read, repeats wait up to 100 seconds, only the first 8 pages of a longer PDF are read [86].
- Daily counters are exact across instances [86].

## 2026-10-30 to 2026-10-31: Releases A and B, Claude plugin 1.3.0 and 1.4.0

Server revisions not recorded. **Claude plugin 1.3.0** (Release A, 30 October), **1.4.0** (Release B, 31 October).

- **Held-open streams.** From 27 October the server billed 7,300 to 10,800 instance-seconds a day (about 300 before) because clients opened a standing event stream that the server held for five minutes. It now answers that request with "not supported". October still ended near the free tier (about US$0.16) [75].
- **Three crashes from real ChatGPT files in one day** (a scan read without a time signature; transposing saxophones with an octave change; a voice written twice in a bar) were fixed, each checked across the 64 test scores [76].
- A daily user code lets us count users without tracking them [78]. Cost and safety guards: alerts, a cost report, a one-instance limit, a deploy guard.
- Eleven engine defects from an eight-reviewer pass were fixed, each with a check across the whole test set [79 to 81].
- Score work takes turns in one queue and every skill script starts (Release A). The engine fixes and compact rests went into plugin 1.4.0 (Release B) [84].
- **Multi-bar rests** are drawn compactly again with every bar still counted [84].
- ChatGPT card: a thumbs up or down once per conversation, and a dark theme [83].
- The MIDI export plays repeats and endings in order. Scores without a time signature, and transpositions with an octave change, are read.

## 2026-10-26 to 2026-10-28: Claude plugin 1.1.0 to 1.2.1, engine 0.2.0

Server revision not recorded. **Claude plugin 1.1.0 and 1.2.0 (26 October), 1.2.1 (27 October).** Engine package `v0.2.0` tagged 27 October (`v0.1.0` was tagged 22 October; the engine package is also used by a separate project).

- **A small piano player in the chat** (1.2.0): plays the passage with dynamics, pedal, ornaments, turns and tempo words, in light and dark themes.
- An unmarked short first bar is treated as the pickup (bar 0), and marks printed just before a barline are placed at the start of the next bar. A pedal fix is in 1.2.1.
- On 28 October an **alternative reading** mark was added: another accepted reading drawn as a dotted bracket under the numerals. The plugin was rebuilt that day; no version change is recorded.
- Evaluation work these days (entries 58 to 74): 30 pieces the draft model never saw; 124 and then 151 pairs of expert analyses; scorer audits that corrected published figures. Public accuracy text at the time: reviewed analysis 67% against 48% for the draft and 71% between experts [58, 59, 66].

## 2026-10-23 to 2026-10-24: monitoring and load limits

Production revisions `00027` and `00028` (24 October). Claude plugin 1.0.0.

- One JSON log line per tool call, with timings by stage; metrics, a dashboard and email alerts; call tracing [46 to 48].
- A staging service with its own storage, login required; deploys upload 5 MB instead of 3.7 GiB [46].
- **Cold start cut from 52.5 s to 13.7 s** on staging by reading the model's files ahead [49].
- Load tests: two calls at once per instance, at most two instances, about US$0.38 per 1,000 calls [50]. Service level objectives for errors and draft speed [51]. The budget alert now counts the free tier [52].
- Turning recorded audio into a score was tested and **parked**: even with perfect timing it missed the accuracy bar [53 to 57].
- Error messages are kept out of the logs, since they can quote user input [60].

## 2026-10-10 to 2026-10-13: drawing quality and the first PDF reading

Production revisions `00018-s45` (10 October), `00019-7n7` and `00023-bmn` (11 October), `00024-cgv` (12 October). Claude plugin 1.0.0. **PDF reader 5.11.0-sma.2 (12 October).**

- **Engraving rounds:** the page looks printed: slurs on the correct side and not through beams, doubled labels removed, lone bars on the last line fixed, line breaks at phrase ends, fonts, empty staves removed [22 to 27, 42 to 44]. A **vector PDF** and **piano reductions of large scores** (one decision per sounding note) were added [28, 29, 40].
- **PDFs of printed music can be read** (11 October). The first version crashed the live server on a file that was not MusicXML; anything that is not MusicXML is now refused before the drawing step [33, 34]. On 12 October the reader was improved (best of three readings, triplet repair, mid-line treble clefs), taking the main benchmark from 86.6% to 91.4% pitch right and from 78.3% to 84.5% pitch and timing right [35, 41].
- A usage report that reads the existing logs [30].
- Merged on 12 to 13 October, with no deployment recorded for them in these entries: the **voice-leading report** for chorale-style scores [37], and the **check my analysis** and **correct bars** tools, notation styles and MusicXML export [38, 39].
- A tie between readings no longer goes to the sparser one [45]. B minor and B-flat minor key names are read as keys, not as flat signs.

## 2026-10-06 to 2026-10-08: first production release

Server revision not recorded. **Claude plugin 1.0.0**; ChatGPT app 1.0.0 (listing package built 6 October; the date it was published is not recorded). The server went live on 6 October at `mcp.sheetmusicanalysis.com`, with the website at `sheetmusicanalysis.com`.

- The server, the website, a Claude plugin for the directory and a ChatGPT listing package, all dated 6 October.
- The draft model stayed loaded between calls. On the hosted server the first draft after a deploy took about 60 s (loading the model's library dominated); later drafts took 0.4 to 3 s [17].
- Crowded chord labels are given room under the bar [18]. A page is capped at 32 bars.
- ChatGPT users attach the score as usual (the file button was removed); drafts no longer fetch arbitrary links.
- 8 October: Claude's held "listen" requests were costing about four hours of server time a day; the server stopped serving them [21].

## 2026-10-01 to 2026-10-05: early development

A local engine, a test server and evaluation work; nothing hosted yet. Tags `v0.1.0` (22 October) and `v0.2.0` (27 October) came later.

- **1 October:** first commit: the analysis engine (reads a score, makes a note table, drafts and draws a harmonic analysis), a Claude plugin and a test server. The same day it was made robust across instruments, eras and file quirks: 31 scores from Monteverdi to Schoenberg, choirs, quartets, songs, piano, transposing instruments [4].
- **2 to 3 October:** evaluation against human analyses was built, and the model that reviews the draft was chosen by measurement. The neural draft never said "minor", so every minor key was read as major; recovering the mode from the chords lifted key accuracy on minor-key pieces from 0.00 to 0.92 (Chopin Prelude No. 20), 0.27 to 0.79 (Beethoven Op. 2 No. 1) and 0.20 to 0.89 (Tchaikovsky) [1, 8 to 11].
- **4 October:** cadential 6/4 chords (a chord that sounds like a tonic but acts as a dominant) were split correctly in the draft, a scorer bug was fixed, and the measure of noise and of the human ceiling (how far experts agree with each other) was built. Experts agree 0.87 on Bach chorales, 0.79 on Mozart sonatas, 0.59 to 0.65 on Chopin mazurkas and Beethoven sonatas [13 to 16].
