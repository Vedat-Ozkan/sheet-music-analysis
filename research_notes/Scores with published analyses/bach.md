# J. S. Bach: popular pieces with a published human analysis AND a free MusicXML score

Research date: 2 October 2026. Method: every analysis page listed as "opened" was fetched and read in full (HTML text, PDFs, and a sample of the annotated score images). Every score file listed as "confirmed" was downloaded with curl, checked for zip/XML type, unzipped where needed, and parsed (part count, measure count, key, time signature, embedded credits and rights). Quotes are verbatim from the fetched pages; figured-bass superscripts are flattened to plain text (for example "V65").

Short names used below:
- **Bruhn** = Siglind Bruhn, *J. S. Bach's Well-Tempered Clavier: In-depth Analysis and Interpretation* (Edition Gorz, 2014), free chapter PDFs on the publisher's site.
- **teoria** = articles by José Rodríguez Alvira on teoria.com.
- **Puget Sound** = Robert Hutchinson, *Music Theory for the 21st-Century Classroom* (University of Puget Sound).
- **Harmonic Circuit** = blog of Alexander Martin, Assistant Professor of Music Theory, Stetson University.
- **WiR** = the When in Rome corpus (MarkGotham/When-in-Rome on GitHub).

---

## Key Question 1: Which popular Bach pieces have a thorough human-written analysis available?

### Takeaway
Eight candidates have a usable pairing; the well-covered ones are the two opening pairs of the Well-Tempered Clavier Book I (BWV 846 and 847, prelude and fugue each), the chorale "Aus meines Herzens Grunde" (BWV 269) and the Two-Part Invention No. 13 in A minor (BWV 784). The famous "audience favourites" outside the keyboard teaching repertoire (Goldberg Aria, Minuet in G, Air, Toccata and Fugue in D minor, Cello Suite No. 1 Prelude, BWV 999) turned out weak: either the analysis is thin, or the only free MusicXML is an arrangement or transposition.

### Cited Findings

Candidates with a thorough analysis (details in Key Question 2):

