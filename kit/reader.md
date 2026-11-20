# Read one page of scanned music into the N1 note format

You are given an image of one page of printed music. Look at the page first: count the staves in a system (a system is the group of staves joined at the left edge and played together) and see what each one is, for example two staves for piano, or a voice staff with words under it above two piano staves. Staves are numbered from the top of each system: the top staff is staff 1. Read every note from the image and write the music in the N1 text format described below. Accuracy matters more than speed: your output is compared note by note, and mark by mark, with a reference.

Rules of the task:
- Work only from the image. Do not search for the piece, do not read any file other than the ones named in your task, and do not rely on memory of the music: write what is printed.
- Go one system at a time, one bar at a time, one staff at a time. For every note, find its line or space against the clef, then apply the key signature and any accidental earlier in the same bar.
- Count the bars in each system by its bar lines, and transcribe every bar. Number bars 1, 2, 3 … in order across the systems of your page, whatever the page's number in the piece. If the piece opens on your page with a pickup (an incomplete first bar), call it m0.
- Ignore dynamics, fingering numbers and pedal marks. Do read ties, grace notes, rests, clef changes (they change which pitch a position means) and changes of key or time signature. Also read slurs, staccato dots and accents, and the words printed under a sung staff.
- If something is unreadable, write your best reading; do not leave a bar out.

## The N1 format

First line: `N1 div=D ts=N/M ks=K`
- `div` is the number of units in a quarter note. Choose it so every duration in the music is a whole number: 4 lets you write sixteenths (1 unit), 12 also allows eighth and sixteenth triplets, 24 or 48 for finer values.
- `ts` is the time signature at the start, for example `ts=3/4`.
- `ks` is the key signature at the start: `0` for none, `3s` for three sharps, `2f` for two flats.

Then, for each bar, one bar line followed by one line per voice:
- Bar line: `m5 len=L`, where L is the bar's length in units (a 3/4 bar with div=12 has len=36). Add `ts=6/8` or `ks=2s` on the bar line where the time or key signature changes.
- Voice line: `staff.voice: tokens`, for example `1.1:` for staff 1 voice 1 and `2.1:` for staff 2 voice 1. If a staff has two independent voices in a bar (stems up and stems down with different rhythms), write them as `1.1:` and `1.2:`.
- Tokens: a number sets the duration, in units, of every token after it until the next number. A pitch is a letter, an optional `#` or `b` (or `##`, `bb`) and an octave, where middle C is `C4`: `F#4`, `Bb3`. Always write the sounding pitch, with the key signature and bar accidentals already applied. Notes sounding together in one voice are joined with `+`: `C4+E4+G4`. `r` is a rest of the current duration. `~` after a pitch ties it to the same pitch in the next note: `E4~`. A grace note is written with `g` before the pitch (`gA4`), or `u` if its stem is slashed (`uA4`); it takes no time and needs no duration.
- Clefs: at the start of each staff's first bar on your page write its clef as `clef=G` (treble), `clef=F` (bass), `clef=C` (alto), `clef=T` (tenor) or `clef=G8` (treble sounding an octave lower), as the first entry of that staff's first voice line. Wherever a new clef is printed inside a staff, write it again at that point, before the first note it applies to: `2.1: 4 C3 E3 clef=G 4 C5 E5`.
- Slurs: write `(` directly before the first note of a slur and `)` directly after its last note: `4 (C4 D4 E4)`. On a chord the bracket goes around the whole chord token: `(C4+E4`. A slur may end in a later bar or system; write its `)` in the same voice it started in. If a slur runs on past the end of your page, close it after your last note under it; if a slur comes in from the page before, open it before your first note under it. Do not write a tie as a slur.
- Staccato and accent: `.` after a note with a staccato dot, `>` after a note with an accent sign: `C4.`, `C4+E4>`, and after the tie sign if there is one: `E4~>`. A slur's `)` comes last: `E4.)`.
- Words: directly under a voice line that has words printed under it, write one line `1.1w:` with one entry for every note of that voice line that is sung: every note token except rests, grace notes and a note that only continues a tie. Write the syllable printed under the note as printed, with a `-` at its end when the word goes on (`Kin- der`), and `_` when no syllable is printed under the note. Write no words line for a voice without words.
- Every voice line must fill its bar exactly: its durations, rests included, must add up to `len`. Check this for every line before moving on.
- A dotted note is written by its full length (a dotted quarter with div=12 is 18). A triplet eighth with div=12 is 4.
- If the printed values of a beamed group do not fit the beat it stands in (for example four eighths, or eight sixteenths, where only three eighths fit), the group is a tuplet, even when no number is printed over it. Spread its notes evenly over that beat, and choose `div` so that each is a whole number. Do not shorten or lengthen other notes to make the bar add up.

Example (a different piece; a pickup bar, grace notes, chords, rests):

```
N1 div=4 ts=3/4 ks=2s
m0 len=4
1.1: clef=G 4 (D4+F#4
2.1: clef=F 4 D3+A3.
m1 len=12
1.1: gB4 gA4 2 C#4+G4) 1 r C#4+F#4> 4 (C#4+G4 C#4+B4
2.1: 2 E3+A3 1 r D#3+A3 4 E3+A3 G3+A3
m2 len=12
1.1: 8 D4+A4) 4 A4+D5.
2.1: 2 F#3+A3 1 r E#3+A3 4 F#3+A3 F#3+A3
```

A voice line with words (another piece):

```
1.1: 4 G4 2 A4 B4 4 (C5 B4) 8 A4~
1.1w: Nun ru- hen al- _ le
```

## Working method (required)

A measuring tool, `notetool.py`, is in the `kit` folder next to this file. Read `kit/tool.md` first and follow its steps in order. Do not write your own image code: use only the tool's commands (run them with Python 3). Put the tool's output (overview, crops, zooms) in a folder of your own for your page, so that readers of other pages do not overwrite it.

## Your files

You were given the image of your page, its page number, the number of pages in the piece, and where to write your result. You may also have been given what an automatic reader found for the time signature and the key signatures. That reader is often wrong on scans, so do not copy it: count the signs printed at the start of your first system and at every change of key. If your count differs from the automatic reader's, zoom in on that key signature and count again, sign by sign, before you go on.

On a page after the first, the time signature is usually not printed again. Use the one you were given unless your page prints another; if you were given none, or the bars plainly do not fit it, work it out from the bars. Write only what is printed on your page. If the page begins or ends in the middle of a bar, write that bar as far as it is printed. Read only your page image, the `kit` folder, and images the tool makes from your page; do not read the other pages, and do not use web search.

## What to deliver

Write the complete transcription, in N1 only (no commentary inside the file), to the file you were told to write. If your page has no music on it at all (a title page, a page of text), write only the two words `NO MUSIC` to that file and say so in your reply. Then reply with: whether the tool's staves and bar lines were right, the number of bars you wrote per system, and a short list of the spots you were least sure of. Before you reply, run the tool's `check` on your file one last time and fix what it reports.
