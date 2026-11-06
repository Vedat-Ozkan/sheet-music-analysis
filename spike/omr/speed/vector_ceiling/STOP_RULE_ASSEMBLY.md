# Test 1: voices and triplets given exact symbols (written 2026-11-02, before any run)

Question: when every symbol in a bar is read exactly, can a simple, rule-based assembler work out where each note starts (its voice and any triplets) so the bar matches the truth? Solver phase 1 failed at this step with Audiveris's symbols; this test asks whether exact symbols make it tractable.

Input: the staff-bars from test 0 (`STOP_RULE.md`) whose symbol multiset matched the truth exactly, on the 34 main-set MuseScore and LilyPond PDFs. From the PDF: each event's x position, printed value, dots, rest or note, stem direction, the beam it belongs to, and printed tuplet numbers where the font has them. The bar length comes from the truth's time signature (reading a printed time signature is a separate, easy step).

Assembler (fixed before running, no tuning on results):
1. One voice if every stem points the same way; otherwise up-stems and rests above the middle line form voice 1, down-stems and rests below form voice 2.
2. In each voice, events in x order, each starting where the previous one ends.
3. If a voice does not fill the bar exactly, try treating beam groups of three equal notes (or of six) as triplets, fewest groups first, and keep the first combination that fills the bar exactly. A printed tuplet number marks its group as a tuplet directly.

A staff-bar **matches** when the multiset of (start, sounding length, rest or note) equals the truth's.

**Rule** (matched over tested staff-bars):
- 90% or more: voices and triplets are tractable with exact symbols; the vector reader is worth planning.
- Under 75%: stop; even with perfect symbols the assembly step is the hard part.
- 75-90%: report and let the owner decide.

Also reported separately: one-voice bars, two-voice bars, and bars with triplets.
