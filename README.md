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
| `spike/` | Throwaway MCP server for plan step 1: tests how a score gets in and how a page shows up in each chat app. |
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
print(draft.as_text(draft.draft(score, ScoreIndex(load_toolkit(score).getMEI())), 1, 8))
"
```

## Test score

`tests/data/chopin_nocturne_op9_no2.mxl` is a community transcription from the MuseTrainer public-domain library (https://github.com/musetrainer/library).
