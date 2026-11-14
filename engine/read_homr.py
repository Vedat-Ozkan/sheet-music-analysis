from __future__ import annotations

import os
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from engine.read_pdf import NOTHING_READ, TIMEOUT, PdfReading, ReadError, clean_score, is_scan, joined, open_pdf, repaired

HOMR = "/opt/homr/bin/homr"
PAGE_WIDTH = 2480
READER = f"homr-0.7.1-width-{PAGE_WIDTH}"
RENDER_PAGES = Path(__file__).with_name("homr_pages.py")
TIMED = {"note", "backup", "forward"}


def read_pdf(data: bytes, homr: str = HOMR) -> PdfReading:
    pdf = open_pdf(data)
    pages, scan = len(pdf.pages), is_scan(pdf)
    deadline = time.monotonic() + TIMEOUT
    with tempfile.TemporaryDirectory(prefix="read_homr_") as work:
        source = Path(work) / "score.pdf"
        source.write_bytes(data)
        env = {"PATH": os.defpath, "HOME": work}
        subprocess.run([str(Path(homr).parent / "python"), "-I", str(RENDER_PAGES), str(source), work, str(PAGE_WIDTH)],
                       env=env, check=True, capture_output=True, timeout=TIMEOUT)
        passes, readings = [], {}
        for page in range(1, pages + 1):
            image = Path(work) / f"page-{page}.png"
            passes.append(_read_page(homr, image, page, env, deadline))
            if passes[-1]["outcome"] == "done":
                readings[page] = image.with_suffix(".musicxml").read_bytes()
    if not readings:
        timed_out = any(record["outcome"] == "timeout" for record in passes)
        raise ReadError("Reading this PDF took too long" if timed_out else NOTHING_READ, passes)
    return reading_from_pages(readings, pages, scan, passes)


def _read_page(homr: str, image: Path, page: int, env: dict, deadline: float) -> dict:
    started = time.monotonic()
    if started >= deadline:
        return {"page": page, "outcome": "timeout", "seconds": 0}
    record = {"page": page}
    try:
        run = subprocess.run([homr, str(image)], env=env, capture_output=True, timeout=deadline - started)
        if run.returncode != 0:
            record.update(outcome="failed", exit_code=run.returncode, problem=run.stderr.decode(errors="replace")[-300:])
        else:
            record["outcome"] = "done" if image.with_suffix(".musicxml").exists() else "no music"
    except subprocess.TimeoutExpired:
        record["outcome"] = "timeout"
    return {**record, "seconds": round(time.monotonic() - started, 1)}


def reading_from_pages(readings: dict[int, bytes], pages: int, scan: bool, passes: list[dict]) -> PdfReading:
    scores = {page: ET.fromstring(readings[page]) for page in sorted(readings)}
    scores = {page: score for page, score in scores.items() if score.find("part/measure") is not None}
    if not scores:
        raise ReadError(NOTHING_READ, passes)
    for score in scores.values():
        for measure in score.iter("measure"):
            regroup_voices(measure)
    skipped = [page for page in range(1, pages + 1) if page not in scores]
    return PdfReading(repaired(clean_score(joined(list(scores.values())))), pages, scan, skipped, passes)


@dataclass
class Onset:
    start: int
    length: int
    lane: tuple[str, str]
    items: list[ET.Element] = field(default_factory=list)

    @property
    def end(self) -> int:
        return self.start + self.length


def regroup_voices(measure: ET.Element) -> None:
    children = list(measure)
    timed = [position for position, child in enumerate(children) if child.tag in TIMED]
    if not timed:
        return
    body, after = children[timed[0]:], children[timed[-1] + 1:]
    onsets, waiting = _onsets(children[timed[0]:timed[-1] + 1])
    for child in body:
        measure.remove(child)
    _write_voices(measure, _voices(onsets), max((onset.end for onset in onsets), default=0), waiting)
    measure.extend(after)


def _onsets(elements: list[ET.Element]) -> tuple[list[Onset], list[ET.Element]]:
    onsets, waiting, cursor = [], [], 0
    for element in elements:
        if element.tag == "backup":
            cursor -= _duration(element)
        elif element.tag == "forward":
            cursor += _duration(element)
        elif element.tag != "note" or element.find("grace") is not None:
            waiting.append(element)
        elif element.find("chord") is not None and onsets:
            onsets[-1].items.append(element)
        else:
            lane = (element.findtext("staff", "1"), element.findtext("voice", "1"))
            onsets.append(Onset(cursor, _duration(element), lane, [*waiting, element]))
            waiting, cursor = [], cursor + _duration(element)
    return onsets, waiting


def _voices(onsets: list[Onset]) -> list[tuple[str, list[Onset]]]:
    lanes: dict[tuple[str, str], list[list[Onset]]] = {}
    for onset in sorted(onsets, key=lambda onset: onset.start):
        voices = lanes.setdefault(onset.lane, [])
        voice = next((voice for voice in voices if voice[-1].end <= onset.start), None)
        if voice is None:
            voice = []
            voices.append(voice)
        voice.append(onset)
    return [(staff, voice) for (staff, _), voices in sorted(lanes.items()) for voice in voices]


def _write_voices(measure: ET.Element, voices: list[tuple[str, list[Onset]]], end: int,
                  trailing: list[ET.Element]) -> None:
    cursor, number = 0, 1
    for number, (staff, voice) in enumerate(voices, start=1):
        if cursor:
            measure.append(_timed("backup", cursor))
        cursor = 0
        for onset in voice:
            if onset.start > cursor:
                measure.append(_timed("forward", onset.start - cursor, staff, str(number)))
            _append_in_voice(measure, onset.items, number)
            cursor = onset.end
    if cursor < end:
        measure.append(_timed("forward", end - cursor))
    _append_in_voice(measure, trailing, number)


def _append_in_voice(measure: ET.Element, items: list[ET.Element], number: int) -> None:
    for item in items:
        if item.find("voice") is not None:
            item.find("voice").text = str(number)
        measure.append(item)


def _timed(tag: str, length: int, staff: str | None = None, voice: str | None = None) -> ET.Element:
    element = ET.Element(tag)
    ET.SubElement(element, "duration").text = str(length)
    if voice:
        ET.SubElement(element, "voice").text = voice
        ET.SubElement(element, "staff").text = staff
    return element


def _duration(element: ET.Element) -> int:
    return int(element.findtext("duration"))