- **Prelude in C major, BWV 846 (WTC I no. 1).** Bruhn gives a four-section harmonic plan with bar numbers, Roman numerals for the cadential progressions, sequences, pedal points and a chord reduction graph of the whole prelude — [Bruhn WTC-01.pdf](https://edition-gorz.de/WTC-01.pdf). A second, independent teacher-style reading treats the piece as variations on ii–V–I with chord-by-chord score images — [teoria, "II, V, I variations in Bach's Prelude BWV 846"](https://www.teoria.com/en/articles/2017/BWV846/index.php). A third source gives a bare bar-by-bar Roman numeral label for all 35 bars — [WiR analysis.txt](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/Corpus/Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/01/analysis.txt).
- **Fugue in C minor, BWV 847 (WTC I no. 2).** Bruhn lists all eight subject entries, both countersubjects, six episodes with their motifs and inter-relations, key plan and a colour design diagram — [Bruhn WTC-02.pdf](https://edition-gorz.de/WTC-02.pdf). Puget Sound prints the whole fugue as annotated score figures marking expositions, episodes, bridge, countersubjects and fragmentation — [Puget Sound, Section 30.8 Fugue Analysis](https://musictheory.pugetsound.edu/mt21c/FugueAnalysis.html).
- **Prelude in C minor, BWV 847 (WTC I no. 2).** Bruhn gives the same style of harmonic plan as for BWV 846 (four sections, Roman numerals at cadences, sequences, dominant and tonic pedals, chord reduction graph) — [Bruhn WTC-02.pdf](https://edition-gorz.de/WTC-02.pdf). WiR supplies bar-by-bar labels — [WiR analysis.txt, Prelude No. 2](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/Corpus/Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/02/analysis.txt).
- **Fugue in C major, BWV 846 (WTC I no. 1).** Bruhn lists all 24 subject statements with bar and voice, the stretto pairs, the two tiny episodes, the cadences and the key plan — [Bruhn WTC-01.pdf](https://edition-gorz.de/WTC-01.pdf). A second analysis with score examples exists on teoria — [teoria, Fugue BWV 846](https://www.teoria.com/en/articles/BWV846/index.php). A third, list-style entry table exists on Tonic Chord — [tonic-chord.com BWV 846](https://tonic-chord.com/bach-prelude-and-fugue-no-1-in-c-major-bwv-846-analysis/).
- **Chorale "Aus meines Herzens Grunde", BWV 269 (Riemenschneider no. 1).** A music theory professor's phrase-by-phrase commentary with a fully annotated score: Roman numeral under every chord, boxed cadence labels, labelled non-chord tones, bar numbers — [Harmonic Circuit, "1. Aus meines Herzens Grunde"](https://alexandermartinblog.wordpress.com/2017/07/17/1-aus-meines-herzens-grunde/). A separate human Roman numeral label file exists for the same chorale — [music21 riemenschneider001.rntxt](https://raw.githubusercontent.com/cuthbertLab/music21/master/music21/corpus/bach/choraleAnalyses/riemenschneider001.rntxt).
- **Two-Part Invention No. 13 in A minor, BWV 784.** Section-by-section analysis (subject entries, episodes, modulations) with Roman numerals and key areas printed under the score — [teoria, Invention No. 13](https://www.teoria.com/en/articles/2020/bach-inventio/13/index.php).
- **Two-Part Invention No. 1 in C major, BWV 772.** Complete motivic and contrapuntal analysis (inversion, augmentation, invertible counterpoint, sequences, key plan) in seven short pages — [teoria, Invention BWV 772](https://www.teoria.com/en/articles/BWV772/index.php).
- **Two-Part Invention No. 8 in F major, BWV 779.** Canon-based structural analysis on teoria — [teoria, Invention No. 8](https://www.teoria.com/en/articles/2020/bach-inventio/08/index.php); plus a pianist's colour-highlighted pattern analysis — [Bindman, Invention 8 analysis PDF](https://eleonorbindman.com/assets/uploads/2023/03/Invention-8-analysis.pdf).

teoria holds further Bach analyses that could serve as extra candidates: fugues BWV 850, 851, 861, 871; all fifteen Inventions; lute works BWV 995–1000 and 1006a; French Suite No. 2; Brandenburg Concertos — [teoria articles index (XML)](https://www.teoria.com/res/xml/articles/index.xml). Bruhn covers all 48 preludes and fugues of both WTC books — [Bruhn, table of contents](http://edition-gorz.de/bruhn4-en-z.html).

Candidates that turned out weak:

- **Cello Suite No. 1 Prelude, BWV 1007.** The best free page is a guitarist's blog post discussing a voice-leading reduction; the full annotated score is a paid download ("Purchase and download the complete analysis (D and G major) for $5.00") — [John Hall, BWV 1007 Prelude analysis](https://johnhallguitar.com/blog/blog/bach-cello-suite-1-bwv-1007-prelude-analysis). A pianist's page is descriptive only, with no Roman numerals — [Bindman, "Analyzing Bach's Prelude from Cello Suite No. 1"](https://eleonorbindman.com/practice-tips/analyzing-bachs-prelude-from-cello-suite-no-1/).
- **Prelude in C minor, BWV 999.** A single-page harmonic walk-through exists — [teoria, BWV 999](https://www.teoria.com/en/articles/2024/BWV999/index.php) — but the only MusicXML found is a D minor transposition (see Key Question 3).
- **Goldberg Variations, Aria, BWV 988.** The only analysis found that names phrases and cadences is an anonymous student post on a DePauw University class blog from 2005, about 350 words, with no bar numbers; a reader comment points out that it wrongly calls E minor the "parallel minor" — [DePauw "Form and Analysis" blog](http://depauwform.blogspot.com/2005/02/aria-from-js-bachs-goldberg-variations.html).
- **Chorales on "O Haupt voll Blut und Wunden" from the St Matthew Passion, BWV 244.** teoria compares three harmonisations phrase by phrase with Roman numerals, but transposes two of them: "To facilitate the comparison we have transported the first one to C major and the second one to A minor" — [teoria, "Chorale Harmonization in Bach's Saint Matthew Passion"](https://www.teoria.com/en/articles/2019/BWV244/index.php).
- **Minuet in G, BWV Anh. 114.** The free score files themselves credit the piece to Christian Petzold, not Bach ("Minuet in G Major / Christian Petzold / Notebooks for Anna Magdalena Bach") — [MuseTrainer file](https://raw.githubusercontent.com/musetrainer/library/master/scores/Bach_Minuet_in_G_Major_BWV_Anh._114.mxl).

Sources checked and rejected for this purpose:

- Luke Dahn's bach-chorales.com gives source, text, tune and collection data for each chorale, not harmonic analysis (the BWV 269 page has only "Original source", "Chorale Text", "Tune", "Appearance in Early Collections" and a note) — [bach-chorales.com BWV 269](https://www.bach-chorales.com/BWV0269.htm).
- Nils Vigeland's essay on "Aus meines Herzens Grunde" is a pitch-class-set tally of vertical sonorities ("I used Fortean PCS naming to make the tabulations"), not a teacher-style harmonic analysis — [Vigeland, "A Bach Harmonization"](https://www.nilsvigeland.com/writings/a-bach-harmonization).
- Tim Smith's Northern Arizona University WTC site: the address tried returned HTTP 404 — [www2.nau.edu/tas3/wtc/i02.html](https://www2.nau.edu/tas3/wtc/i02.html).

### Inferences
- The WTC Book I opening pairs are the safest choice because three independent human sources exist for each (Bruhn, teoria or Puget Sound, and WiR labels), so the tool's output can be compared with more than one reading.
- The chorale BWV 269 is the only candidate whose published analysis has the same shape as the tool's output (labels drawn on the score: numerals, cadences, non-chord tones).
- For fugues and inventions the published analyses are mainly about counterpoint (entries, episodes, motifs); they test phrase/form and key-area output more than chord-by-chord numerals.
- "Very popular with the general public" and "well analysed by teachers" overlap less than expected: the teaching repertoire (WTC, inventions, chorales) is well served, the concert favourites are not.

### Gaps
- No thorough free analysis was found for the Goldberg Aria, the Air from BWV 1068, "Jesu, Joy of Man's Desiring" (BWV 147) or the Toccata and Fugue in D minor (BWV 565). Only one or two searches were run for each, so better sources may exist.
- Two search hits for the Minuet in G were not opened and are unverified: an academia.edu paper and a "songbirdmusicacademy.com" page (authorship and whether human-written unknown).
- Allen Winold, *Bach's Cello Suites: Analyses and Explorations* (Indiana University Press, 2007; vol. 1 text with a chapter "The preludes", vol. 2 musical examples) is the standard book for BWV 1007, but page numbers could not be confirmed; the chapter list comes from a library catalogue search snippet only.
- Public-domain Prout, Iliffe and Riemann WTC analyses on IMSLP/archive.org were not opened. The Tonic Chord pages look like a reproduction of an older textbook, but the page names no source.
- Reginald Bain's University of South Carolina WTC page did not load (connection failed).

---

## Key Question 2: For each analysis — URL, author, date, depth, coverage, annotated images, quotes

### Takeaway
Bruhn's book chapters are the deepest source (about 12 pages per prelude-and-fugue pair, by a published music analyst, free PDF). The Harmonic Circuit chorale post and the teoria Invention 13 pages are the two with Roman numerals printed on the score. Puget Sound gives a whole-fugue annotated score for BWV 847. Everything else is supplementary or thin.

### Cited Findings

**A. Bruhn, WTC I/1 in C major (Prelude and Fugue BWV 846)** — opened, read in full (12 PDF pages)
- URL: [https://edition-gorz.de/WTC-01.pdf](https://edition-gorz.de/WTC-01.pdf) (170 KB PDF; book pages 49–60: prelude pp. 49–52, fugue pp. 52–60).
- Book: Siglind Bruhn, *J. S. Bach's Well-Tempered Clavier: In-depth Analysis and Interpretation*, 580 pages, 2014, ISBN 978-3-938095-19-5, "ca. 180 music examples, 50 color diagrams" — [Edition Gorz order page](http://edition-gorz.de/order-bru4-engl.html). The publisher offers the chapters to "read online" — [Edition Gorz book page](http://edition-gorz.de/bruhn4a-engl.html).
- Author credentials: "a music analyst, concert pianist, and interdisciplinary researcher", Ph.D. University of Vienna, "From 1993 to 2018 she was a full-time research associate at the University of Michigan's Institute for the Humanities", "author of more than 40 book-length monographs" — [Edition Gorz author page](http://edition-gorz.de/bruhn0-c.html).
- Prelude coverage: four sections with bar ranges; Roman numerals for the cadences; sequences; transposed passage; diminished sevenths; dominant and tonic pedals; a two-system chord reduction of the entire prelude with sequence brackets and tension hairpins. Also performance advice (dynamics, tempo, ornament) that is irrelevant to the tool.
- Prelude does not cover: a Roman numeral for every single bar (bars 5–8, 12–14 and 20–23 are described by chord quality and function, not all by numeral); non-chord tones (the piece is pure arpeggiation).
- Quotes (prelude):
  - "The first cadential closure is reached in m. 4, the steps leading to it being: m. 1 = I, m. 2 = ii2, m. 3 = V65, m. 4 = I."
  - "mm. 15-19 are an exact transposition of mm. 7-11 (see the progression I6, IV2, ii7, V7, I in mm. 7-11 in G major, in mm. 15-19 in C major)."
  - "The emergence of the dominant pedal in m. 24 serves to divide it into two subsections. The first of these subsections, from m. 20 to the downbeat of m. 24, ends in an imperfect cadence."
- Fugue coverage: subject length and harmonisation (with a harmonised example), table of 24 entries by bar and voice, stretto pairs, episodes, cadences in A minor (mm. 13–14), D (m. 19) and C (mm. 23–24), tonic pedal coda, colour bar-chart of entries across all 27 bars.
- Quotes (fugue):
  - "The C-major fugue does not feature any counter-subject."
  - "Only twice is the density of the material in this fugue briefly interrupted. As the subject is absent in these measures, they qualify as episodes: E 1 = m. 13 (last three eighth-notes) to m. 14 (first eighth-note), E 2 = m. 23 (after the first 16th-note) to m. 24 (first eighth-note)."
  - "The harmonic progression within this fugue leads first from C major to its relative A minor, confirmed by the cadential close of mm. 13-14."

**B. Bruhn, WTC I/2 in C minor (Prelude and Fugue BWV 847)** — opened, read in full (12 PDF pages)
- URL: [https://edition-gorz.de/WTC-02.pdf](https://edition-gorz.de/WTC-02.pdf) (289 KB PDF; book pages 61–72: prelude pp. 61–66, fugue pp. 66–72). Same book and author as A.
- Prelude coverage: four sections (mm. 1–4, 5–14, 15–18, 18–38), Roman numerals at cadences, sequence, V7/iv, dominant pedal from m. 21, Presto imitation, tonic pedal from m. 34, chord reduction graph of the whole prelude. Much tempo and dynamics advice.
- Quotes (prelude):
  - "The first harmonic progression ends in m. 4, the steps being: m. 1 = i, m. 2 = iv64, m. 3 = vii + C pedal, m. 4 = i."
  - "The final steps of the cadence in this new key are: m. 10 = V2, m. 11 = I64, m. 12 = IV6, m. 13 = V65, m. 14 = I."
  - "The bass-note transition from C to B♭ converts the tonic chord into an inverted V7/iv (dominant-seventh of the subdominant) and thus triggers a new, active harmonic motion. This leads very soon (m. 21) to a dominant pedal."
- Fugue coverage: subject (with harmonisation i–iv–i6–V9–i printed under it), tonal answer, eight entries by bar and voice, two countersubjects, six episodes with motifs M1/M2 and which episode varies which, cadential close mm. 28–29, coda over tonic pedal, key plan, colour design diagram of all 31 bars.
- Fugue does not cover: chord-by-chord Roman numerals through the episodes; individual non-chord tones.
- Quotes (fugue):
  - "There are altogether eight subject statements in this fugue: 1. mm. 1-3 M … 2. mm. 3-5 U … 3. mm. 7-9 L … 4. mm. 11-13 U … 5. mm. 15-17 M … 6. mm. 20-22 U … 7. mm. 26-28 L … 8. mm. 29-31 U" (M, U, L = middle, upper, lower voice).
  - "It features two counter-subjects, only the first of which is truly independent."
  - "The harmonic progression in this fugue leads from C minor to the relative major key, E♭ major (in the fourth subject entry), but returns to the home key very soon thereafter and never leaves it again."

**C. teoria, "II, V, I variations in Bach's Prelude BWV 846"** — opened, all 10 sub-pages read; one score image viewed
- URL: [https://www.teoria.com/en/articles/2017/BWV846/index.php](https://www.teoria.com/en/articles/2017/BWV846/index.php). Author José Rodríguez Alvira; "© 2017 José Rodríguez Alvira. Published by teoria.com".
- Length: 10 short pages, roughly 900 words in total, about 45 small score images, plus a summary page [Table of variations](https://www.teoria.com/en/articles/2017/BWV846/variations.php) with 27 chord images named by numeral (image file names include "ii42", "V65", "vi6", "V42-V").
- Covers: bars 1–23 chord by chord as five "variations" of ii–V–I, then the dominant pedal (m. 24) and tonic pedal (m. 32). Does not cover: cadence types, bars 24–35 chord by chord.
- Quotes:
  - "Bach's Prelude BWV 846 from the first book of The Well-Tempered Clavier seems to be a set of variations of this progression."
  - "The ii degree chord in measure 2: Is now a secondary dominant of the V degree in third inversion" — [first variation page](https://www.teoria.com/en/articles/2017/BWV846/01.php)
  - "A dominant pedal starting in measure 24 will lead to the climax. Finally, in measure 32 Bach presents the last variation of the ii-V-I progression over a tonic pedal" — [last measures page](https://www.teoria.com/en/articles/2017/BWV846/final.php)

**D. WiR Roman numeral labels, WTC I preludes** (supplement, bare labels)
- BWV 846: header reads "Analyst: Mark Gotham, manually, through judicious automation, and in collaboration with colleagues and students"; one label per bar, for example "m1 C: I / m2 ii2 / m3 V65 / m4 I / m5 vi6 / m6 G: V2", pedals marked "Pedal: G m24 m32 b1" — [WiR analysis.txt no. 1](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/Corpus/Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/01/analysis.txt).
- BWV 847 prelude: same analyst line, adding "at Cornell University" — [WiR analysis.txt no. 2](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/Corpus/Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/02/analysis.txt).
- The corpus README describes this set as "Complete preludes from the first book of Bach's Well Tempered Clavier (24 analyses)" — [WiR README](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/README.md). Each folder also holds an `analysis_automatic.rntxt`, which is machine output and must not be used as the human reference — [WiR repository](https://github.com/MarkGotham/When-in-Rome).

**E. Puget Sound, Section 30.8 "Fugue Analysis" (BWV 847 fugue)** — opened, text read in full; figures downloaded but not rendered
- URL: [https://musictheory.pugetsound.edu/mt21c/FugueAnalysis.html](https://musictheory.pugetsound.edu/mt21c/FugueAnalysis.html). Author Robert Hutchinson, University of Puget Sound; edition dated March 30, 2026 — [front matter](https://musictheory.pugetsound.edu/mt21c/frontmatter.html). "©2017 Robert Hutchinson", GNU Free Documentation License — [colophon](https://musictheory.pugetsound.edu/mt21c/colophon-1.html).
- Length: about 600 words of text plus four captioned figures made of 11 SVG score images (fug-c-min-A to K) that together print the whole fugue.
- Covers: definitions (exposition, subject, tonal/real answer, bridge, countersubject, episode), first exposition, each later exposition and episode, fragmentation of subject and both countersubjects. Does not cover: Roman numerals, cadences, key areas in the text.
- Quotes:
  - "“Countersubject 1” is in the alto voice in measure 3 and in the soprano voice in measure 7."
  - "In this fugue, there is motivic fragmentation of the subject, countersubject 1, and countersubject 2."
  - "In the four systems below, we see the fourth exposition, fourth episode, and final exposition, which includes two subject statements separated by cadential material."

**F. teoria on the BWV 847 fugue** (supplement; video only)
- The article page contains only an MP4 video with on-screen analysis, "©2011 José Rodríguez Alvira" — [teoria BWV 847](https://www.teoria.com/en/articles/BWV847/index.php). This counts as a video fallback.
- A tutorial page gives a structure table ("Exposition measures 1 - 10, Episode 10 - 11, Presentation 12 - 14, Episode 14 - 15, Presentation 16 - 18, Episode 18 - 20, Presentation 21 - 23, Episode 23 - 27, Presentation 27 - 32") and says the first episode "is about 2 measures and leads us to the relative major key of Eb major" — [teoria, "After the Exposition"](https://www.teoria.com/en/tutorials/forms/contrapuntal/05-episodes.php).
- Conflict: these bar numbers run to 32 and place entries one bar later than Bruhn, who gives entries at mm. 1-3, 3-5, 7-9, 11-13, 15-17, 20-22, 26-28, 29-31 in a 31-bar fugue — [Bruhn WTC-02.pdf](https://edition-gorz.de/WTC-02.pdf). The MusicXML files have 31 measures (Key Question 3), matching Bruhn.

**G. Harmonic Circuit, "1. Aus meines Herzens Grunde" (BWV 269)** — opened, text read in full; top half of the annotated score image viewed (bars 1–14)
- URL: [https://alexandermartinblog.wordpress.com/2017/07/17/1-aus-meines-herzens-grunde/](https://alexandermartinblog.wordpress.com/2017/07/17/1-aus-meines-herzens-grunde/). Dated July 17, 2017.
- Author: "My name is Alexander Martin. I am Assistant Professor of Music Theory at Stetson University." — [Harmonic Circuit, About](https://alexandermartinblog.wordpress.com/about/).
- Length: about 700 words in six phrase sections (mm. 1–4, 5–7, 8–10, 11–14, 15–18, 19–21) plus one full-page annotated score — [score image, 2224×2765 px](https://alexandermartinblog.files.wordpress.com/2017/07/1-aus-meines-herzens-grunde1.png).
- The annotated score shows, as seen in bars 1–14: key label "G:", a Roman numeral under every chord (I, IV6, V6, VI, VII6, II65, V8–7 …), boxed cadence labels above the fermatas ("I: HC", "I: PAC", "IV: IAC"), non-chord tone labels on the notes ("P", "N", "sus.", "ret."), and bar numbers.
- Covers: chord-by-chord harmony, cadences, phrases, non-chord tones, voice leading (with Schenkerian terms such as Urlinie and Kopfton). Does not cover: nothing major missing for a 21-bar chorale; no modulation beyond the tonicised IV.
- Notation difference to note: all numerals are upper case (VI, II65, VII6) in Schenkerian style, not case-coded for chord quality.
- Quotes:
  - "The harmonic framework for this is I—II6/5—V—I, or T—PD—D—T in functional terms."
  - "There's an unusual cadential 6/3 in m. 12."
  - "The arrival on the I in m. 13 sounds like it should be a I: IAC, but Bach destabilizes the would-be-tonic by adding a flattened seventh."
- The same blog analyses Riemenschneider chorales 1–8 in the same way (for example no. 6 "Christus, der ist mein Leben", no. 5 "An Wasserflüssen Babylon") — [Harmonic Circuit, Chorale Analyses category](https://alexandermartinblog.wordpress.com/category/chorale-analyses/).
- Supplement, bare labels: music21 ships a RomanText file for the same chorale: "BWV: 269 / Title: Aus meines Herzens Grunde / Analyst: Andrew Jones / Proofreader: Dmitri Tymoczko and Hamish Robb", with beat-level labels such as "m3 IV b2.5 viio6 b3 I" — [riemenschneider001.rntxt](https://raw.githubusercontent.com/cuthbertLab/music21/master/music21/corpus/bach/choraleAnalyses/riemenschneider001.rntxt).

**H. teoria, Invention No. 13 in A minor, BWV 784** — opened, all 7 sub-pages read; one of six score images viewed (bars 8–13)
- URL: [https://www.teoria.com/en/articles/2020/bach-inventio/13/index.php](https://www.teoria.com/en/articles/2020/bach-inventio/13/index.php). Author José Rodríguez Alvira, "© 2020"; the Inventions series is dated 2020-04-23 in the site index — [teoria articles index (XML)](https://www.teoria.com/res/xml/articles/index.xml).
- Length: text is very short (about 250 words over 5 section pages); the analysis lives in six annotated score images covering bars 1–3, 3–6, 6–8, 8–13, 13–18 and 18–25, that is the whole piece.
- The image viewed prints Roman numerals with key labels and a pivot under the score, for example "C major: I, vi / G major: ii, V65, I7, IV7" and "E minor: V43, i, iv7, VII, III7, VI, ii7, V7, i" — [score image bars 8–13](https://www.teoria.com/res/images/articles/bach-inventio/13/inventio_13_8_13.png).
- Covers: form (subject presentations and episodes with bar ranges), key areas and modulations, Roman numerals, Neapolitan sixth. Does not cover: cadence types, non-chord tones.
- Quotes:
  - "This episode modulates to E minor - dominant key of A minor - via G major" — [bars 8–18 page](https://www.teoria.com/en/articles/2020/bach-inventio/13/04.php)
  - "Once in E minor, a new episode will take us back to A minor using a series of diminished seventh chords" — same page
  - "Note the use of the Neapolitan sixth chords in measure 23" — [bars 18–25 page](https://www.teoria.com/en/articles/2020/bach-inventio/13/05.php)

**I. teoria, Invention No. 1 in C major, BWV 772** — opened, all 7 sub-pages read; one score image viewed (bars 3–6)
- URL: [https://www.teoria.com/en/articles/BWV772/index.php](https://www.teoria.com/en/articles/BWV772/index.php). "© 2015 José Rodríguez Alvira".
- Length: about 700 words, about 20 score images, two summary tables (techniques by bar; modulations).
- Covers the whole piece: subject, imitation, inversion, augmentation, invertible counterpoint, sequences, key plan (C, G, D minor, A minor, F, C). Does not cover: Roman numerals or cadences; the image viewed carries only numbered motive boxes, no harmonic labels.
- Quotes:
  - "In measures 3 and 4 Bach presents a sequence based on the subject" — [bars 3–6 page](https://www.teoria.com/en/articles/BWV772/03-06.php)
  - "Bach uses invertible counterpoint at the octave (what was played by the upper voice is now played by the lower voice and viceversa)." — [bars 7–8 page](https://www.teoria.com/en/articles/BWV772/07-08.php)
  - Technique table: "Inversion 3-4 ; 11-12 ; 13-14 ; 15-18 ; 19-20 / Augmentation 3-4 ; 11-12 ; 19-20" — [coda page](https://www.teoria.com/en/articles/BWV772/coda.php)

**J. Invention No. 8 in F major, BWV 779** — both sources opened and read in full
- teoria: four "canons" with bar ranges and keys ("First canon, Measures 1 to 12, From F major to C major … Final canon, Measures 26 to 34, From Bb major to F major"); "A diminished seventh chord in measure 15 modulates to G minor" — [teoria, Invention No. 8](https://www.teoria.com/en/articles/2020/bach-inventio/08/index.php) and [second canon page](https://www.teoria.com/en/articles/2020/bach-inventio/08/02.php). Whether its score images carry Roman numerals was not checked.
- Bindman (concert pianist and teacher): 1 page of text plus the full score with four colour-coded patterns; aimed at students "with minimal theory background"; no Roman numerals; cadences only located ("Measures 10-11 and the last 2 measures function as necessary cadences") — [Bindman PDF, 3 pages](https://eleonorbindman.com/assets/uploads/2023/03/Invention-8-analysis.pdf). This one is thin for our purpose.

**K. Other analyses of the BWV 846 fugue** (supplement)
- teoria: notes the entry order "subject - answer - answer - subject" and says "there are only 22 complete subjects. To be able to get to the total of 24 subjects you need to include two incomplete presentations" — [teoria, Fugue BWV 846](https://www.teoria.com/en/articles/BWV846/index.php). Only the index page was read.
- Tonic Chord (unsigned, dated May 5, 2018): bar-by-bar entry list with keys, for example "Bars 12-13: Subject in Tenor. Full Close in A minor"; summary "Exposition: Bars 1-6 / Counter-exposition: Bars 7-10. / Episodes: None. / Stretti: 6." Its prelude section is a three-period outline only ("Bars 1-11: Period I … Bars 11-19: Period II … Bars 20-35: Period III. In reality a long Coda"), which is thin — [tonic-chord.com BWV 846](https://tonic-chord.com/bach-prelude-and-fugue-no-1-in-c-major-bwv-846-analysis/).
- Conflicts between the three: Bruhn counts 24 statements, nine stretto combinations and two episodes; teoria counts 22 complete statements; Tonic Chord counts six stretti and no episodes — [Bruhn WTC-01.pdf](https://edition-gorz.de/WTC-01.pdf); [teoria](https://www.teoria.com/en/articles/BWV846/index.php); [tonic-chord.com](https://tonic-chord.com/bach-prelude-and-fugue-no-1-in-c-major-bwv-846-analysis/).

**L. Weak or partial analyses**
- Cello Suite No. 1 Prelude, John Hall (guitarist), 27 December 2013, about 450 words, describes a two-staff reduction "similar to what Heinrich Schenker would do", discussed in the D major guitar transposition: "The bass begins on the tonic (D) sustained as a pedal point through measure six"; "the underlying 7-6 suspensions over the A pedal point in measures 29-31"; "the tonic 6-4 chord (D/A) in measure thirty-nine is really still considered dominant". Only one sample image is free — [John Hall](https://johnhallguitar.com/blog/blog/bach-cello-suite-1-bwv-1007-prelude-analysis).
- Cello Suite No. 1 Prelude, DCML expert labels (bare labels): annotator Adrian Nagel, 42 measures, 54 labels, annotation standard 2.3.0 — [DCMLab/bach_solo README](https://github.com/DCMLab/bach_solo); label table with chord, cadence and phrase-end columns — [BWV1007_01_Prelude.harmonies.tsv](https://raw.githubusercontent.com/DCMLab/bach_solo/main/harmonies/BWV1007_01_Prelude.harmonies.tsv).
- BWV 999, teoria, dated 2024-10-26 in the site index, one page, about 250 words, Creative Commons BY-NC-ND 4.0: "We start with a tonic pedal point over which the chords i - iv - vii - i appear."; "A German augmented sixth leads to the G minor dominant with a minor ninth."; "The prelude finishes on the dominant." The score is shown through a script-driven synced player, which could not be viewed — [teoria BWV 999](https://www.teoria.com/en/articles/2024/BWV999/index.php); [index XML](https://www.teoria.com/res/xml/articles/index.xml).

### Inferences
- Bruhn plus WiR labels together give full chord-by-chord coverage for the two preludes: Bruhn explains structure and cadences, WiR fills in the numeral for every bar.
- The Harmonic Circuit chorale post can be compared with the tool's drawn output almost label for label; the upper-case numeral convention has to be normalised first.
- For BWV 847 fugue, use Bruhn's bar numbers as the reference; the teoria tutorial table appears to number bars differently and should not be used for bar-level checks.
- José Rodríguez Alvira's teoria pages are reliable but brief; they work best as a second opinion, except Invention 13 where the numerals are printed on the score.

### Gaps
- José Rodríguez Alvira's credentials are not stated on the pages fetched, so they are unverified here.
- Only one of the six Invention 13 score images, one BWV 772 image and the top half of the BWV 269 image were viewed; the rest are assumed to follow the same pattern.
- The 11 Puget Sound SVG figures downloaded correctly (76–132 KB each) but could not be rendered in this environment, so the labels drawn on them were not seen; their content is taken from the surrounding text.
- The original publication date of Bruhn's book before the 2014 Edition Gorz edition was not checked.
- The teoria "Música viva" animated analysis of BWV 772 and the BWV 847 video were not watched.

---

## Key Question 3: For each piece — MusicXML download URL, source, licence, download confirmed, instrumentation, completeness

### Takeaway
Every strong candidate has a MusicXML file that downloaded and parsed correctly, in original instrumentation and complete. Licences are clear for WiR (CC BY-SA 4.0) and ASAP (CC BY-NC-SA 4.0); the files for the BWV 847 fugue and the Inventions are MuseScore exports sitting in other people's GitHub repositories with no rights statement of their own. The cello suite has no MusicXML (MuseScore format only), and BWV 999 exists only transposed.

### Cited Findings

All rows below were downloaded on 2 October 2026 with HTTP 200 and parsed without error unless stated.

| Piece | Direct URL | Type and size | Content check | Licence / provenance |
|---|---|---|---|---|
| BWV 846 Prelude | [WiR …/01/score.mxl](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/Corpus/Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/01/score.mxl) | .mxl zip, 8,831 bytes | 1 part, 2 staves, 35 measures, 751 notes, 4/4, no sharps or flats; credits "Praeludium 1 / BWV 846 / Johann Sebastian Bach"; MuseScore 3.2.3, 2019 | Corpus content "CC BY-SA licence" 4.0 — [WiR README](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/README.md) |
| BWV 846 Prelude (alt.) | [ASAP Bach/Prelude/bwv_846/xml_score.musicxml](https://raw.githubusercontent.com/fosfrancesco/asap-dataset/master/Bach/Prelude/bwv_846/xml_score.musicxml) | uncompressed XML, 267,546 bytes | 35 measures, 751 notes; MuseScore 2.3.2, 2018 | "Creative Commons Attribution Non-Commercial Share-Alike 4.0" — [ASAP README](https://raw.githubusercontent.com/fosfrancesco/asap-dataset/master/README.md) |
| BWV 846 Prelude (alt., avoid) | [music21 bwv846.mxl](https://raw.githubusercontent.com/cuthbertLab/music21/master/music21/corpus/bach/bwv846.mxl); identical bytes at [MuseTrainer](https://raw.githubusercontent.com/musetrainer/library/master/scores/Prelude_I_in_C_major_BWV_846_-_Well_Tempered_Clavier_First_Book.mxl) | .mxl zip, 7,726 bytes | only 34 measure elements and 729 notes, against 35 measures in WiR, ASAP and Bruhn; source tag "http://musescore.com/score/117279", MuseScore 1.3, 2013 | no rights statement in file |
| BWV 846 Fugue | [ASAP Bach/Fugue/bwv_846/xml_score.musicxml](https://raw.githubusercontent.com/fosfrancesco/asap-dataset/master/Bach/Fugue/bwv_846/xml_score.musicxml) | uncompressed XML, 317,164 bytes | 1 part, 2 staves, 27 measures, 860 notes; credits "Fugue No. 1 in 4 voices in C Major / from “Das Wohltemperierte Klavier” Book I" | CC BY-NC-SA 4.0 (ASAP README, as above) |
| BWV 847 Prelude | [WiR …/02/score.mxl](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/Corpus/Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/02/score.mxl) | .mxl zip, 13,517 bytes | 1 part, 2 staves, 38 measures, 1,124 notes, 3 flats; credits "Praeludium 2 / BWV 847" | CC BY-SA 4.0 (WiR README) |
| BWV 847 Prelude (alt.) | [freedots scores/bwv847-p.xml](https://raw.githubusercontent.com/mlang/freedots/master/scores/bwv847-p.xml) | XML, 364,011 bytes | 38 measures, 1,132 notes; Sibelius 6.1 export, 2010 | file states "Creative Commons Attribution-ShareAlike 3.0" |
| BWV 847 Fugue | [EuterPen scores/BWV_847.xml](https://raw.githubusercontent.com/VincentCavez/EuterPen/main/scores/BWV_847.xml) | XML (MusicXML 4.0), 305,246 bytes | 1 part, 2 staves, 31 measures, 836 notes, 3 flats; credits "Fugue No. 2 in 3 voices in C Minor / from “Das Wohltemperierte Klavier” Book I / Johann Sebastian Bach"; MuseScore 4.2.0, 2024 | no rights statement in file; repository has no licence |
| BWV 847 Fugue (alt.) | [gong …/Fugue_No._2_BWV_847_in_C_Minor.musicxml](https://raw.githubusercontent.com/fullstack-lang/gong/main/app/xsd/tests/musicxml/Fugue_No._2_BWV_847_in_C_Minor.musicxml) | XML, 301,661 bytes | 31 measures, 836 notes; source tag "http://musescore.com/score/231261"; MuseScore 2.0.2, 2015 | no rights statement in file |
| BWV 847 Fugue (alt., voices on separate staves) | [sightread …/Bach_WTC_Fugue_2_in_Cm_BWV_847.xml](https://raw.githubusercontent.com/marycourtland/sightread/master/examples/Bach_WTC_Fugue_2_in_Cm_BWV_847.xml) | XML, 287,056 bytes | 3 parts, 31 measures each, 835 notes; MuseScore 1.0, 2012 | no rights statement; repository has no licence |
| BWV 847 Fugue (Humdrum, needs conversion) | [humdrum-tools wtc1f02.krn](https://raw.githubusercontent.com/humdrum-tools/bach-wtc-fugues/master/kern/wtc1f02.krn) | kern text, 6,151 bytes | header "The Well-Tempered Clavier, Book 1, Fugue 2 in C minor"; repository describes "each part on their own staff" — [repo](https://github.com/humdrum-tools/bach-wtc-fugues) | not MusicXML; conversion not tested |
| BWV 269 chorale | [music21 bwv269.mxl](https://raw.githubusercontent.com/cuthbertLab/music21/master/music21/corpus/bach/bwv269.mxl) | .mxl zip, 4,863 bytes | 4 parts (Soprano, Alto, Tenor, Bass), 24 measure elements with last measure number 21, 229 notes, 3/4, 1 sharp; credits "PDF © 2004 Margaret Greentree / BWV 269" | music21 corpus notice: works are "either out of copyright in the United States or is licensed for use, though there may be restrictions on commercial use" — [corpus/license.txt](https://raw.githubusercontent.com/cuthbertLab/music21/master/music21/corpus/license.txt) |
| Invention 13, BWV 784 | [webern/mx …/Invention_13.xml](https://raw.githubusercontent.com/webern/mx/main/data/foundsuite/Invention_13.xml) | XML, 238,074 bytes | 1 part, 2 staves, 25 measures, 593 notes, 4/4, no key signature accidentals; title "Invention 13", composer "J. S. Bach (1685 - 1750)"; MuseScore 2.0.2, 2015 | no rights statement in file; repository code is MIT — [webern/mx](https://github.com/webern/mx) |
| Invention 1, BWV 772 | [webern/mx …/Invention 1.xml](https://raw.githubusercontent.com/webern/mx/main/data/foundsuite/Invention%201.xml) | XML, 197,175 bytes | 1 part, 2 staves, 22 measures, 487 notes; credits "Bach, J. S. / Invention No. 1 / in C Major" | as above. Same music also at [musii-kit](https://raw.githubusercontent.com/otsob/musii-kit/main/examples/data/bach_invention_1.musicxml) and [vexflow-musicxml](https://raw.githubusercontent.com/lasconic/vexflow-musicxml/master/docs/samples/bach_bwv772.xml) (both 22 measures, 487 notes) |
| Invention 8, BWV 779 | [webern/mx …/Invention_8.xml](https://raw.githubusercontent.com/webern/mx/main/data/foundsuite/Invention_8.xml) | XML, 241,193 bytes | 34 measures, 609 notes, 3/4, 1 flat | as above |
| Invention 4, BWV 775 | [webern/mx …/Invention_4.xml](https://raw.githubusercontent.com/webern/mx/main/data/foundsuite/Invention_4.xml) | XML, 192,479 bytes | 52 measures, 464 notes, 3/8, 1 flat | as above |
| St Matthew chorales BWV 244 | music21 [bwv244.15](https://raw.githubusercontent.com/cuthbertLab/music21/master/music21/corpus/bach/bwv244.15.mxl), [bwv244.54](https://raw.githubusercontent.com/cuthbertLab/music21/master/music21/corpus/bach/bwv244.54.mxl), [bwv244.62](https://raw.githubusercontent.com/cuthbertLab/music21/master/music21/corpus/bach/bwv244.62.mxl) | .mxl zips, about 4.5 KB each | 4 parts each; keys 4 sharps, 1 flat (minor), none (minor), matching the article's "E major", "D minor", "A minor" | music21 corpus notice as above |
| Goldberg Aria, BWV 988 | [freedots scores/bwv988-aria.xml](https://raw.githubusercontent.com/mlang/freedots/master/scores/bwv988-aria.xml) | XML (MusicXML 1.1), 170,066 bytes | 1 part, 2 staves, 32 measures, 500 notes, 3/4, 1 sharp; source "Mutopia Project" | file states "Creative Commons Attribution-ShareAlike 3.0" |
| BWV 999 (transposed, not usable) | [freedots scores/bwv999.xml](https://raw.githubusercontent.com/mlang/freedots/master/scores/bwv999.xml) | XML, 152,356 bytes | titled "Prelude in D Minor", 1 flat, single staff, 43 measures; made by "Neuratron PhotoScore" from "Scanned sheet music" | file states "Public Domain" |
| Minuet in G, BWV Anh. 114 (Petzold) | [MuseTrainer](https://musetrainer.github.io/library/scores/Bach_Minuet_in_G_Major_BWV_Anh._114.mxl) | .mxl zip, 4,745 bytes | 1 part, 2 staves, 32 measures, 209 notes, 3/4, 1 sharp | file states "Public Domain (PianoXML typeset)" |
| Air, BWV 1068 (arrangement) | [MuseTrainer](https://raw.githubusercontent.com/musetrainer/library/master/scores/J._S._Bach_-_Air_on_the_G_String_Piano_arrangement.mxl) | .mxl zip, 7,965 bytes | piano arrangement, 37 measures, 1 sharp (the file name says "Piano arrangement") | no rights statement |
| Toccata and Fugue in D minor (arrangement) | [MuseTrainer](https://raw.githubusercontent.com/musetrainer/library/master/scores/Bach_Toccata_and_Fugue_in_D_Minor_Piano_solo.mxl) | .mxl zip, 66,697 bytes | piano solo, 143 measures; credit "Adp. from The H. W. Gray Co., Inc." | no rights statement |
| Cello Suite 1 Prelude (MuseScore format, needs conversion) | [DCMLab/bach_solo MS3/BWV1007_01_Prelude.mscx](https://raw.githubusercontent.com/DCMLab/bach_solo/main/MS3/BWV1007_01_Prelude.mscx) | .mscx XML, 187,014 bytes | MuseScore 3.6.2 file, 42 measures, annotator tag "Adrian Nagel"; includes the harmony labels | "Creative Commons Attribution-NonCommercial-ShareAlike 4.0" — [bach_solo README](https://github.com/DCMLab/bach_solo) |

Other notes on sources:
- WiR holds score.mxl plus analysis.txt for WTC I preludes; fugue folders seen in the file listing ("19_fugue", "22_fugue") contain only analysis.txt and remote.json, and there is no fugue folder for no. 1 or 2 — [WiR repository tree](https://github.com/MarkGotham/When-in-Rome/tree/master/Corpus/Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I).
- WiR chorale 001 has analysis.txt, analysis_BCMH.txt and remote.json but no local score file — [WiR Chorales/001](https://github.com/MarkGotham/When-in-Rome/tree/master/Corpus/Early_Choral/Bach,_Johann_Sebastian/Chorales/001).
- ASAP's Bach set has BWV 846 prelude and fugue but no BWV 847 — [ASAP repository, Bach folder](https://github.com/fosfrancesco/asap-dataset/tree/master/Bach).
- MuseTrainer describes itself as "MuseTrainer public domain MusicXML library" — [MuseTrainer README](https://raw.githubusercontent.com/musetrainer/library/master/README.md).
- The KernScores server returned HTTP 503 for the Invention 13 kern file — [kern.humdrum.org request](https://kern.humdrum.org/cgi-bin/ksdata?file=inven13.krn&l=osu/classical/bach/inventions&format=kern).

### Inferences
- The WiR files are the cleanest choice for the two preludes: right bar count, clear licence, and the human labels sit in the same folder.
- The music21 / MuseTrainer copy of the BWV 846 prelude should be avoided for checking against bar-numbered analyses, because its 34 measure elements will not line up with the 35-bar text every analysis uses.
- The BWV 847 fugue files with credits "Fugue No. 2 in 3 voices in C Minor, from Das Wohltemperierte Klavier Book I" look like copies of one MuseScore-hosted edition; this wording matches the Open Well-Tempered Clavier project, which was released into the public domain, but that link is an assumption and is not stated in the files.
- The three-part sightread version of the BWV 847 fugue (one voice per part) may suit voice-leading output better than the two-staff piano layout.
- For BWV 269 the 24 measure elements against a last number of 21 most likely reflect the pickup bar and split bars at the repeat; bar numbers should be checked against the Harmonic Circuit score (numbered 1–21) before comparing.

### Gaps
- Licence of the BWV 847 fugue and Invention files is unverified: they carry no rights statement and sit in third-party repositories as test or sample data.
- Note-level accuracy of the files was not proofread against an Urtext; only structure (parts, measures, key, metre) was checked.
- No MusicXML was found for the Cello Suite No. 1 Prelude in original form; MuseScore is not installed here, so converting the DCML .mscx file was not tested.
- No C minor MusicXML of BWV 999 was found. A guitar file in another repository (joedesmos-co/Corranzo) appeared in search but was not downloaded.
- musescore.com, OpenScore and the PDMX dataset were not searched; musescore.com downloads need a login.
- GitHub code search was rate-limited part of the way through, so some filename searches (cello suite, "Jesu, Joy") returned nothing and are inconclusive.

---

## Key Question 4: Which candidates are strongest overall, ranked, and why?

### Takeaway
Top three for the owner to consider: (1) Prelude in C major BWV 846, (2) chorale "Aus meines Herzens Grunde" BWV 269, (3) Fugue in C minor BWV 847. These three give one arpeggiated harmony piece, one four-part chorale with non-chord tones and cadences, and one contrapuntal piece, each with a professional analysis and a verified score file. Prelude in C minor BWV 847 and Invention 13 are the best substitutes.

### Cited Findings

Ranking (strongest first), with the evidence each rank rests on:

1. **Prelude in C major, BWV 846.** Three independent human readings: Bruhn's sectional and cadential analysis with a full chord reduction — [Bruhn WTC-01.pdf](https://edition-gorz.de/WTC-01.pdf); teoria's chord-by-chord ii–V–I reading with score images — [teoria](https://www.teoria.com/en/articles/2017/BWV846/index.php); WiR's label for every bar — [WiR analysis.txt](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/Corpus/Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/01/analysis.txt). Score: WiR score.mxl, 35 measures, CC BY-SA 4.0, download confirmed — [score.mxl](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/Corpus/Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/01/score.mxl). The sources agree on the key points: Bruhn's "m. 1 = I, m. 2 = ii2, m. 3 = V65, m. 4 = I" equals WiR's "m1 C: I / m2 ii2 / m3 V65 / m4 I"; both put the dominant pedal at m. 24.
2. **Chorale "Aus meines Herzens Grunde", BWV 269.** The annotated score carries numerals, cadence types and non-chord tone labels, written by a university theory professor — [Harmonic Circuit](https://alexandermartinblog.wordpress.com/2017/07/17/1-aus-meines-herzens-grunde/). Second human reading as labels — [music21 rntxt](https://raw.githubusercontent.com/cuthbertLab/music21/master/music21/corpus/bach/choraleAnalyses/riemenschneider001.rntxt). Score: four-part .mxl, download confirmed — [music21 bwv269.mxl](https://raw.githubusercontent.com/cuthbertLab/music21/master/music21/corpus/bach/bwv269.mxl). The two readings can differ in detail: at bar 12 the professor reads an "apparent I6" standing for the dominant ("cadential 6/3"), while the label file has "m12 I6 b3 V7".
3. **Fugue in C minor, BWV 847.** Bruhn's full entry, countersubject, episode and key analysis with design diagram — [Bruhn WTC-02.pdf](https://edition-gorz.de/WTC-02.pdf); whole-fugue annotated score in an open textbook — [Puget Sound](https://musictheory.pugetsound.edu/mt21c/FugueAnalysis.html). Score: 31-measure MusicXML, download confirmed, licence unverified — [EuterPen BWV_847.xml](https://raw.githubusercontent.com/VincentCavez/EuterPen/main/scores/BWV_847.xml).
4. **Prelude in C minor, BWV 847.** Bruhn's harmonic plan — [Bruhn WTC-02.pdf](https://edition-gorz.de/WTC-02.pdf) — plus WiR labels and a WiR score with clear licence, 38 measures, download confirmed — [score.mxl](https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/Corpus/Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/02/score.mxl). Only one prose analysis was found, and the piece is similar in kind to BWV 846.
5. **Invention No. 13 in A minor, BWV 784.** Roman numerals and key areas on the score for the whole piece, but very little prose — [teoria](https://www.teoria.com/en/articles/2020/bach-inventio/13/index.php). Score: 25 measures, download confirmed, licence unverified — [Invention_13.xml](https://raw.githubusercontent.com/webern/mx/main/data/foundsuite/Invention_13.xml).
6. **Fugue in C major, BWV 846.** Deep analysis in Bruhn — [Bruhn WTC-01.pdf](https://edition-gorz.de/WTC-01.pdf) — and a verified score — [ASAP](https://raw.githubusercontent.com/fosfrancesco/asap-dataset/master/Bach/Fugue/bwv_846/xml_score.musicxml) — but the licence is non-commercial, and the three published analyses disagree on how many entries and stretti there are (see K in Key Question 2).
7. **Invention No. 1 in C major, BWV 772.** Complete motivic analysis with no Roman numerals or cadences — [teoria](https://www.teoria.com/en/articles/BWV772/index.php); score verified — [Invention 1.xml](https://raw.githubusercontent.com/webern/mx/main/data/foundsuite/Invention%201.xml).
8. **Cello Suite No. 1 Prelude, BWV 1007.** Free analysis is a short blog post discussed in a transposed key — [John Hall](https://johnhallguitar.com/blog/blog/bach-cello-suite-1-bwv-1007-prelude-analysis); score only in MuseScore format — [DCML .mscx](https://raw.githubusercontent.com/DCMLab/bach_solo/main/MS3/BWV1007_01_Prelude.mscx).

Not recommended on current evidence: Goldberg Aria (score fine, analysis is a short student post — [DePauw blog](http://depauwform.blogspot.com/2005/02/aria-from-js-bachs-goldberg-variations.html)); BWV 999 (analysis in C minor — [teoria](https://www.teoria.com/en/articles/2024/BWV999/index.php) — but score in D minor — [freedots](https://raw.githubusercontent.com/mlang/freedots/master/scores/bwv999.xml)); Minuet in G (composer is Petzold per the file credits — [MuseTrainer](https://raw.githubusercontent.com/musetrainer/library/master/scores/Bach_Minuet_in_G_Major_BWV_Anh._114.mxl)); Air and Toccata (piano arrangements only — [MuseTrainer README](https://raw.githubusercontent.com/musetrainer/library/master/README.md)).

### Inferences
- A set of BWV 846 Prelude + BWV 269 chorale + BWV 847 Fugue exercises the widest range of the tool's features: one chord per bar with pedals and applied chords; dense four-part harmony with cadences and non-chord tones; and subject/answer/episode structure with a modulation to the relative major.
- If the owner prefers three pieces that all yield chord-by-chord comparisons, swap the fugue for Invention 13 or the BWV 847 Prelude.
- If licence clarity matters for anything shipped or shown publicly, the WiR files (CC BY-SA 4.0) are the safest; the fugue and invention files would be better re-sourced from a clearly licensed edition before publication.
- BWV 846 Prelude is also the best-known of all candidates to the general public; BWV 269 is well known mainly to theory students as the first chorale in the Riemenschneider collection.
- Where human analyses disagree (bar 12 of BWV 269; entry counts in the BWV 846 fugue), a difference from one source is not by itself a tool error.

### Gaps
- Popularity is judged informally; no listening or teaching statistics were collected.
- The ranking rests on the analyses found in one session; public-domain textbook analyses (Prout, Iliffe, Riemann) and Tim Smith's WTC site were not reviewed and could change the order for the fugues.
- Whether the tool's bar numbering matches the files (pickup bars, repeats in BWV 269) has not been tested.
