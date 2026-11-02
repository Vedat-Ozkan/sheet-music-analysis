# Sheet Music Analysis

Harmonic analysis of sheet music, drawn on the engraved score, for music students and composers.

## Use it

First turn on **Code execution and file creation** in Claude's Settings → Capabilities: the plugin reads your file in Claude's sandbox.

Attach a MusicXML score (`.mxl` or `.musicxml`; MuseScore, Dorico, Sibelius and Finale can export one) and ask Claude to analyse a passage, for example "Analyse bars 1–8 and show me the annotated score". Claude returns the page as PNG and PDF with Roman numerals, chord functions, cadences, phrase brackets, non-chord tones and voice-leading arrows, plus a short commentary numbered to match the page. Ask for a whole piece and Claude analyses it passage by passage, then returns it as one PDF.

You can also attach a PDF of printed music; Claude reads the notes first (about half a minute a page, up to the first 8 pages of a PDF of at most 12), shows you what it read, and waits for you to check it. To get the draft analysis and the piano player, also connect the Sheet Music Analysis connector in Settings → Connectors.

Works with any Claude model; the analysis is most accurate with Claude Opus, since Claude checks and corrects the draft analysis itself (see below).

## How it works

The skill reads your attached file inside Claude's own sandbox and engraves the annotated page there. To get a neural model's draft analysis, Claude sends a compact list of the passage's notes to the Sheet Music Analysis connector; Claude then checks and corrects that draft before anything is drawn.

## What the plugin downloads and runs

Inside Claude's sandbox only, the plugin installs its Python packages from PyPI at fixed versions. The first time you attach a PDF it also downloads the music-reading program (about 105 MB) from GitHub: the program itself, our adjusted version of one of its files, and English text-recognition data. Each download is checked against a fixed checksum before it runs. Nothing is installed on your own computer.

## Data

The score file stays in your conversation. The connector receives the notes of the passage (pitches, durations, and tempo and expression words such as "cresc."; no titles or lyrics) and returns the draft; it keeps the notes for one day so the passage can be played in the chat, then deletes them. Privacy policy: https://sheetmusicanalysis.com/privacy.html

## More

- Website and how-to guide: https://sheetmusicanalysis.com
- Support: support@sheetmusicanalysis.com
- The draft analysis comes from [AnalysisGNN](https://github.com/manoskary/analysisgnn) by Emmanouil Karystinaios, Johannes Hentschel, Markus Neuwirth and Gerhard Widmer, with our thanks.
