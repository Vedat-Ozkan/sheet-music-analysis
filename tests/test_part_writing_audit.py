import json
from pathlib import Path

import pytest
from music21 import corpus
from music21.musicxml.m21ToXml import GeneralObjectExporter

from engine.part_writing import applies, check
from engine.render import load_toolkit
from engine.score import ScoreIndex

ENTRIES = json.loads((Path(__file__).parent / "data/reference/part_writing_audit.json").read_text())["entries"]
CHORALES = sorted({entry["chorale"] for entry in ENTRIES})


@pytest.fixture(scope="module")
def reported():
    found = {}
    paths = {(p.stem if p.suffix in (".mxl", ".xml") else p.name): p for p in corpus.getComposer("bach")}
    for chorale in CHORALES:
        index = ScoreIndex(load_toolkit(GeneralObjectExporter(corpus.parse(paths[chorale])).parse()).getMEI())
        found[chorale] = {(h.rule, tuple(h.bars), tuple(h.beats), tuple(tuple(v) for v in h.voices)) for h in check(index)} if applies(index) else set()
    return found


def test_reference_is_sizeable():
    assert sum(e["verdict"] == "real" for e in ENTRIES) >= 70
    assert sum(e["verdict"] == "checker bug" for e in ENTRIES) >= 10


@pytest.mark.parametrize("verdict", ["real", "checker bug"])
def test_audited_findings(reported, verdict):
    wrong = []
    for entry in ENTRIES:
        if entry["verdict"] != verdict:
            continue
        key = (entry["rule"], tuple(entry["bars"]), tuple(entry["beats"]), tuple(tuple(v) for v in entry["voices"]))
        if (key in reported[entry["chorale"]]) != (verdict == "real"):
            wrong.append(f'{entry["chorale"]} {entry["rule"]} bars {entry["bars"]} beats {entry["beats"]}')
    assert not wrong, f"{verdict} entries that {'vanished' if verdict == 'real' else 'came back'}: {wrong}"
