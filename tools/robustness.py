"""Run a varied set of classical scores through every stage and report what breaks.

    .venv/bin/python tools/robustness.py [--no-model] [--only NAME]

The scores come from the corpus bundled with music21, so nothing is copied into
this repository. For each score the stages are: read and index, note table,
note-list round trip, plain engraving, the draft model on the whole piece and on an
excerpt's note list, and rendering the model's unreviewed draft. Results are written
to out/robustness/report.json with one PNG per score.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
import urllib.request
from pathlib import Path

from music21 import corpus

from engine import draft, notes, reduce
from engine.annotate import check, render
from engine.render import engrave, load_toolkit
from engine.score import ScoreIndex

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out" / "robustness"
CORPUS = Path(os.path.dirname(corpus.__file__))

ASAP = "https://raw.githubusercontent.com/fosfrancesco/asap-dataset/master/"
MUSETRAINER = "https://raw.githubusercontent.com/musetrainer/library/master/scores/"

SCORES = {
    # name: (path in the music21 corpus, what it exercises)
    "bach-chorale-major": ("bach/bwv66.6.mxl", "four voices on four staves, pickup, fermatas"),
    "bach-chorale-minor": ("bach/bwv269.mxl", "four voices, minor key"),
    "mozart-quartet": ("mozart/k155/movement1.mxl", "string quartet, alto clef, repeats"),
    "beethoven-quartet": ("beethoven/opus18no1/movement2.mxl", "string quartet in 9/8, slow movement"),
    "haydn-quartet": ("haydn/opus74no1/movement1.mxl", "string quartet, long movement"),
    "schubert-song": ("schubert/Lindenbaum.xml", "voice and piano, lyrics, uncompressed file"),
    "schumann-song": ("schumann_robert/dichterliebe_no2.xml", "voice and piano, short"),
    "clara-schumann-piano": ("schumann_clara/polonaise_op1n1.mxl", "piano, several voices per staff"),
    "handel-aria": ("handel/rinaldo/Lascia_chio_pianga.mxl", "voice and orchestra reduction"),
    "corelli-trio-sonata": ("corelli/opus3no1/1grave.xml", "three parts with continuo"),
    "verdi-aria": ("verdi/laDonnaEMobile.mxl", "voice and piano, 3/8"),
    "weber-clarinet": ("weber/concertino_clarinet.mxl", "transposing instrument"),
    "cpe-bach-keyboard": ("cpebach/h186.mxl", "keyboard, ornaments"),
    "joplin-rag": ("joplin/maple_leaf_rag.mxl", "piano, repeats and endings, syncopation"),
    "beach-piano": ("beach/prayer_of_a_tired_child.musicxml", "piano with voice, late Romantic harmony"),
    "monteverdi-madrigal": ("monteverdi/madrigal.3.1.mxl", "five voices, early tonal"),
    "beethoven-grosse-fuge": ("beethoven/opus133.mxl", "very long, dense quartet"),
    # Impressionist and early twentieth-century piano music. Downloaded for local testing only and
    # never committed: the ASAP transcriptions are CC BY-NC-SA, the MuseTrainer ones public domain.
    "ravel-pavane": (ASAP + "Ravel/Pavane/xml_score.musicxml", "Ravel 1899: modal harmony, parallel chords"),
    "ravel-ondine": (ASAP + "Ravel/Gaspard_de_la_Nuit/1_Ondine/xml_score.musicxml", "Ravel 1908: dense figuration, three staves"),
    "ravel-barque": (ASAP + "Ravel/Miroirs/3_Une_Barque/xml_score.musicxml", "Ravel 1905: arpeggio washes, meter changes"),
    "ravel-alborada": (ASAP + "Ravel/Miroirs/4_Alborada_del_gracioso/xml_score.musicxml", "Ravel 1905: repeated notes, changing meters"),
    "debussy-reflets": (ASAP + "Debussy/Images_Book_1/1_Reflets_dans_lEau/xml_score.musicxml", "Debussy 1905: whole-tone and pentatonic passages"),
    "debussy-pour-le-piano": (ASAP + "Debussy/Pour_le_Piano/1/xml_score.musicxml", "Debussy 1901: toccata texture, glissandi"),
    "debussy-clair-de-lune": (MUSETRAINER + "Clair_de_lune_-_Claude_Debussy.mxl", "Debussy 1905: 9/8, extended chords"),
    "satie-gymnopedie": (MUSETRAINER + "Erik_Satie_-_Gymnopedie_No.1.mxl", "Satie 1888: major-seventh chords, modal"),
    "scriabin-etude": (ASAP + "Scriabin/Etudes_op_8/11/xml_score.musicxml", "Scriabin 1894: late-Romantic chromaticism"),
    "scriabin-sonata-5": (ASAP + "Scriabin/Sonatas/5/xml_score.musicxml", "Scriabin 1907: near-atonal, mystic chord"),
    "rachmaninoff-prelude": (ASAP + "Rachmaninoff/Preludes_op_32/5/xml_score.musicxml", "Rachmaninoff 1910: cross-rhythms"),
    "prokofiev-toccata": (ASAP + "Prokofiev/Toccata/xml_score.musicxml", "Prokofiev 1912: motoric, dissonant"),
    "schoenberg-op19-2": ("schoenberg/opus19/movement2.mxl", "Schoenberg 1911: atonal"),
    "schoenberg-op19-6": ("schoenberg/opus19/movement6.mxl", "Schoenberg 1911: atonal, very sparse"),
}


def fetch(name: str, url: str) -> bytes:
    """Download a test score once and keep it under out/, which is not committed."""
    cached = OUT / "scores" / f"{name}{Path(url).suffix}"
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as response:
            cached.write_bytes(response.read())
    return cached.read_bytes()


def stage(results: dict, name: str, function):
    started = time.time()
    try:
        value = function()
        results[name] = {"ok": True, "seconds": round(time.time() - started, 2)}
        if isinstance(value, dict):
            results[name].update(value)
        return value
    except Exception as error:  # the point is to collect every kind of failure
        results[name] = {
            "ok": False,
            "seconds": round(time.time() - started, 2),
            "error": f"{type(error).__name__}: {str(error)[:400]}",
            "where": traceback.format_exc().strip().splitlines()[-3].strip(),
        }
        return None


def summary(index: ScoreIndex) -> list:
    return [
        (m.number, m.length, [(e.staff, e.layer, e.onset, e.duration, e.pitch, e.grace, e.tied) for e in m.events if e.pitch])
        for m in index.measures
    ]


def run(name: str, with_model: bool) -> dict:
    path, exercises = SCORES[name]
    score = fetch(name, path) if path.startswith("https://") else (CORPUS / path).read_bytes()
    results: dict = {"path": path, "exercises": exercises}
    state: dict = {}

    def read():
        state["index"] = ScoreIndex(load_toolkit(score).getMEI())
        index = state["index"]
        numbers = [m.number for m in index.measures]
        return {
            "measures": len(numbers),
            "first": numbers[0],
            "last": numbers[-1],
            "duplicate_numbers": len(numbers) - len(set(numbers)),
            "notes": sum(1 for m in index.measures for e in m.events if e.pitch),
            "staves": max((e.staff for m in index.measures for e in m.events), default=0),
            "meter": index.meter,
            "key_signature": index.key_signature,
        }

    stage(results, "read", read)
    index = state.get("index")
    if index is None:
        return results
    first, last = index.measures[0].number, index.measures[min(len(index.measures), 9) - 1].number
    window = (max(first, 1), last)

    stage(results, "table", lambda: {"chars": len(reduce.as_text(index))})

    def round_trip():
        text = notes.encode(index)
        state["notes"] = text
        return {"chars": len(text), "identical": summary(notes.decode(text)) == summary(index)}

    stage(results, "note_list", round_trip)
    stage(results, "engrave", lambda: (OUT / f"{name}-plain.png").write_bytes(engrave(score, window).png(1)) and None)

    if with_model:
        def model():
            state["draft"] = d = draft.draft(index)
            return {"chords": len(d.chords), "cadences": len(d.cadences), "keys": sorted({c.key for c in d.chords}),
                    "non_chord_tones": len(d.non_chord_tones)}

        stage(results, "model", model)

        def model_on_excerpt():
            d = draft.draft_from_notes(notes.encode(index, *window))
            return {"chords": len(d.chords)}

        stage(results, "model_on_excerpt", model_on_excerpt)

        if "draft" in state:
            stage(results, "draft_resolves", lambda: check(draft.as_annotations(state["draft"]), index))

            def draw():
                page = render(score, draft.as_annotations(state["draft"], *window), measures=window)
                (OUT / f"{name}-draft.png").write_bytes(page.png(1, width=1600))
                return {"pages": page.page_count}

            stage(results, "render_draft", draw)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-model", action="store_true", help="skip the draft model stages")
    parser.add_argument("--only", action="append", help="run only this score (repeatable)")
    parser.add_argument("--matching", help="run the scores whose name contains this text")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for name in args.only or [name for name in SCORES if not args.matching or args.matching in name]:
        started = time.time()
        report[name] = run(name, not args.no_model)
        failed = [stage_name for stage_name, result in report[name].items() if isinstance(result, dict) and result.get("ok") is False]
        print(f"{name:26s} {time.time() - started:5.1f}s  " + ("ok" if not failed else "FAILED: " + ", ".join(failed)), flush=True)
    path = OUT / "report.json"
    merged = json.loads(path.read_text()) if path.exists() and (args.only or args.matching) else {}
    merged.update(report)
    path.write_text(json.dumps(merged, indent=1, default=str))


if __name__ == "__main__":
    main()
