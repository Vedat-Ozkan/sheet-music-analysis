# Ceiling check for a vector reader (written 2026-11-02, before any run)

Question: on exported PDFs, can the PDF's own drawing instructions recover every printed symbol's value exactly? If yes, a new reader would only have voices and tuplets left to solve; if no, the route is not worth months.

Input: main-set (`bench`) MuseScore (ms) and LilyPond (ly) PDFs and their truth files.

Method: from the PDF alone, per staff and bar (bars from barlines), list every event: each stem with its noteheads, each stemless head column, each rest. Value of an event: head kind (whole/half/black), flags or beams at its stem (one per halving), augmentation dots, rest glyph value. Grace notes (small heads) are left out. From the truth, the same list per staff and bar from `<type>`, `<dot>` and `<rest>` on non-chord, non-grace, printed notes. A staff-bar **matches** when the two lists are the same multiset.

Only PDFs whose barlines give the same bar count per staff as the truth are scored; the rest are reported as not aligned.

**Rule** (on matched staff-bars over aligned staff-bars):
- 95% or more: viable; the symbol layer is solved by reading the PDF, and the months go into voices and tuplets.
- Under 85%: stop; even exact drawing instructions do not give the symbols cheaply.
- 85-95%: report and let the owner decide.

Also reported: the same share on the staff-bars inside currently flagged bars, aligned PDFs per engraver, and the main reasons for mismatches.
