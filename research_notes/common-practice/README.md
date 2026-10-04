# How textbooks analyse common-practice harmony and form

Research of 2026-10-03, at the owner's suggestion, to base the skill's main method (Baroque to late Romantic) on how theory textbooks teach analysis rather than on general knowledge. As with the modal research (`research_notes/modal/`), the method comes from teaching sources, never from the published analyses the evaluation compares against.

## Source

*Open Music Theory*, version 2 (Gotham, Gullings, Hamm, Hughes, Jarvis, Lavengood, Peterson, 2023), [viva.pressbooks.pub/openmusictheory](https://viva.pressbooks.pub/openmusictheory/), CC BY-SA 4.0. It is a peer-reviewed open textbook used in university theory courses; its form chapters follow Caplin's *Classical Form* and its schema chapters Gjerdingen's *Music in the Galant Style*. Chapters read:

- Analysis procedure: "Performing Harmonic Analysis Using the Phrase Model" (Peterson); "Introduction to Harmony, Cadences, and Phrase Endings".
- Keys: "Tonicization" (Lavengood and Peterson); "Extended Tonicization and Modulation to Closely Related Keys" (Peterson); "Modal Mixture".
- Chords and dissonance: "Embellishing Tones"; "Cadential 6/4"; "6/4 Chords as Prolongations"; "Common-Tone Chords"; "Harmonic Elision"; "Altered and Extended Dominant Chords"; "Augmented Sixth Chords"; "Neapolitan"; "Neo-Riemannian Triadic Progressions".
- Patterns: "Diatonic Sequences"; "Chromatic Sequences"; "The Omnibus Progression"; "Galant Schemas"; "The Rule of the Octave".
- Form: "The Phrase, Archetypes, and Unique Forms" (Peterson); "Hybrid Phrase-Level Forms"; "Expansion and Contraction"; "Formal Sections in General" (Jarvis); "Sonata Form"; "Binary Form"; "Ternary Form"; "High Baroque Fugal Exposition".

The chapter texts are kept outside the repo (`out/research/common-practice/`).

## What the textbook teaches that our method lacked

**Analyse from the cadence backwards.** The textbook's procedure: (1) find the phrase endings, by listening for a new beginning; (2) label each cadence and analyse its harmony (sol in the bass at a half cadence, sol–do at an authentic cadence; watch for a cadential 6/4); (3) find the strong predominant before the cadential dominant (usually fa, sometimes re, in the bass); (4) only then go back to the start and work out how the tonic is prolonged. Our method starts at the first bar and works forward.

**Strict cadence criteria.**
- Authentic: V(7)–I *at the end of a phrase*. Perfect only when both chords are in root position and do is in the top voice; otherwise imperfect. Half: the phrase ends on V.
- "Not every pause or V–I motion is a cadence." A real cadence is followed by a sense of beginning (a new phrase, or the start of the last one again). If what follows repeats the middle of the phrase, the cadence was subverted.
- Phrases of two bars are rare unless the tempo is slow. Beginners mark too many cadences.
- A cadential 6/4 is part of V (V6/4–5/3), not a tonic chord.

**Tonicization, extended tonicization, modulation.** These sit on a spectrum. "Cadences establish keys": a modulation needs a cadence in the new key, and the clearest ones carry on in the new key afterwards. The same accidental returning again and again is the cue to look for one. Between the two lies extended tonicization: longer than an applied chord and its target, but without a cadence in the new key. Bracket it as a region of the new key rather than declaring a modulation. Two warning signs: writing x/ii, y/ii, z/ii over and over, and numerals that stop making sense in the home key while the coming cadence is still in it. Pivot chords are best when they are predominants in both keys and worst when they involve V.

**Chromatic notes.** Ask first whether the chromatic note is a chord tone or an embellishing tone. If it is a chord tone, the chord's quality decides the label: a major triad or dominant seventh is V(7)/x, a diminished triad or diminished seventh is viio(7)/x. Mixture changes a chord's quality, not its function (♭VI, iv in major). Common-tone diminished sevenths and common-tone augmented sixths decorate the chord they share a note with and have no function of their own. Harmonic elision replaces an expected chord with its dominant seventh or a diminished seventh.

**Six-four chords** come in four kinds, each with its own label: cadential (V6/4–5/3, sol in the bass, on the stronger beat), passing (bass passing tone between chords of the same function), neighbour (static bass, upper neighbours above, same chord on both sides), and arpeggiating (bass leaps through the fifth; usually not labelled).

**Embellishing tones** are nearly always the middle of a three-note figure whose outer notes are consonant with the bass: passing and neighbour notes (by step), appoggiatura (leap in, step out, usually on the beat) and escape tone (step in, leap out, off the beat), suspension and retardation (held over, resolving down or up, on the beat), pedal, and anticipation.

**Sequences.** A pattern repeated and transposed: descending fifths, descending thirds (Pachelbel), ascending 5–6, and their chromatic forms. Label the sequence and its pattern rather than giving every chord a new key; the applied chords inside a chromatic sequence do not make modulations.

**Phrase forms** (after Caplin): the sentence (presentation of a basic idea and its repetition, then a continuation with fragmentation, faster harmonic rhythm or sequence, driving to a cadence); the period (antecedent ending with a weaker cadence, usually HC; consequent with a stronger one, usually PAC); the repeated phrase; compound forms; and phrases that fit no archetype. Expansions lengthen a phrase from inside, and suffixes (post-cadential extensions, codettas) come after its cadence and are not new cadences.

**Late-Romantic triadic progressions** that confound Roman numerals (chains of third relations, common-tone motion) can be named by their transformations: relative, parallel, leading-tone exchange (R, P, L), rather than forced into one key.

**Baroque fugue.** Subject, answer (often tonally adjusted), countersubject, exposition, episodes (usually sequential). Keys of later entries are judged by cadences, as anywhere else.

## Proposed changes to the skill (not yet applied)

**Outcome (2026-10-03):** these changes were applied, tested on 15 pieces and made no measurable difference (docs/engineering-log.md, challenge 9), so they were removed at the owner's request.

To be made after the modal change has been measured, so each change gets its own before and after:

1. Reorder the method: phrase endings and cadences first, then the strong predominant, then the opening tonic.
2. Add the strict cadence criteria and the check for a new beginning after a cadence.
3. Replace the key rule with the tonicization–extended tonicization–modulation spectrum, including the region bracket for extended tonicization.
4. Add the chromatic-note procedure, the four six-four types and the common-tone chords.
5. Add sequences as a named pattern, labelled with a `region`.
6. Add the sentence and period vocabulary to the phrase step, and post-cadential suffixes.
7. For late-Romantic third relations, allow R, P, L names where no key fits.
