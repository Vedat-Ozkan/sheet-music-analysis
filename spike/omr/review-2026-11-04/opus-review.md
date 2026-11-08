# Review of 2026-11-04 work

> Historical record of a 2026-11-04 review. Scan merging is parked and the reader is frozen until 1 December except a clef fix (`docs/engineering-log.md` entry 128).

## Confirmed, ranked

1. **"Exact" credits bars drawn wrong; 68.4% overstates the merge.** `homr300` has no accidental, tie, beam or direction elements. Drawn signs: five pieces 268 to 169 (reference 288), inspect 314 to 133 (376). Exact plus signs matching the sound (estimate; fires 2 times on references): five pieces 135 to 146, inspect 25 to 54, unseen 18 to 37. Engine timing disagrees with scorer on 12 merged exact bars. Directions move to bar start (`mergexml.py:107-109`). Decision: don't present 68.4; write signs first.

2. **Target missed; even perfect choosing barely reaches 75%.** Rule 3 fails. Rule 4's pass is net only: 38 gained, 6 lost, Mozart 3, Beethoven 2. 173 clears 172.66 only through the "neither adds up" branch (172 without), right on 1 of 16 staves (unseen 0 of 17). Bootstrap by piece: baseline 29-76%, gain 5-21 points. A chooser peeking at the reference gets 187-190 of 253 (73.9-75.1%). "Five pages" are 5 pieces, 11 pages. Decision: 75% needs better reading.

3. **bench-olimpic's gain is homr's.** homr alone: inspect 86-87, unseen 73-76, pitch 97.6. Merged: 85, 74, pitch 94.3. Rule 5 passes without merge help.

4. **Multi-part scores corrupt.** `mergexml.py:83,118-119` always reads homr's first part. On 42 clean multi-part PDFs: exact 1046 to 911; pitch 27716 to 25291, below homr's 25812. Part index patched in scratch: 931, 26973. Every scored scan is piano-only. Decision: blocks voice-and-piano.

5. **`clean.py` damages readings; crash explanation wrong.** Staves plus rests alone load 45 of 45 and 100 of 100 others; the repeats fix is not needed. Segfault untraced. `drop_repeats` (`clean.py:28-30`) deleted Bach's returns to five flats (bars 11, 17); the page stays at one flat from bar 15. `fix_rest_chords` deleted 55 rests, 46 matching the reference. Decision: rewrite both.

6. **Warnings catch less.** Silent wrong bars fall (64 to 48, 84 to 56, 85 to 63), but their share rises: 59 to 64%, 58 to 64%, 59 to 72%.

7. **Cost picture incomplete.** Omitted: US$13 is 2.6 times the US$5 target, before reading costs; production ran 1.6-1.9 times slower than staging; 8 scanned pages add 3.5 minutes while 15 of 25 reads already pass Cloudflare's limit; two readings at 1.1-1.3 GB each, homr to 1.2, server about 0.9, against 4 GiB, never measured together. Claude users read in the sandbox: no gain unless homr runs there (728 MB, models from GitHub, untested). Decision: re-quote.

8. **Log.** 69.9 is the old engine; today's gives 63.5. Unseen's 72.1 is today's (old: 79.9): unlike tables. "About 20% with true page sizes" is 16.9. Exact ignores grace notes (191 of 4,682 bars).

9. **378e4fd6d** is a root-cause fix, but the catch path still returns 0 (`Page.java:206`) and `engine/score.py:139` is unguarded. Its five test divisors were already multiples of 4.

10. **Risks.** 12 fork commits exist only under `/tmp`. The CC BY-SA OLiMPiC PDF in `tests/data` lacks credit.

## Plausible

- **Unseen isn't unseen to homr.** Its FAQ lists OpenScore Lieder, GrandStaff and PDMX as training data; `convert_lieder.py` shows no OLiMPiC exclusion. homr beats the current reader by 36 points on OLiMPiC, 0.8 on real pieces: consistent, though tiny systems confound it. Treat 46% as a ceiling.
- FAQ: weights include CC BY-NC PrIMuS. `safe.py` patches homr, so a service must publish it.

## Held up

Headline figures and cost arithmetic recompute. Chooser never reads the reference. Halves share no work. Scan rule 170/170, 93/93. Tie, mark, split-bar commits: no defect. Clef 128-132, 1480-1480.

## NOT RUN

Suite, `test_awkward`, `diff_check`; Cloud Run; real voice-and-piano scans; both readers together; Claude sandbox; clef crops by eye. `bench-pitch` per-PDF flags stayed in scratch, unopened.
