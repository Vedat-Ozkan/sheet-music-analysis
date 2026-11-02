# Rhythm solver for the PDF reader: design (2026-11-02)

Goal: fewer bars that don't add up (`engine.read_pdf.problem_spots`) by choosing, per measure, the best-supported reading that fills the bar, using evidence the reader currently throws away. Context and numbers: `docs/engineering-log.md` entry 90. Audiveris fork base: branch `sma-integration`.

## Where alternatives are lost today (Audiveris 5.11 fork)

By RHYTHMS every rejected candidate has been removed with `inter.remove()` and nothing records it.

| # | Where | What is lost |
|---|---|---|
| L1 | `SymbolsBuilder` keeps the top 2 evaluations (`maxEvaluationCount=2`, floor `symbolMinGrade` 0.15) | rest, flag or dot shapes ranked 3rd or lower |
| L2 | `RestInter.createValid` | rests near a head chord (inactive in production: `minInterChordDx=0`) |
| L3 | `AbstractFlagInter.createValidAdded` | flags with no stem link |
| L4-L6 | `DotFactory` checks, `SigReducer.checkAugmentationDots`, `reduceAugmentations`, `reduceHeadAugmentations` | dot candidates and losing dot-to-chord links |
| L7 | `SIGraph.deleteWeakInters` via `SigReducer.contextualizeAndPurge` | anything with contextual grade < 0.5; rests get no support, so a rest graded < 0.625 always dies |
| L8 | `SIGraph.reduceExclusions` | the weaker side of exclusions (flag shapes, head kinds, rest vs other) |
| L9 | `NoteHeadsBuilder.purge`, `ChordsBuilder` | the small-head (grace) alternative |
| L10 | `BeamsBuilder` items below `getMinGrade` | evidence for one more beam |
| L11 | `MeasureRhythm.process` | tuplet hypotheses tried first-fit, no ranking or margin |
| L12 | `SlotMapper.mapRookies` (greedy; `processAll` disabled), `createNewVoices` | other voice mappings; chords left without a time |
| L13 | `StackRhythm.generateStackSlots`, `PartwiseBuilder` | untimed chords dropped from export; disagreeing onsets across parts unflagged |

## Data model

- `Alt(kind, shape, grade, rivalGrade, bounds, staff, glyph, partner)`, with kind one of REST, DOT, FLAG, BEAM_ITEM, SMALL_HEAD. It is kept as a transient list per system and filled by one helper at L1-L10.
- Per-measure edits:
  - ADD_REST (new chord)
  - ADD/MOVE/DROP_DOT (×3/2, ×2/3)
  - FLAG±1 / BEAM±1 (×½, ×2)
  - GRACE (leaves the timeline)
  - TUPLET(family) (×2/3 on a `getSpans` family)
- Every edit except DROP_DOT, BEAM−1 and TUPLET points to recorded ink. There is no "add note" or "drop chord" without ink.
- Edits are overrides during the search. An accepted solution changes the symbol graph for real, so that `<type>` and `<duration>` agree at export.

## Search

- **Inner search (replaces L12):** beam search over slots, left to right.
  - Branching: the top 4 `ChordsMapper` mappings, or a new voice at the slot time.
  - Hard constraints: same onset within a narrow slot, beam/tie groups kept in one voice, no voice past the bar end, every chord timed.
- **Outer search, only on failing measures:**
  - up to 12 relevant edits, subsets of at most 3, in increasing cost order;
  - an exact-duration filter decides the order;
  - stop when the next subset costs more than best + Δ.
- **Edit cost:** `c0[kind] + w[kind]·max(0, logit(rival) − logit(grade))`, about 12 constants fitted on `bench` only.
- **Cross-part sync:** runs at stack level. Keep the top 3 solutions per measure and pick the combination that minimises cost + `s` per same-column pair with different onsets.
- **Caps:** 48 inner searches per measure and 3 s per page; when a cap is hit, the bar is left as it was.

## Acceptance guards (otherwise keep the baseline and leave the bar flagged)

1. The bar failed without edits.
2. The best solution fills every voice exactly, times every chord, and uses no more voices than the baseline.
3. Every edit has ink with grade ≥ `gmin[kind]`; at most 3 edits, and at most 1 type change on a pitched note.
4. Margin: the best rival with a different pitched onset/duration sequence costs at least Δ more.
5. Total cost ≤ `Cmax`.
6. No same-column agreement across parts is broken.
7. The engine's Python tuplet repairs run only on bars still flagged.

## Phases

| Phase | Work | Expected on main set (309 → ) | Stop if |
|---|---|---|---|
| 0 | Diagnostic build logs every Alt at L1-L10; join offline with the per-bar truth classification | measured ceiling per cause | under 50% of rest/dot/type bars have matching ink → drop phases 2-3 |
| 1 | Revoicing only: inner search + stack sync + guards, no edits | −30 to −45 (Bach 846, Die Stadt, Faisst) | fewer than 20 of the 61 voice-only bars cleared |
| 2 | REST and DOT edits | −15 to −25 | false-fix rate > 10% |
| 3 | FLAG±1, BEAM±1, GRACE | −20 to −30 | same |
| 4 | Fold the tuplet search in; retire engine tuplet repairs | 0, less code | tuplet bucket grows on any held-out set |

**Measuring each phase:**
- Production path through `spike/omr/speed/variants.py`, on all five sets.
- Pitch+timing must go up and pitch must not go down on every set.
- Report which reading wins and the added seconds per page.
- New gate, the false-fix rate: among bars that stop being flagged, those whose onsets don't match the truth must be ≤ 10%.
- `spike/omr/bench-timechange` is the unseen check, run once per phase and never tuned on.

**Honest ceiling:** about 80-105 of the roughly 230 bars left after the targeted fixes, which would leave about 125-150. Under 100 probably also needs new detection where no candidate exists (missed notes, beams with no item). Phase 0 replaces this estimate with a measurement.

**Risks:**
- Hiding a wrong rhythm. Guarded by the margin rule and the false-fix gate.
- Uncalibrated grades. If fitted weights differ by more than 2× between sets, the cost model isn't working.
- Changing which reading `read_pdf` picks.
- Runtime. Tighten the caps if the solver adds more than about 10% of read time.
