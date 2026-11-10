# Sheet Music Analysis

Harmonic analysis of sheet music, drawn on the engraved score, for music students and composers.

## Use it

In Claude Code: `/plugin install sheet-music-analysis --marketplace Vedat-Ozkan/sheet-music-analysis`. On the web and in the desktop app, see https://sheetmusicanalysis.com/docs.html#install.

Add the plugin and the connector it lists on its Connectors tab. Then ask Claude to analyse a passage, for example "Analyse bars 1–8 of my score and show me the annotated page", and choose your score file in the card that appears: a MusicXML file (`.mxl` or `.musicxml`; MuseScore, Dorico, Sibelius and Finale can export one) or a PDF of printed music, up to 10 MB. Choosing it starts the analysis. Files attached to the chat cannot reach the connector, so if you attached one, choose the same file again in the card. You can also paste a link to the file instead (a direct link, or a Google Drive or Dropbox share link set so that anyone with the link can view it).

Claude returns the page with Roman numerals, chord functions, cadences, phrase brackets, non-chord tones and voice-leading arrows, with PNG and PDF downloads, plus a short commentary numbered to match the page. Ask for a whole piece and Claude analyses it passage by passage, then returns it as one PDF. A PDF is read first (up to the first 8 pages of a PDF of at most 12, about a minute or two); Claude shows you what was read, then goes straight on to the analysis. Ask to hear the music and a small piano player appears in the chat.

Works with any Claude model; the analysis is most accurate with Claude Opus, since Claude makes the analysis itself from the notes (see below).

## How it works

The connector receives the file you choose in the card (or downloads it from your link), reads it, and returns the notes beat by beat. Claude analyses them, then the connector draws the analysis on the engraved page. Claude does not download, open or search for files itself, and nothing runs on your computer or in Claude's code sandbox.

## Data

The connector receives only the file you choose in the card, or downloads it from the link you give, and keeps the score and the pages it draws for 30 days, then deletes them. Privacy policy: https://sheetmusicanalysis.com/privacy.html

## More

- Website and how-to guide: https://sheetmusicanalysis.com
- Support: support@sheetmusicanalysis.com
