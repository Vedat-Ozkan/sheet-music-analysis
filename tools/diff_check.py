"""Differential check: run the same inputs through a base git ref and the working tree, print what changed.

    python tools/diff_check.py --base <git-ref> AREA [AREA ...]      # e.g. --base main typed partwriting
    python tools/diff_check.py --base HEAD~3 all --limit 30

Areas (each maps an input name to a JSON-able output):
  typed        engine.check_analysis.from_text over tests/data/check_analysis/typed_inputs.json + tests/data/awkward/typed.txt
  partwriting  engine.part_writing findings (rule, bars, beats, voices) over tests/data/part_writing_*.musicxml + --limit Bach chorales
  pdfwarn      engine.read_pdf.problem_spots over the cached final Audiveris readings in the main checkout (read-only)
  export       engine.export.export_musicxml label placement (bar, beat, text) for scores + analyses already in tests/
  render       SHA-256 of the PNG of the 9 engraving pieces (tools/engraving_check.py) in 3 numeral styles, plus the mozart-41 piano reduction

The base ref is exported with `git archive` into a temp dir; each side runs in its own subprocess with PYTHONPATH set to
its tree. Fixtures always come from the working tree (and, for git-ignored ones, the main checkout), so both sides see
identical inputs. Changes are printed for a human to read and do NOT affect the exit code; the exit code is 1 only if a
side errored on some input (or a side's subprocess failed). ClarificationNeeded is a normal typed output, not an error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
AREAS = ("typed", "partwriting", "pdfwarn", "export", "render")


def main_checkout() -> Path:
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=HERE,
                                capture_output=True, text=True, check=True).stdout.strip()
        return Path(common).parent
    except Exception:
        return HERE


# ---------------------------------------------------------------- areas (run inside a worker, one side each)

def area_typed(args):
    from engine import check_analysis
    from_text = check_analysis.from_text
    # Older refs have no ClarificationNeeded; their questions were plain ValueErrors.
    ClarificationNeeded = getattr(check_analysis, "ClarificationNeeded", ValueError)
    cases = {f"json:{c['id']}": c["text"] for c in json.loads((HERE / "tests/data/check_analysis/typed_inputs.json").read_text())}
    for number, line in enumerate((HERE / "tests/data/awkward/typed.txt").read_text().splitlines(), 1):
        if line.strip():
            cases[f"awkward:{number}: {line}"] = line
    out = {}
    for name, text in cases.items():
        try:
            out[name] = [[x.measure, x.beat, x.key, x.figure] for x in from_text(text)]
        except ClarificationNeeded as e:
            out[name] = {"clarification": str(e)}
        except Exception as e:
            out[name] = {"__error__": f"{type(e).__name__}: {e}"}
    return out


def _findings(xml: bytes):
    from engine.part_writing import applies, check
    from engine.render import load_toolkit
    from engine.score import ScoreIndex
    index = ScoreIndex(load_toolkit(xml).getMEI())
    if not applies(index):
        return []
    return sorted([h.rule, list(h.bars), list(h.beats), [list(v) for v in h.voices]] for h in check(index))


def area_partwriting(args):
    out = {}
    for path in sorted((HERE / "tests/data").glob("part_writing_*.musicxml")):
        out[path.name] = _safe(lambda: _findings(path.read_bytes()))
    from music21 import corpus
    from music21.musicxml.m21ToXml import GeneralObjectExporter
    for filename in list(corpus.chorales.Iterator(returnType="filename"))[: args.limit]:
        out[f"corpus:{filename}"] = _safe(lambda: _findings(GeneralObjectExporter(corpus.parse(filename)).parse()))
    return out


def area_pdfwarn(args):
    from engine.read_pdf import problem_spots
    out = {}
    for path in sorted((main_checkout() / "spike/omr").glob("*/cache/runs/results-final--*.musicxml")):
        def one():
            bars, doubles = problem_spots(path.read_bytes())
            return {"bars": bars, "doubles": [list(d) for d in doubles]}
        out[f"{path.parents[2].name}/{path.name}"] = _safe(one)
    return out


def _placements(xml: bytes):
    """(bar, beat, text) of every Roman-numeral lyric and direction in the exported score, bottom part only."""
    from fractions import Fraction
    part = ET.fromstring(xml).findall("part")[-1]
    found, divisions, beat_type = [], 1, 4
    for measure in part.findall("measure"):
        divisions = int(measure.findtext("attributes/divisions") or divisions)
        beat_type = int(measure.findtext("attributes/time/beat-type") or beat_type)
        cursor, last = Fraction(0), Fraction(0)
        for element in measure:
            beat = lambda at: float(1 + at / divisions * Fraction(beat_type, 4))
            if element.tag == "note":
                lyric = [l for l in element.findall("lyric") if (l.get("name") or "").startswith("roman-analysis")]
                if lyric:
                    found.append([measure.get("number"), beat(cursor), " ".join(t.text or "" for t in lyric[0].findall("text"))])
                if element.find("grace") is None and element.find("chord") is None:
                    last = Fraction(element.findtext("duration") or 0)
                    cursor += last
            elif element.tag == "backup":
                cursor -= Fraction(element.findtext("duration"))
            elif element.tag == "forward":
                cursor += Fraction(element.findtext("duration"))
            elif element.tag == "direction" and element.findtext("direction-type/words"):
                found.append([measure.get("number"), beat(cursor + Fraction(element.findtext("offset") or 0)),
                              element.findtext("direction-type/words")])
    return found


def area_export(args):
    from engine.export import export_musicxml
    from engine.render import load_toolkit
    from engine.score import ScoreIndex
    data, main = HERE / "tests/data", main_checkout()
    placement = {"annotations": [
        {"type": "harmony", "at": {"measure": 1, "beat": 1}, "key": "G", "label": "V⁶⁵"},
        {"type": "harmony", "at": {"measure": 1, "beat": 2}, "label": "viiø7/V"},
        {"type": "harmony", "at": {"measure": 1, "beat": 3}, "key": "D", "label": "I"},
        {"type": "harmony", "at": {"measure": 1, "beat": 4}, "label": "V7"}]}
    cases = {"export_placement": (data / "export_placement.musicxml", placement),
             "chopin-nocturne-trivial": (data / "chopin_nocturne_op9_no2.mxl",
                                         {"annotations": [{"type": "harmony", "at": {"measure": 1, "beat": 2}, "label": "V65"}]})}
    for stem, score in [("debussy-clair", "export-debussy-clair.musicxml"), ("brahms-118-2", "export-brahms-118-2.musicxml"),
                        ("mozart-k458", "export-mozart-k458.musicxml")]:
        cases[stem] = (data / score, json.loads((HERE / f"examples/engraving/{stem}.json").read_text()))
        # the shipped excerpts are shorter than the reviewed analyses
        have = {m.number for m in ScoreIndex(load_toolkit(cases[stem][0].read_bytes()).getMEI()).measures}
        cases[stem][1]["annotations"] = [a for a in cases[stem][1]["annotations"] if a["type"] == "harmony" and a["at"]["measure"] in have]
    bach = main / "out/engraving/scores/bach-269.mxl"
    if bach.is_file():
        cases["bach-269"] = (bach, json.loads((HERE / "examples/engraving/bach-269.json").read_text()))
    return {name: _safe(lambda s=score, a=analysis: _placements(export_musicxml(s.read_bytes(), a)))
            for name, (score, analysis) in cases.items()}


def area_render(args):
    from engine.annotate import render
    from engine.annotations import AnnotationList
    from tools.engraving_check import PIECES
    scores = main_checkout() / "out/engraving/scores"
    out = {}
    for name, (source, bars) in PIECES.items():
        # The same cached copies on both sides; a network fetch would add a variable the check is not about.
        score = (source if isinstance(source, Path) else _cached(scores, name)).read_bytes()
        notes = AnnotationList.model_validate_json((HERE / f"examples/engraving/{name}.json").read_text())
        for style in ("current", "abrsm", "figured_bass"):
            styled = notes.model_copy(update={"style": style})
            # PNG hashes, not SVG: Verovio's element IDs differ from run to run.
            out[f"{name} {style}"] = _safe(lambda: hashlib.sha256(render(score, styled, measures=bars).png(1)).hexdigest())
    for name in ("mozart-41",):
        source, bars = PIECES[name]
        score = (source if isinstance(source, Path) else _cached(scores, name)).read_bytes()
        notes = AnnotationList.model_validate_json((HERE / f"examples/engraving/{name}.json").read_text())
        out[f"{name} piano"] = _safe(lambda: hashlib.sha256(render(score, notes, measures=bars, piano=True).png(1)).hexdigest())
    return out


def _cached(scores, name):
    found = next(scores.glob(f"{name}.*"), None)
    if found is None:
        raise SystemExit(f"render: no cached score for {name} in {scores}; run tools/engraving_check.py in the main checkout to fetch it")
    return found


def _safe(fn):
    try:
        return fn()
    except Exception as e:
        return {"__error__": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------- driver

def worker(area: str, out: str, args):
    import engine
    result = {"__engine__": str(Path(engine.__file__).resolve().parent), "outputs": globals()[f"area_{area}"](args)}
    Path(out).write_text(json.dumps(result))


def run_side(label: str, root: Path, area: str, args, scratch: Path) -> dict:
    out = scratch / f"{label}-{area}.json"
    env = dict(os.environ, PYTHONPATH=str(root))
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", area, "--out", str(out), "--limit", str(args.limit)],
                          cwd=root, env=env, capture_output=True, text=True)
    if proc.returncode or not out.exists():
        return {"failed": f"{label} {area} worker exited {proc.returncode}: {proc.stderr.strip()[-600:]}"}
    result = json.loads(out.read_text())
    if not result["__engine__"].startswith(str(root.resolve())):
        return {"failed": f"{label} imported engine from {result['__engine__']}, not {root}"}
    return result["outputs"]


def is_error(value) -> bool:
    return isinstance(value, dict) and "__error__" in value


def show(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def diff_lines(old, new) -> list[str]:
    if isinstance(old, list) and isinstance(new, list) and all(isinstance(x, list) for x in old + new):
        removed, added = [x for x in old if x not in new], [x for x in new if x not in old]
        if removed or added:
            return [f"    - {show(x)}" for x in removed] + [f"    + {show(x)}" for x in added]
    return [f"    old: {show(old)}", f"    new: {show(new)}"]


def compare(area: str, old: dict, new: dict) -> int:
    if "failed" in old or "failed" in new:
        for side, value in (("base", old), ("new", new)):
            if "failed" in value:
                print(f"== {area}: ERROR {value['failed']}")
        return 1
    names = list(dict.fromkeys([*old, *new]))
    changed = [n for n in names if old.get(n, "<absent>") != new.get(n, "<absent>")]
    errors = {side: sum(is_error(v) for v in outputs.values()) for side, outputs in (("base", old), ("new", new))}
    print(f"== {area}: {len(names)} inputs: {len(changed)} changed, {len(names) - len(changed)} unchanged, "
          f"errors base={errors['base']} new={errors['new']}")
    for name in changed:
        print(f"  CHANGED {name}")
        print("\n".join(diff_lines(old.get(name, "<absent>"), new.get(name, "<absent>"))))
    for side, outputs in (("base", old), ("new", new)):
        for name, value in outputs.items():
            if is_error(value):
                print(f"  ERROR ({side}) {name}: {value['__error__']}")
    return sum(errors.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base")
    parser.add_argument("areas", nargs="*", help=f"{', '.join(AREAS)} or all")
    parser.add_argument("--limit", type=int, default=60, help="Bach chorales for partwriting")
    parser.add_argument("--worker")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.out, args)
        return 0
    areas = list(AREAS) if "all" in args.areas else args.areas
    if not args.base or not areas or any(a not in AREAS for a in areas):
        parser.error(f"give --base and areas from: {', '.join(AREAS)}, all")
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        base = scratch / "base"
        base.mkdir()
        archive = subprocess.run(["git", "archive", args.base], cwd=HERE, capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(base)], input=archive, check=True)
        problems = 0
        for area in areas:
            problems += compare(area, run_side("base", base, area, args, scratch), run_side("new", HERE, area, args, scratch))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
