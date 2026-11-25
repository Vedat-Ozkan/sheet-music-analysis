# Changelog

What changed for users, newest first. Numbers in brackets are entries in `docs/engineering-log.md`; #n are pull requests.

## Unreleased

- Not merged yet (branch `go-on-wording`): what the server tells a chat after a reading and after a draft now ends with the next step, so fewer chats stop before the page is drawn [208].
- Not merged yet (branch `go-on-wording`): the note on a scan's reading says the analysis may be wrong where the reading is, instead of asking the user to check carefully [208].
- Not merged yet (branch `faster-ci`): the tests on GitHub run as four parallel jobs, a text-only change runs only the tests that read texts, and a deploy accepts the pull request's full test run when main holds exactly what it tested, and never a text-only run [209].

## 2026-11-25: server 00070-555

Claude plugin unchanged (1.10.3). ChatGPT app unchanged (1.5.0).

- A scanned PDF is analysed straight away from the quick reading, and the careful reading is offered at the end of that analysis instead of before it [207] (#48).
- The card's "Suggest something" box says how to show us a chat (share it, paste the link), and opens by itself after a thumbs-down or after a problem is sent to us; the privacy page says what a pasted chat link lets us read [205] (#47).

## 2026-11-24: server 00069-8bl

Claude plugin unchanged (1.10.3). ChatGPT app unchanged (1.5.0).

- An unknown score or PDF id is answered without repeating the id; the server's log records which of our own error sentences a chat was given, and never one that quotes the score [204] (#45).

## 2026-11-23: server 00067-4r6

Claude plugin unchanged (1.10.3). ChatGPT app 1.5.0, published the same day.

- Time signatures written as a sum, such as 3+2/8, are read correctly; scores saved as UTF-16 are accepted [167] (#30).
- In PDF readings, a bar split by a repeat sign or double bar line keeps one bar number [166] (#29).
- Cleaner reading of PDFs with drums or guitar: empty bars are shaded, empty staves dropped, fingering numbers no longer turned into dynamics, and the user is warned when much of a reading is doubtful [179] (#34).
- Drum rolls and wider grace notes are read; a PDF with very thin beams is read a second time and the better reading kept [180] (#35).
- Production answers only requests that come through our proxy; draft analyses and corrections share a daily limit of 300 [168] (#31).
- A scanned PDF can be read a second, slower way by the chat itself, page by page; the chat offers it and says how long it takes before starting [197, 201].
- With no bars named, the whole piece is analysed without a question first; the reply is written for a player, in sentences rather than tables, and ends with one thing to listen for [198, 201].
- The drawn page keeps the bars chosen for each line (no more single bars left alone), has tighter gaps between lines, and its guide to the marks is shorter and sits under the last page the chat shows [182, 183] (#37).
- The PDF download is laid out for Letter paper [184, 185].
- Chord symbols printed in a score stay on the drawn page and are given to the chat [199].
- Bars are named as in the printed copy, such as "16a" for a bar the print does not number; a pickup bar marked by the PDF reader is trusted [189, 190].
- A voice keeps its number from bar to bar; a key change shared by all parts is read in concert pitch [187].
- The piano version always writes its opening key and time signature, keeps every part, shows no part labels, and says plainly when it cannot be written faithfully [191, 194].
- A part of a PDF reading that lost a bar gets a bar of rest, so all parts hold the same bars [195].
- A correction of bars is no longer refused for bars the server itself handed out [196].
- Each drawing request gets a drawing process to itself and the others wait in line; a PDF that could not be read is not read again [192, 186].
- A PDF read runs inside a request of its own, so it no longer slows to a crawl between two calls from the chat [173] (#33).
- The chat card in ChatGPT no longer empties itself, and a failed reading keeps its "send this problem to us" button [200].
- The upload card no longer puts the device code in the web address; the privacy page names the note that a file was already sent [170] (#32).
- Tools that store something are announced to the chat as such; only playing a score and starting a careful reading are announced as read-only [201].

## 2026-11-14: server 00065-fjv

Claude plugin 1.10.3. ChatGPT app 1.4.0.

- A guide to the marks at the foot of the drawn page explains each kind of mark used on it [162].
- Chat results name the callouts that match the numbers on the page [161, 163].
- Site gallery redrawn with the guide [164].

## 2026-11-13: server 00064-tcs

- Only messages written for the user are reported as the user's mistake; faults on our side are reported as ours [157].

## 2026-11-13: server 00063-qcs

- A scan too small to read now says so [155].

## 2026-11-13: server 00062-fzf

- In Claude, a card the user has not filled yet gets a plain answer instead of a tool error [154].

## 2026-11-12: server 00061-t27

- Limit raised to 10 new scores per person a day; a score sent again is free [153].

## 2026-11-12: server 00060-xv9

- One person's PDFs are read one after another [151].
- A PDF attached again in ChatGPT is read from our kept copy [151].
- Failed attachment downloads in ChatGPT get a plain answer [150].
- Site gallery redrawn; privacy page says files are kept 30 days [152].

## 2026-11-10: server 00059-8sb

PDF reader 5.11.0-sma.8. Claude plugin 1.10.2. ChatGPT app 1.3.0.

- Student check: numerals typed without beats are placed one per beat, or the user is asked [147].
- Clef changes printed small in a PDF are read instead of lost [148].

## 2026-11-10: server 00058-lxg

- Limits on new scores: 100 a day in total, 5 per person, 30 uploads a day per internet connection [142].
- The draft model was removed from the server [143].
- Student check tests each numeral against the notes [143, 144].

## 2026-11-09: server 00057-bnh

Claude plugin 1.10.1.

- PDFs of any length are accepted; the first 8 pages are read [137].
- Stored files are kept 30 days instead of 1 [138].
- The "scan too small" warning is decided from the scan itself [139].
- "Suggest something" added to the chat cards [140].

## 2026-11-09: server 00056-j5d

Claude plugin 1.10.0.

- In Claude the user chooses the score in an upload card; links remain as a fallback [134].

## 2026-11-08

ChatGPT app 1.2.0 published.

- The site's accuracy headline is now by chord: agreement with an expert 99% as often as experts agree with each other [131].

## 2026-11-07: server 00048-9ss

PDF reader 5.11.0-sma.7. Claude plugin 1.8.0.

- The draft model's output is no longer sent to the chat model [124].
- A mark the score cannot take is left out with a warning instead of the whole drawing being refused [123].

## 2026-11-06: servers 00046-cdp and 00047

Claude plugin 1.7.5 (with 00047).

- A multi-movement PDF no longer loses movements after the first [110].
- Seven defects found by audit fixed, including clef handling in note-name hints and mid-bar key changes [113].

## 2026-11-05: servers 00044-v72 and 00045-6px

PDF reader 5.11.0-sma.6 (00044).

- Printed flats on PDFs made with old music fonts are read again [109].
- Long PDF reads now reach the user past the 125-second limit of the web front door [110].

## 2026-11-03: server 00043

PDF reader 5.11.0-sma.5.

- Fewer silent wrong pitches in PDF readings [101].

## 2026-10-24: servers 00027 and 00028

- Logging, metrics, alerts and tracing for every call [46-48].
- Cold start cut from 52.5 s to 13.7 s on staging [49].
- Two calls at once per instance, at most two instances [50].

## 2026-10-12: server 00024-cgv

- More accurate PDF reading: best of three readings, triplet repair [35].

## 2026-10-11: servers 00019-7n7 and 00023-bmn

- PDFs of printed music can be read [33].
- A file that is not MusicXML is refused before drawing instead of crashing the server [34].

## 2026-10-10: server 00018-s45

- Printed-looking pages: better slurs, labels and line breaks, vector PDF output, piano reductions of large scores [22-29].

## 2026-10-01 to 2026-10-06: early development and first release

- 1 Oct: first commit: analysis engine, Claude plugin and a test server; made robust across instruments and eras.
- 2-4 Oct: evaluation against human analyses built [1-16].
- 6 Oct: server, website and Claude plugin 1.0.0 added (sheetmusicanalysis.com, mcp.sheetmusicanalysis.com).
