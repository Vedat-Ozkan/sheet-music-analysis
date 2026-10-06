# Sheet music analysis

Harmonic analysis drawn on an engraved score, for use inside Claude and ChatGPT. The plan is in `docs/plan.md`; the research behind it is in `docs/research-2026-10-01.md`.

## Layout

| Path | What it is |
|---|---|
| `engine/` | Parses MusicXML, engraves it with Verovio, draws an annotation list on the page, exports PNG and PDF. |
| `docs/annotation-spec.md` | The annotation list format the chat model writes. |
| `examples/` | A hand-written annotation list for Chopin, Nocturne Op. 9 No. 2, measures 1–8. |
| `skill/`, `tools/build_skill.py` | The skill that runs the engine inside Claude's sandbox on the attached file; the build script bundles the engine with it into `out/sheet-music-analysis.zip`. |
| `engine/notes.py` | Compact text form of a score's notes, which the skill passes to the server so the draft model can run without the file being uploaded. |
| `spike/` | Throwaway MCP server (superseded by `server/`) for plan step 1: tests how a score gets in and how a page shows up in each chat app. |
| `server/`, `Dockerfile` | The production MCP server (`server/app.py`): the four tools the plugin and ChatGPT use, daily limits, storage in a Cloud Storage bucket that deletes scores and pages after a day. `server/deploy.sh PROJECT_ID` builds the image on Cloud Build and deploys it to Cloud Run (one instance at most). Run locally with `.venv/bin/python -m server.app` (port 8080, files under `out/server/`). |
| `site/`, `wrangler.jsonc` | The website at sheetmusicanalysis.com: landing page, how-to-use, privacy and terms, plus the clef icons the server reports to chat hosts. Static files served by Cloudflare; publish with `npx wrangler@4 deploy`. |
| `engine/draft.py` | Runs the draft model and condenses its output into chords, cadences, phrase ends and non-chord tones. |
| `vendor/analysisgnn/` | Clone of the draft model (not committed; see `.gitignore`). |

## Setup

```bash
uv sync --python 3.11
.venv/bin/python -m pytest
```

Render the example to `out/`:

```bash
.venv/bin/python -c "
from engine.annotate import render
from engine.annotations import AnnotationList
score = open('tests/data/chopin_nocturne_op9_no2.mxl', 'rb').read()
notes = AnnotationList.model_validate_json(open('examples/chopin_op9_no2_m1-8.json').read())
page = render(score, notes, measures=(1, 8))
open('out/example.png', 'wb').write(page.png(1, width=1600))
open('out/example.pdf', 'wb').write(page.pdf())
"
```

## Platform spike

```bash
PUBLIC_BASE_URL=https://<public-host> .venv/bin/python -m spike.server   # serves /mcp on port 8765
```

The server needs a public HTTPS address (a tunnel or a host) before Claude or ChatGPT can reach it. It has no login, so run it only while testing. Each tool call is logged to `out/spike/calls.log` with the input path that was used.

| Tool | What it does |
|---|---|
| `draft_analysis` | Runs the draft model and returns its table for the chat model to review. |
| `render_analysis` | Draws the reviewed annotation list and shows the page in a card, with a PDF link. |
| `draft_from_notes` | Runs the draft model on a note list sent by the Claude skill. |
| `choose_score` | Fallback: a file button in the chat, for Claude users who have the connector but not the skill. |
| `engrave_score`, `engrave_score_card` | Plain engraving, as an image result or in a card. |
| `sample_analysis`, `sample_analysis_card` | The hand-annotated Chopin example, needing no file. |

Results of testing in both apps are in `docs/gate1-results.md`.

## Robustness

```bash
.venv/bin/python -m tools.robustness            # every score, every stage
.venv/bin/python -m tools.robustness --matching ravel
```

Runs 31 scores through reading, the note table, the note list, engraving, the draft model and rendering: Bach chorales, Classical and Romantic quartets, songs and piano music from the music21 corpus, and impressionist and early twentieth-century piano music (Ravel, Debussy, Satie, Scriabin, Rachmaninoff, Prokofiev, Schoenberg) downloaded on first use into `out/`. The downloaded transcriptions are for local testing and are not committed. Results go to `out/robustness/report.json`.

