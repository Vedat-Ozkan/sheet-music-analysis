"""Draw analysed passages from five eras, two string quartets and two symphonies, and count collisions:
overlay labels against the music, and the music's own text (dynamics, words, lyrics, chord symbols)
against each other and the notes.

    .venv/bin/python -m tools.engraving_check [--tag NAME]

Each passage has a hand-checked annotation list in examples/engraving/, written the way
the skill writes them. Pages go to out/engraving/<tag>/ as PNG (the size the server sends)
and PDF, so a round of engraving changes can be looked at before and after. The count is a
first filter, not a verdict: a flagged label can look clear when zoomed in, and the pages
still need looking at.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from engine.annotate import render
from engine.annotations import AnnotationList
from engine.overlay import LABEL_PAD, Box, PageLayout
from tools.robustness import ASAP, CORPUS, MUSETRAINER, fetch

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out" / "engraving"
EXAMPLES = ROOT / "examples" / "engraving"
# Full orchestral scores, MIT-licensed: https://github.com/iis-mctl/mctl-symphony-dataset
MCTL = "https://raw.githubusercontent.com/iis-mctl/mctl-symphony-dataset/main/symbolic_symphony_set/"

PIECES = {
    # name: (score, printed bars)
    "bach-269": (CORPUS / "bach/bwv269.mxl", (0, 8)),
    "mozart-545": (MUSETRAINER + "Mozart_-_Piano_Sonata_No._16_-_Allegro.mxl", (1, 8)),
    "schubert-lindenbaum": (CORPUS / "schubert/Lindenbaum.xml", (9, 16)),
    "brahms-118-2": (ASAP + "Brahms/Six_Pieces_op_118/2/xml_score.musicxml", (0, 8)),
    "debussy-clair": (MUSETRAINER + "Clair_de_lune_-_Claude_Debussy.mxl", (1, 8)),
    "mozart-k458": (CORPUS / "mozart/k458/movement1.mxl", (0, 8)),
    "beethoven-59-1": (CORPUS / "beethoven/opus59no1/movement1.mxl", (1, 8)),
    "mozart-41": (MCTL + "mo1/sheet.xml", (1, 8)),
    "dvorak-9-2": (MCTL + "dv2/sheet.xml", (5, 12)),
}

# The overlay keeps no record of what it drew, so the check watches it draw: the boxes Verovio
# reported before any annotation, and every label drawn outside the numeral row.
_layouts: list[PageLayout] = []
_init, _text, _numerals = PageLayout.__init__, PageLayout._text, PageLayout._draw_harmonies


def _watch_init(self, svg, *args, **kwargs):
    _init(self, svg, *args, **kwargs)
    self.source = svg
    self.music = [box for system in self.systems for box in system.content]
    self.labels = []
    _layouts.append(self)


def _watch_text(self, x, y, string, size, **kwargs):
    box = _text(self, x, y, string, size, **kwargs)
    if kwargs.get("fill") != "#ffffff" and not getattr(self, "in_numerals", False):
        self.labels.append((string, box))
    return box


def _watch_numerals(self, *args, **kwargs):
    self.in_numerals = True
    try:
        return _numerals(self, *args, **kwargs)
    finally:
        self.in_numerals = False


PageLayout.__init__, PageLayout._text, PageLayout._draw_harmonies = _watch_init, _watch_text, _watch_numerals


def _touches(a: Box, b: Box, gap: float = 0.0) -> bool:
    return a.x - gap < b.right and a.right + gap > b.x and a.y - gap < b.bottom and a.bottom + gap > b.y


# Verovio's own placement: text it sets in the music, and what that text must keep clear of.
TEXT = {"dynam", "text", "harm", "syl", "fing", "reh"}  # words in dir, tempo and the like are boxed as "text"
SOLID = TEXT | {"note", "accid", "rest", "clef", "keySig", "meterSig", "artic", "stem", "flag", "dots"}
BBOX = re.compile(r'<g id="bbox-([^"]+)" class="(\w+) bounding-box">\s*<rect x="([-\d.]+)" y="([-\d.]+)" height="([-\d.]+)" width="([-\d.]+)"')
OVERLAP = 10  # Verovio units (a staff space is 180): less than this is boxes kissing, not ink touching


PARENT = re.compile(r'<g id="([^"]+)" class="(?:dir|tempo|dynam|harm|verse|fing|reh|mNum|label|labelAbbr)\b')


def _owner_kind(svg: str, at: int) -> str:
    start = svg.rfind('<g id="', 0, at)
    kind = re.match(r'<g id="[^"]+" class="(\w+)', svg[start:])
    return kind.group(1) if kind else ""


def music_collisions(svg: str, skip: frozenset[str] = frozenset()) -> list[str]:
    """Pairs like "dynam/text" for each text item or clef Verovio drew on top of another item. Needs an SVG
    rendered with svgBoundingBoxes. Boxes are rectangles, so a hit is a lead to look at, not proof."""
    parents = [(match.start(), match.group(1)) for match in PARENT.finditer(svg)]
    boxes = []
    for match in BBOX.finditer(svg):
        id, kind, x, y, h, w = match.groups()
        # Bar numbers' boxes come out unplaced (x near 0), so they would collide with every clef.
        if kind in SOLID and kind not in skip and not (kind == "text" and _owner_kind(svg, match.start()) == "mNum"):
            # The element a text box belongs to: one tempo mark is several boxes ("♩", "= 60").
            owner = next((pid for start, pid in reversed(parents) if start < match.start()), None) if kind == "text" else id
            boxes.append((kind, id, owner, float(x), float(y), float(x) + float(w), float(y) + float(h)))
    hits = []
    for i, (kind, id, owner, x0, y0, x1, y1) in enumerate(boxes):
        if kind not in TEXT and kind != "clef":
            continue
        for j, (other, _, other_owner, a0, b0, a1, b1) in enumerate(boxes):
            if j == i or other_owner == owner or (other in TEXT | {"clef"} and j < i):  # each pair once
                continue
            # A clef change is checked against the notes around it; a clef's box always reaches its own staff's stems.
            if kind == "clef" and other not in {"note", "accid", "rest"}:
                continue
            if min(x1, a1) - max(x0, a0) > OVERLAP and min(y1, b1) - max(y0, b0) > OVERLAP:
                hits.append(f"{kind}/{other} {id}")
    return hits


def check(name: str, tag: str, style: str = "current") -> dict:
    source, bars = PIECES[name]
    score = fetch(name, source) if isinstance(source, str) else source.read_bytes()
    annotations = AnnotationList.model_validate_json((EXAMPLES / f"{name}.json").read_text())
    annotations = annotations.model_copy(update={"style": style})
    _layouts.clear()
    page = render(score, annotations, measures=bars)
    folder = OUT / tag
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.png").write_bytes(page.png(1))
    (folder / f"{name}.pdf").write_bytes(page.pdf())
    return collisions(page.page_count)


def collisions(page_count: int) -> dict:
    """Check the recorded pages, including whole numeral labels rather than their stacked chunks."""
    overlapping, tight = [], []
    for layout in _layouts:
        labels = layout.labels + layout.harmony_labels
        for i, (string, box) in enumerate(labels):
            others = layout.music + [other for j, (_, other) in enumerate(labels) if j != i]
            if any(_touches(box, other) for other in others):
                overlapping.append(string)
            elif any(_touches(box, other, LABEL_PAD / 2) for other in others):
                tight.append(string)
    # Chord symbols on these pages are hidden placeholders that make room for the numerals.
    # The last layouts are the drawn pages; earlier ones only measured systems for line breaks.
    music = [hit for layout in _layouts[-page_count :] for hit in music_collisions(layout.source, frozenset({"harm"}))]
    return {"labels": sum(len(layout.labels) + len(layout.harmony_labels) for layout in _layouts), "overlapping": overlapping, "tight": tight, "music": music}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="latest", help="folder under out/engraving/ for this round's pages")
    parser.add_argument("--style", choices=("current", "abrsm", "figured_bass"), default="current")
    args = parser.parse_args()
    report = {name: check(name, args.tag, args.style) for name in PIECES}
    for name, result in report.items():
        print(f"{name:22s} labels {result['labels']:3d}  overlapping {result['overlapping'] or '-'}  tight {result['tight'] or '-'}  music {result['music'] or '-'}")
    print(
        f"total: {sum(len(r['overlapping']) for r in report.values())} overlapping, {sum(len(r['tight']) for r in report.values())} tight,"
        f" {sum(len(r['music']) for r in report.values())} music collisions"
    )
    (OUT / args.tag / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
