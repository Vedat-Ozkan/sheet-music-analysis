# Plan: audio input (solo piano recordings), approved 2026-10-24

## Context
The owner wants users to attach a recording instead of a score. The test in engineering log 53 (Chopin Op. 28 No. 4, Ilić recording) found:
- **Notes are accurate:** the Kong piano model reached note-onset F1 0.977.
- **The bars are not:** beat tracking under rubato got 9 of 25 bar lines right, and wrong bar numbers are visible to any beginner.
- **The cost of score-building:** analysis agreement was 56% fully automatic, 59% with the meter given, 73% with the real score's timing, and 77% with the real score's notes put through the same score-building.

Before building anything, a research phase must show whether the bar problem can be solved.

Owner decisions, 2026-10-24:
- **Claude first:** transcription runs in Claude's sandbox, so it costs nothing on our server. ChatGPT comes later.
- **Solo piano only:** other audio gets a plain explanation.
- **One optional question** may be asked before transcribing: "Do you know the time signature, or the piece's name?" No other extra steps.
- **Go/no-go gate on about 20 pieces that have real performances, as below.** If it fails, audio is parked with the evidence.
  - Bar lines right in at least 90% of bars, on at least 16 of the 20 pieces.
  - Roman-numeral accuracy against **expert labels** no more than 5 points below the same pieces analysed from the real score.

Standing rules:
- Beginner wording; the owner signs off on wording and sees real Claude examples before shipping.
- Opus standards review for visuals; no code comments; minimal code; end-to-end tests.
- Keep the engineering log updated.
- `engine/` never imports server code.
- No deploy or publish without asking.

## Phase 0: sandbox feasibility (1–2 days, no product code)
1. **Probe the real claude.ai sandbox.** I drive it with Claude in Chrome after the owner OKs it, or the owner pastes the probe script. It measures:
   - Whether `download.pytorch.org/whl/cpu` is reachable, and the size and time of a default torch install.
   - Whether onnxruntime, soundfile and numpy install from PyPI.
   - Whether ffmpeg is present; if not, whether the `imageio-ffmpeg` wheel works. mp3/m4a/ogg must be readable, because a WAV over about 3 minutes exceeds the 30 MB upload limit.
   - The time limit per command.
   - Whether the temp folder survives across turns, which the cache needs.
   - How fast a 170 MB GitHub release downloads.
   - Peak RAM and wall time to transcribe and beat-track a 3-minute mp3 on 2 CPUs.
2. **Preferred runtime is ONNX without torch.**
   - Export Kong (CC BY 4.0) and Beat This! (MIT) to ONNX locally, writing the spectrogram front end in numpy if it won't export.
   - Check that the ONNX versions give the same notes and beats as torch on Chopin 28/4.
   - Re-host the weights and their sha256 as a GitHub release. Both original hosts are blocked in the sandbox. Attribution goes in the release notes and the skill.
3. **Kill:** no runtime finishes a 3-minute piece in about 5 minutes or less within about 6 GB of RAM. Basic Pitch at F1 0.744 is a likely-fatal fallback, so re-measure it before parking.
4. **Record:** engineering-log entry with the probe table.

## Phase 1: research gate (about 2–3 weeks)
**Harness: new `eval/audio.py`.**
- Moves the scratch `align.py` and `evaluate.py` from `scratchpad/audio-test/scripts/` into the repo.
- Reuses:
  - `eval/pieces.py`: `Piece`, `score()`, `labels()`, ASAP, DCML, ROME, and `eval/dcml.py`;
  - `engine/comparison.py`: `from_romantext`, `from_draft`, `Timeline`, `compare`;
  - `eval/run.py` `cached_draft`;
  - the ±1 bar-shift search in `eval/survey.py`.
- Maps performance time to score position with ASAP's beat and downbeat annotations, and with DTW only for unannotated recordings.
- First check: it must reproduce log 53's numbers on Chopin 28/4.

**Test set: 20 pieces in ASAP that have expert labels.** The first 32–64 bars of each, chosen to include:
- at least 4 pickups;
- at least 3 compound meters;
- at least 2 pieces in 2/4;
- at least 2 meter changes;
- at least 3 tempo changes or fermatas.

**Where the audio comes from:**
- **Preferred:** real MAESTRO audio fetched as single files over HTTP Range with `remotezip`. MAESTRO is CC BY-NC-SA, so it is used for evaluation only and never goes in `tests/`.
- **Fallback:** ASAP performance MIDI rendered with FluidSynth and the Salamander Grand piano (CC BY).
- **Plus** 3–4 CC recordings from Wikimedia Commons or Musopen.

**Metrics:**
- Bars right after the best ±1 shift, with tolerance the larger of 0.3 s and a quarter beat. A wrong meter counts as wrong bars.
- Downbeat F-measure as a diagnostic.
- Numeral accuracy against expert labels for the audio path versus the score path: full numeral, root plus quality, and key.
- Diagnostics: draft-versus-draft agreement and note F1.

