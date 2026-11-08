# Sheet Music Analysis

Harmonic analysis of sheet music, drawn on the engraved score, for music students and composers.

## Use it

Add the plugin and the connector it lists on its Connectors tab. Then paste a link to your score in the chat and ask Claude to analyse a passage, for example "Analyse bars 1–8 of https://… and show me the annotated score". The link can go straight to a MusicXML file (`.mxl` or `.musicxml`; MuseScore, Dorico, Sibelius and Finale can export one) or a PDF of printed music, or be a Google Drive or Dropbox share link set so that anyone with the link can view it. Files attached to the chat cannot reach the connector, so share the file as a link. For a score on IMSLP, download the PDF in your browser and share it from Google Drive or Dropbox.

Claude returns the page with Roman numerals, chord functions, cadences, phrase brackets, non-chord tones and voice-leading arrows, with PNG and PDF downloads, plus a short commentary numbered to match the page. Ask for a whole piece and Claude analyses it passage by passage, then returns it as one PDF. A PDF is read first (up to the first 8 pages of a PDF of at most 12, about a minute or two); Claude shows you what was read and waits for you to check it. Ask to hear the music and a small piano player appears in the chat.

Works with any Claude model; the analysis is most accurate with Claude Opus, since Claude checks and corrects the draft analysis itself (see below).

## How it works

The connector downloads the file from your link, reads it, and returns the notes beat by beat with a draft analysis. Claude checks and corrects that draft, then the connector draws the analysis on the engraved page. Claude does not download, open or search for files itself, and nothing runs on your computer or in Claude's code sandbox.

## Data

The connector downloads the file only from the link you give, and keeps the score and the pages it draws for one day, then deletes them. Privacy policy: https://sheetmusicanalysis.com/privacy.html

## More

- Website and how-to guide: https://sheetmusicanalysis.com
- Support: support@sheetmusicanalysis.com
- The draft analysis comes from [AnalysisGNN](https://github.com/manoskary/analysisgnn) by Emmanouil Karystinaios, Johannes Hentschel, Markus Neuwirth and Gerhard Widmer, with our thanks.
