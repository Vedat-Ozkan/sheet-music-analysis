# Sheet Music Analysis

Harmonic analysis of sheet music, drawn on the engraved score, for music students and composers.

## Use it

Attach a MusicXML score (`.mxl` or `.musicxml`; MuseScore, Dorico, Sibelius and Finale can export one) and ask Claude to analyse a passage, for example "Analyse bars 1–8 and show me the annotated score". Claude returns the page as PNG and PDF with Roman numerals, chord functions, cadences, phrase brackets, non-chord tones and voice-leading arrows, plus a short commentary numbered to match the page.

Works with any Claude model; the analysis is most accurate with Claude Opus, since Claude checks and corrects the draft analysis itself (see below).

## How it works

The skill reads your attached file inside Claude's own sandbox and engraves the annotated page there. To get a neural model's draft analysis, Claude sends a compact list of the passage's notes to the Sheet Music Analysis connector; Claude then checks and corrects that draft before anything is drawn.

## Data

The score file stays in your conversation. The connector receives the notes of the passage (pitches and durations, no titles, lyrics or text) and returns the draft; it keeps nothing afterwards.