**Timing methods, cheapest first, each run on all 20 pieces:**
- **T0:** Beat This! baseline.
- **T1:** choose the meter and phase that put chord changes, bass onsets and note density on downbeats. Candidates: 2, 3, 4, 6 and 12 beats per bar.
- **T2:** smoothing that penalises tempo jumps (Viterbi), so one slowing can't shift every later bar.
- **T3:** use the optional answer. A meter constrains T1. For a piece name, Claude states its meter, key and pickup in the chat.
- **T4, only if T0–T3 fail:** other trackers or score-from-MIDI tools such as PM2S, BeatNet and Transkun, each after a licence check. madmom's models are NC and excluded.
- **T5, only if the owner approves:** fine-tune Beat This! on ASAP/MAESTRO. A one-off GPU cost of roughly US$10–30, quoted first.

**Score-building work alongside, measured on the real-notes run (77% today):**
- hand split by a cost-minimising pass instead of the emptiest pitch;
- note endings that respect the pedal;
- pitch spelling within a key window.

**Verdict:** a per-piece table plus pass/fail goes in a new engineering-log entry. If it fails, audio is parked with that evidence, and `site/docs.html` keeps saying audio isn't supported.

## Phase 2: build for Claude (about 1.5–2 weeks, only if the gate passes)
- **New `engine/read_audio.py`:** ports the scratch `transcribe.py` and `to_score.py` and the winning timing method.
  - Heavy imports load lazily, and no other engine module imports it.
  - Signature: `read_audio(data, meter=None, key=None, weights=...) -> AudioReading(musicxml, doubtful_bars, seconds_per_bar, is_piano)`.
  - Reuses `_numbers`, `shade`, `fit_top_margin` and `problem_spots` from `engine/read_pdf.py`.
  - A new `audio_notice()` writes beginner text that points at timestamps, e.g. "Bars 12–14 may be off by a beat; listen around 0:41".
  - The `is_piano` threshold is tuned on 5–10 non-piano clips.
- **New `skill/scripts/read_audio.py`,** mirroring `skill/scripts/read_pdf.py`:
  - pinned GitHub release asset checked by sha256;
  - a cache keyed by reader version and input sha256 in the temp folder;
  - writes `DIR/score.musicxml` plus PNG pages with doubtful bars shaded;
  - tells Claude to show every page and wait for the user's go-ahead;
  - takes `--meter` and `--key` from the optional question;
  - prints a plain refusal for audio that isn't solo piano.
  - Check that `skill/scripts/correct_score.py` bar fixes work on its output.
  - Rerunning with a different meter or shift in the chat needs owner sign-off against the attach, ask, answer rule.
- **`skill/SKILL.md`:**
  - a new input step: recording → optional question → `read_audio.py` → check page → existing steps 2–7;
  - a frontmatter description that mentions recordings. That is listing text, so the owner signs off.
  - Wiring in PDF reading, which is still missing from the skill, is a separate owner-approved change made first.
- **`pyproject.toml`:** an `audio` optional extra for runtime packages, and an `audio-research` dependency group outside the default groups.
- **`tools/build_skill.py`:** no code change; run it to rebuild `dist/`, which hasn't been rebuilt since 2026-10-10.
- **`tools/robustness.py`:** an audio branch modelled on its PDF branch.
- **Test: one end-to-end `tests/test_read_audio.py`.**
  - Input: a clip of 20 s or less rendered from public-domain MIDI with Salamander.
  - Pass: `model_notes.py` produces valid N1, the meter is right, and the bar count is exact.
- **Real claude.ai run** on a CC recording outside the test set: install time, peak RAM, total time for 3 minutes, and a cache hit on the second call.
- **Review:** owner review of real screenshots and wording (notice, question, refusal, listing), then an Opus visual standards review. Engineering-log entries.
- **Kill:** the full flow takes more than about 6 minutes, runs out of memory, or the owner rejects the wording or visuals after two rounds.

## Phase 3 (later, owner go-ahead): ChatGPT
- **Server tool:** a `read_audio` tool in `server/app.py` following the existing `read_pdf` pattern:
  - `AttachedFile` with `openai/fileParams`, and `download()` with a higher size cap for audio;
  - format checked from the file's magic bytes, and a cache key that includes the reader version;
  - a one-at-a-time busy lock like `pdf_lock`, and a new `DAILY_LIMITS` kind in `take()`;
  - the existing score_id, preview, card and `correct_bars` path.
- **Image:** a separate `.venv-audio`, with weights checked by sha256 and a runner subprocess modelled on `engine/models/analysisgnn_runner.py` and the `_Worker` in `engine/draft.py`.
- **Cost:** quote it first, at about 200 CPU-s per 3-minute piece.

## Verification
- **Phase 0:** the probe table from a real sandbox; ONNX matches torch.
- **Phase 1:** the harness reproduces log 53; the per-piece table for T0–T3; the gate verdict in the engineering log.
- **Phase 2:**
  - `pytest tests/test_read_audio.py` and the robustness audio branch;
  - a fresh `dist/` from `tools/build_skill.py`;
  - the full claude.ai run with timings;
  - owner sign-off on screenshots and wording, and the Opus visual review passed.

## Effort
- Phase 0: 1–2 days.
- Phase 1: 2–3 weeks.
- Phase 2: 1.5–2 weeks plus review rounds.
- Phase 3: about 1 week, later.
- Cost:
  - Phases 0–2 cost nothing on Cloud Run.
  - T5 only with an approved one-off GPU spend.
  - No paid API use is planned.