## Evaluation

```bash
.venv/bin/python -m eval.run                                   # draft model alone, scored against expert chord labels
.venv/bin/python -m eval.review                                # Opus at medium effort reviews each passage, as the skill does
.venv/bin/python -m eval.run --reviewed out/eval/reviewed/opus-medium   # score the reviewed analyses the same way
.venv/bin/python -m eval.judge                                 # compare with what a teacher wrote about each piece
```

`eval/pieces.py` lists 23 pieces from Bach to Ravel, each paired with a published human analysis (how they were chosen is in `reports/Scores with published analyses.md`). Twelve have a chord-by-chord reading by a human analyst that a script can compare against; the rest have prose only. Scores, labels and results are kept in `out/eval/` and are not committed. The review and judge steps call `claude -p`, so they use the account Claude Code is signed in with.

Results, and the problems met along the way, are written up in `docs/engineering-log.md`.

The score for a reading is the share of the piece, by duration, where it agrees with the human labels: on the key, on the chord's root, on the whole chord, on the chord with its bass note, and on all of these together (`full`). `reference_fit` is the share of notes that belong to the human's chord; a low value means the bar numbers of the labels and the file do not line up.

## Draft model

AnalysisGNN drafts the analysis; the chat model reviews it. It runs in its own environment (`.venv-agnn`, Python 3.11, PyTorch 2.5 CPU) and `engine/draft.py` calls it as a subprocess, so the engine itself needs no ML packages.

```bash
uv venv .venv-agnn --python 3.11 && export VIRTUAL_ENV=$PWD/.venv-agnn
uv pip install torch==2.5.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install pyg-lib torch-scatter torch-sparse torch-cluster -f https://data.pyg.org/whl/torch-2.5.0+cpu.html
uv pip install torch-geometric pytorch-lightning partitura music21 numpy pandas scikit-learn torchmetrics wandb tqdm gitpython scipy requests matplotlib seaborn imbalanced-learn
uv pip install --no-deps "git+https://github.com/manoskary/graphmuse.git@main"   # the PyPI 0.0.5 wheel is too old for the checkpoint
git clone --depth 1 https://github.com/manoskary/analysisgnn vendor/analysisgnn && uv pip install --no-deps -e vendor/analysisgnn
mkdir -p artifacts/models && curl -L -o artifacts/models/model.ckpt \
  https://huggingface.co/spaces/manoskary/analysisgnn/resolve/main/checkpoint/model.ckpt
```

Notes on the weights (checked 2026-10-01):

- The checkpoint comes from the author's public Hugging Face Space `manoskary/analysisgnn`, which is marked MIT. The Weights & Biases artifact named in the upstream README is no longer accessible to ordinary accounts.
- The author has called this public version "effectively deprecated" and said a better model with an open Hugging Face checkpoint will follow once a paper review finishes (quoted in upstream issue #9, May 2026).
- Two upstream quirks are worked around in `engine/models/analysisgnn_runner.py`: the Roman numeral output is decoded with the wrong table, so numerals are rebuilt from the degree, quality and inversion outputs; and the confidences of those outputs are flattened by repeated softmax, which the runner undoes.
- On this machine a full analysis of the 38-bar nocturne takes about 4.5 s and 0.8 GB of memory on CPU, model loading included.

Draft table for a range of measures:

```bash
.venv/bin/python -c "
from engine import draft
from engine.render import load_toolkit
from engine.score import ScoreIndex
score = open('tests/data/chopin_nocturne_op9_no2.mxl', 'rb').read()
print(draft.as_text(draft.draft(ScoreIndex(load_toolkit(score).getMEI())), 1, 8))
"
```

## Test score

`tests/data/chopin_nocturne_op9_no2.mxl` is a community transcription from the MuseTrainer public-domain library (https://github.com/musetrainer/library).
