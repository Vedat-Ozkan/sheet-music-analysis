# Why Audiveris 5.11 loses accuracy (2026-10-11)
Method: attribute.py (own XML onset extractor, bars aligned with compare.align; reproduces baseline 32280 vs 32411 matched).
Output: attribution.json (per PDF, per engraver). Debug logs: scratchpad/why/{all,dbg}. e-subclasses are bar-level heuristics.
Lost 9091 of 41371 truth notes: crash/skipped 1709, head missing 2098+254 grace, tuplet-related 1864, clef/octave/semitone pitch 1163,
voice-count 541, bars missing 442, dots 421, grace timing 329, other 270. Invented notes: 658 (1.6%).
Mechanisms (stock source lines): RestInter.java:203-215 (+const :239 minInterChordDx=0.5) drops 16th rests beside a chord; MeasureRhythm.java:1044/690
+AbstractChordInter.java:635 chords without timeOffset are dropped; TupletsBuilder.java:512-526 (stock) TOO_MANY/TOO_LONG;
only TUPLET_THREE/SIX signs exist (no 2, 5, 9, 13); PartwiseBuilder.java:3722 NPE drops whole measures; SlurInter.java:152 + Voices.java:430 NPE on Verovio lieder with split start barlines.
Experiment: -option org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0 on bach-prelude-846--ms: pitch 54.7% -> 76.2%, pitch+onset 11.0% -> 44.8% (not tested on other PDFs).
