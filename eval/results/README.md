# Evaluation results

Score summaries behind the figures in the top-level README and `docs/engineering-log.md`, copied from `out/eval/` (not in git). Only scores and our own model-written annotation lists are here. Expert label files, published analyses and scores are not, because several corpora are CC BY-NC-SA or have unclear licences. Run every command from the repository root.

## Headline figures

| Published figure | File | How to read it | Regenerate |
|---|---|---|---|
| Ours against an expert 0.694, one expert against the other 0.697 by chord at full, 99% of the experts' figure; root 0.885 and 0.907; precision 0.720; difference +0.012 (−0.027 to +0.052); by time 0.74 and 0.70 (36 pieces, two experts each; README and site, `site/index.html` and `site/method.html`) | `out/eval/ladder-multi-opus-medium-multi-alone-table.json`, not copied here | `summary.all`, `ours` and `experts`: `recall.full` (0.6939, 0.6974; the ratio 0.9949 is the 99%), `recall.root` (0.885, 0.907), `ours.precision.full` (0.720), `ours minus experts` → `recall full`, `time.full` (0.736, 0.704). The site's per-style and per-level figures are `summary.<style>` and `summary.all` `recall.<level>` in the same file; log 122 | `.venv/bin/python -m eval.ladder --set multi --reviewed out/eval/reviewed/opus-medium-multi-alone-table` |
| Earlier figure, still in `docs/listing.md`: neural draft alone, 0.48 (30 held-out pieces) | `report-heldout.json` | `draft.full`, weighted by `scored_bars`, over the 30 pieces that have a `reviewed` entry. The command prints the draft over all 94 held-out pieces (0.453), not this figure. | `.venv/bin/python -m eval.run --set heldout --reviewed out/eval/reviewed/opus-medium-2026-10-24` |
| Earlier figure, still in `docs/listing.md`: draft reviewed by the chat model, 0.67 (30 held-out pieces) | `report-heldout.json` | `reviewed.full`, weighted by `scored_bars`, over the same 30 pieces (0.670); the command prints it. | same command |
| Earlier figure, still in `docs/listing.md`: two experts against each other, 0.71 (151 pairs) | `ceiling.json` | `summary.all`: 151 pairs, 10,684 bars, `full` 0.711. `pairs` lists each pair's scores. | `.venv/bin/python -m eval.ceiling` |

`report-heldout.json` was regenerated on 2026-11-06 with the command above, because the copy in `out/eval/` had been rewritten that day with three pieces scored from a later review (`opus-medium-after-fixes-2026-10-31`). Its totals match those of the earlier file: draft 0.481 and review 0.670 on the 30 pieces. The draft over all 94 pieces is 0.4528 here, against 0.4526 in the earlier file.

## Other files

| File | What it holds | Regenerate |
|---|---|---|
| `reviewed-opus-medium-2026-10-24/` | The 30 held-out annotation lists written by Opus 5.5 at medium effort on 2026-10-24. These are the reviewed readings scored in `report-heldout.json`. | `.venv/bin/python -m eval.review --set heldout --only ID --passages 2 --tag NAME` |
| `report.json` | Core set: 25 pieces, 13 with expert labels and a review. Draft `full` 0.570 and reviewed 0.759, weighted by bars. Unlike the 12 pieces of the log's 0.57 to 0.76, it includes Beethoven Op. 2 No. 1 i, which was reviewed again. | `.venv/bin/python -m eval.run --reviewed out/eval/reviewed/opus-medium-2026-10-24` |
| `any-expert.json` | Ours and the draft against any of several experts, on 14 pieces. The 6 pieces with two or more experts (229 bars) give ours against the same others 0.79 for function and 0.86 for idea, against the experts' 0.73 and 0.80 (log, challenge 66). | `.venv/bin/python -m eval.any_expert --reviewed out/eval/reviewed/opus-medium-2026-10-24` |
| `plain-2026-10-25.log` | Scores of the plain Sonnet and Opus chats in challenge 61 (127 bars, three pieces). This is the scoring before the fixes of challenge 66. | `.venv/bin/python -m eval.plain --only ID [--only ID]` |

## No file found

- Entry 82 (plain chats rescored after the challenge 66 fixes, and our setup after entries 80-81): the scores were only printed, and no saved copy exists.
- Entry 85 (plain chats and our setup given the same PDF): the scores were only printed, and no saved copy exists. Regenerate with `.venv/bin/python -m eval.pdf_compare --kind real`.

The plain chats' saved replies are left out. One of them reproduces a published analysis's header, including its analyst's email address.
