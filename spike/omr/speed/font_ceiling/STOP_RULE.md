# Ceiling check for reading symbols from the PDF's music font (written 2026-11-02, before any run)

Question: of the flagged bars on MuseScore (ms) and LilyPond (ly) PDFs, how many could reading the music-font glyphs fix?

Input: solver phase 0 rows (int3 reading, main set, 338 flagged bars; 214 on ms and ly). Each row lists what the bar needs to match the truth (rest missing, dot, flag/type, note missing, grace read as a real note, tuplet, voice) with an x position, staff and page.

A bar counts as **covered** when every item it needs is a symbol that ink can supply (rest, dot, flag, notehead) and the PDF has a music-font glyph of that kind on the right staff within one staff space of the expected x. Bars that need only voice or tuplet changes, or a "no ink" change (dropping a dot or a beam), are not covered: font reading gives exact symbols, not voices or tuplets.

Covered bars are an upper bound on what font reading alone can fix.

**Rule:**
- 60 or more covered bars (of 214): worth the 5-8 days.
- Fewer than 30: stop; font reading is not where the flagged bars are.
- 30 to 59: report the numbers and let the owner decide.

Also reported, not part of the rule: covered bars if one staff of tolerance is allowed, and how many ms/ly bars are voice- or tuplet-only.
