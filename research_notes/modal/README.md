# How textbooks analyse modal and impressionist music

Research of 2026-10-03, used to rewrite the skill's guidance for Debussy, Ravel and their contemporaries (`skill/SKILL.md`, "Modal and impressionist music, step by step") and to add the per-bar collection count to the note table (`engine/pitch_collections.py`).

The method was taken from general teaching sources, not from the published analyses the evaluation compares against, so that a better score means better analysis rather than an analysis fitted to the answer key.

## Sources

| Source | Licence | Used for |
|---|---|---|
| Gotham, "Analyzing with Modes, Scales, and Collections", *Open Music Theory* (2023), [viva.pressbooks.pub](https://viva.pressbooks.pub/openmusictheory/chapter/analyzing-with-collections-scales-and-modes/) | CC BY-SA 4.0 | Finding a mode: collection, then final; "first, last, loudest, longest"; chromatic notes inside a mode; changes of mode as modulation; hands taken together and apart |
| Gotham, Lavengood, Moseley, Shaffer, "Collections", *Open Music Theory*, [viva.pressbooks.pub](https://viva.pressbooks.pub/openmusictheory/chapter/collections/) | CC BY-SA 4.0 | The six collections and their properties (WT0/WT1, three octatonics, four hexatonics, acoustic) |
| Gotham and Hughes, "Pentatonic Harmony", *Open Music Theory*, [viva.pressbooks.pub](https://viva.pressbooks.pub/openmusictheory/chapter/pentatonic-harmony/) | CC BY-SA 4.0 | Separate the questions (tonic, chord roots, chord collection, overall collection), then combine; accept two readings when both fit |
| Rubin, "Nonfunctional Tonality", *Music Composition & Theory* (2024), [open.lib.umn.edu](https://open.lib.umn.edu/musiccomposition/chapter/nonfunctional-tonality/) | CC BY 4.0 | Planing; naming chords by root and quality instead of Roman numerals; non-chord tones still exist; a veiled tonic–dominant relation can remain |
| Hutchinson, "Impressionism", *Music Theory for the 21st-Century Classroom*, [LibreTexts](https://human.libretexts.org/Bookshelves/Music/Music_Theory/Music_Theory_for_the_21st-Century_Classroom_(Hutchinson)/32:_Impressionism_and_Extended_Tonality/32.01:_Impressionism) | GFDL 1.3 | Modes, extended chords, diatonic and chromatic planing |
| Acevedo and Rush, "Impressionism", *Music Theory 21c*, [tobyrush.com](https://tobyrush.com/book/text/twc/twc06.html) | CC BY-NC-SA 4.0 | Static harmony; added seconds, fourths and sixths as chord members |
| Uchida, *Tonal Ambiguity in Debussy's Piano Works*, MA thesis, University of Oregon (1990), [scholarsbank.uoregon.edu](https://scholarsbank.uoregon.edu/server/api/core/bitstreams/02c02733-9c18-4b3d-a80e-7b6f23990771/content) | thesis, quoted only | Its list of the factors behind tonal ambiguity (after Kostka's chapter layout), and its quotations of Mark DeVoto's *New Harvard Dictionary of Music* entries on "Tonality" and "Harmony" |

Kostka and Santa, *Materials and Techniques of Post-Tonal Music*, and Persichetti, *Twentieth-Century Harmony*, are the standard textbooks behind these chapters; they were not available to read here.

## What the sources agree on

- **Collection, then centre.** Gather the pitch content, find the collection, then decide the final from emphasis: first and last notes, longest and loudest, phrase beginnings and ends, metrically strong notes. A mode is a collection plus a final. Chromatic notes can sit inside a mode. (Gotham)
- **Changes of collection behave like modulations**, close or remote according to common tones and a shared final, and often line up with section boundaries. (Gotham)
- **What keeps a key in Debussy**, as DeVoto puts it: the tonic triad, progressions pointing to it ("especially by strong cadences"), "pedal points and ostinato basses", and "essential diatonicism". Pedal tones keep a centre in whole-tone and pentatonic passages; without them, "any note in a pentatonic scale can be heard as a tonal center". (DeVoto, quoted by Uchida)
- **How the dominant is weakened**: "by lowering the leading tone in the dominant chord, by adding unresolved nonharmonic tones, and by substituting other chords for the dominant in cadences". Chord types include "unresolved major ninths, elevenths, and thirteenths", and "unresolved or simultaneously resolved appoggiaturas". (DeVoto)
- **Name chords by root and quality**: "in nonfunctional harmony we cannot usually apply the standard tonal analytical tool of Roman numeral notation" (Rubin). Added seconds, fourths and sixths and extended chords on any degree are chord members (Acevedo and Rush).
- **Planing** moves one sonority in parallel; exact (real or chromatic) planing leaves any one key, diatonic planing stays within it. (Rubin, Hutchinson)
- **Debussy never fully left tonality**: functional and V–I passages sit beside modal ones. (Uchida)
- **Two readings can both stand** (pentatonic or Aeolian, say); say which you favour and why. (Gotham and Hughes)

## What we changed

**Outcome (2026-10-03):** both changes below were tested and made no measurable difference (docs/engineering-log.md, challenges 8 and 9), so they were removed at the owner's request. The code is in this session's history only, not in the repository.

- `engine/pitch_collections.py` counts, bar by bar, the smallest collection that holds the notes, allowing one short stray note, and checks the staves separately when they fit no single collection together (polychords, bitonality). The note table now carries these lines.
- `skill/SKILL.md` gained six steps for modal and impressionist passages: collection first; centre; chords as sonorities (held extensions are chord tones, an appoggiatura must resolve); planing; dominants and cadences (V only when it resolves, modal cadences by name); and keeping the tonal reading where the music is still tonal.
