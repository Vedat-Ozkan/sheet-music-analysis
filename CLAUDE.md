# Sheet Music Analysis: rules for working in this repo

These are the owner's standing rules. Older detail is in the memory notes for this folder; where they disagree, this file wins.

## Before calling anything done
- Find the root cause of every defect, then add a check that runs across the whole test corpus for that kind of defect before fixing it. A second patch round on the same code means stop and fix the design.
- Fix the whole class of bug: search for every other place with the same pattern.
- Run `tools/diff_check.py --base main AREA` for engine changes and read every changed item, not totals.
- Run `tests/test_awkward.py` and the real-world inputs in `tests/data/` for any change to reading, analysis or drawing. Every file that crashed for a user goes into the test data.
- Look at produced pages full size against the original before reporting that they work. Use real inputs only, never invented demo ones.
- A different model or agent reviews a branch before it is merged.
- For the full suite, have a subagent run it and report only failures. Report checks that could not run as NOT RUN.

## Deploying
- Production deploys only from a clean, committed tree on `main` that CI has passed. Staging may run a branch.
- Measure and quote any change that adds Cloud Run compute before deploying it. Running cost target is about US$5 a month; the Google Cloud account is on a free trial that ends 2027-01-05.
- Never raise max instances or the daily limits without asking. Daily limits are shared by everyone by design; ask before changing anything about usage counting or limits.
- After a deploy, check the new revision's startup lines and errors in the logs.
- The published Claude plugin is `dist/sheet-music-analysis` on GitHub `main`: pushing a changed `dist/` is a plugin release. Ask first, rebuild it with `tools/build_skill.py` and bump the version in `plugin/.claude-plugin/plugin.json`.
- ChatGPT holds new or changed tools until OpenAI approves them, and an update that is held keeps the old tool metadata. Keep every widget address an approved tool points to working until the update is approved.

## Owner decisions
- Display, upload or UI choices: show real examples from both Claude and ChatGPT first; the owner decides.
- Public text (site, listings, messages users see) must be clear to someone with very basic music knowledge; explain how a number was measured; no library or model names.
- Record problems, fixes and before/after numbers in `docs/engineering-log.md`, honestly.
- Keep agent and evaluation token use low: short fresh briefs, Sonnet for routine work, test on 2-3 pieces first, ask before anything over about US$10.
- Commit with explicit paths; never push, deploy or publish without being asked.
