# Reading notes with notetool.py

The tool measures; you look and write. Do not write your own image code. Follow the steps in order, one image at a time.

## 1. Layout

    python3 kit/notetool.py layout IMAGE overview.png

View `overview.png`. Staves are traced in blue and named SYSTEM.STAFF (`2.1` is the top staff of system 2). The bar lines the tool found are red, and each box between them has a red number.

- Check that every staff is traced and that every printed bar line is red. The tool misses bar lines and can take a stem for one, so a box is not always one bar: it can hold two or more. Count the bars of each system in the picture, by the printed bar lines, and write every one of them, each with its own notes. Remember which box holds more than one.
- A box marked `wide?` (the printed list says so too) is much wider than most bars on the page. Look in the picture for bar lines inside it. A single bar can be long: count more than one only where you see a bar line.
- The tool numbers bars from 1 in every system, and its bar 1 starts at the left edge (clef and key signature included). Your own bar numbers run on across systems and images; a pickup is m0.
- Write down for each system: the clef of each staff, the key signature (count the sharps or flats), the time signature, and any clef that changes inside a staff, with the x where the new clef is printed.

## 2. Labels

    python3 kit/notetool.py label IMAGE crops --clefs G,F --change 2.2@1450=G,3.2@900=F

`--clefs` names the clef of each staff of a system from top to bottom: `G` treble, `F` bass, `C` alto, `T` tenor. For a clef with a small 8 or 15, give the plain clef: the labels name the printed line or space, and the 8 goes into the note list as its own sign (`clef=G_8`). `--change SYSTEM.STAFF@X=CLEF` switches a staff to another clef from that x on. A change stays in force in the following systems until the next change, as in print. The first printed line of each system shows the clefs used: compare them with the clef printed at the start of that system.

The tool writes enlarged crops (`crops/s1_1.png`, …) and prints, for each bar and staff, the filled note heads from left to right, for example `x1242 D4+D5 | x1356 E4?(touching)+E5`. Heads joined by `+` are at the same x (a chord, or two voices). `x` is the position in the original image. On the crops, faint blue lines mark the ledger positions.

View every crop. Read one bar at a time, one staff at a time, comparing the printed list with the crop.

If the tool prints `system N: SKIPPED`, it traced the wrong number of staves in that system and made no crops for it. Read that system from zooms: take the rows of its staves from the overview's rulers, and give `zoom` the clef of the staff you are reading.

## 3. What to trust

- A blue label is a measured line or space. Take its letter and octave as they are.
- A label is never more than the line or space. You add the key signature and accidentals yourself: with two sharps a label `F4` is written `F#4`.
- A blue label outside the staff was counted against the printed ledger lines and is as good as one inside.

## 4. What never to trust

- Red labels (`?` in the list). `off`: the head is not centred on a line or space. `ledger`: the ledger lines could not be counted. `touching`: heads touch, as in stacked chords and seconds; such heads can also be mislabelled, doubled or missing. Zoom on every one.
- Heads without a label. The tool does not label hollow heads (half and whole notes), grace notes, and now and then a filled head. Read them in a zoom. The first grace note of a group may be a chord.
- Labels on things that are not notes: clefs, key and time signatures, text. Ignore them.
- Accidentals, dots, ties, slurs, staccato dots, accents, words, chord symbols, rests, beams, flags, the triplet 3, clef changes: the tool sees none of these. Read them by eye, and zoom when a sign is small or crowded.
- A note printed between the staves is listed under the nearer staff, in that staff's clef.

## 5. Zoom

    python3 kit/notetool.py zoom IMAGE X0 X1 Y0 Y1 zoom.png --clef F

The four numbers are original image pixels: read them from the rulers on the crop (`x…` along the top, `y…` down the left). Keep the box small: one chord or a few notes, with the nearest staff lines inside. At the right edge the close-up names every staff line (green) and every ledger position (red, with a thin blue guide line across) of the nearest staff, in the clef you gave.

Rules that settle doubtful heads:

- Inside the staff, follow the printed line to its name: a head with a staff line through its middle is on that line; a head between two lines is in the space.
- Outside the staff, count the printed ledger lines, not the guides (printed ledger lines are often spaced a little wider). A head with a ledger line through its middle is on that line. A head sitting on top of its last ledger line (above the staff), or hanging under it (below the staff), is in the space beyond.
- Two heads on the same side of the stem that touch are a third apart. In a second, the lower head is left of the stem and the upper head is right of it.
- A hollow head is read like a filled one: find the line through its middle or the two lines that enclose it.
- If a whole stretch of labels makes no sense for the staff, look for a small clef printed inside the staff and run `label` again with `--change`.

## 6. Write and check

- Pitch: label, then key signature (it applies in every octave), then any accidental printed earlier in the same bar on the same line or space (it lasts to the bar line and only in that octave). A natural sign cancels the key signature.
- Rhythm: read it from the crop (stems, flags, beams, dots, rests). With div=12: quarter 12, eighth 6, sixteenth 3, dotted quarter 18, triplet eighth 4. Each voice line must add up to the bar's `len`.
- A tie joins two heads of the same pitch and is written `~`. An arc between different pitches is a slur: `(` before its first note and `)` after its last.
- When a bar looks like an earlier bar, still read it, then compare the two.

After every system:

    python3 kit/notetool.py check YOUR_FILE

The check uses the same rules as the server that builds the score from your file. Each error says where it is and what to fix; fix every one.

- `adds up to`: the voice does not fill its bar. Read the rhythm again. Never change `len` to make it fit.
- `NOTE len=…`: allowed only for a pickup bar, the two parts of a bar that a repeat sign splits, and a bar that the page turn splits (at the end or the start of your page).
- `departs from the key signature`: point to the printed accidental for each one (on the note or earlier in the bar). Each staff is compared with its own key signature, the one its latest `t:` line gives or else `ks=`. If there is no accidental, the pitch is wrong, or the staff prints another key signature and needs its `t:` line (reader.md).
- `entries for … sung notes`: the words line does not have one entry for each sung note of its voice. Count again.
- `cannot be written as one note`: no single printed note has that length. Read the note value again; a note held across a beat is written as tied notes.
