"""Engrave a MusicXML score with Verovio and rasterise the pages."""

from __future__ import annotations

import base64
import io
import os
import re
import zipfile
from dataclasses import dataclass
from fractions import Fraction
from importlib.resources import files
from xml.sax.saxutils import escape, unescape

import resvg_py
import verovio
from PIL import Image, ImageChops

from engine.reduce import midi
from engine.score import ScoreIndex
from engine.text import FONT_DIR, FONT_FILES, MAIN as TEXT_FONT

# Set before cairo first looks for a font, so the PDF uses the same fonts as the PNG.
os.environ.setdefault("FONTCONFIG_FILE", str(FONT_DIR / "fonts.conf"))

RESOURCE_PATH = str(files("verovio") / "data")
VEROVIO_OPTIONS = {
    "xmlIdChecksum": True,  # element IDs are repeatable across runs
    "svgViewBox": True,
    "pageWidth": 2100,
    "pageHeight": 2970,
    "scale": 40,
    "header": "none",
    "footer": "none",
    "breaks": "auto",
    # Staves that only rest are left out of a system, but never out of the first (see _tidy), as in a
    # printed score: the first system names every instrument. "auto" only condenses from page 2,
    # and an excerpt is one page.
    "condense": "encoded",
    # Verovio's half-unit default sets dynamics and directions against the notes they avoid.
    "defaultTopMargin": 1.0,
    "defaultBottomMargin": 1.0,
}


LARGE_SCORE_STAVES = 4  # more staves than a string quartet

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}

# MuseScore's short names for the standard parts, for files that give none. Later systems print
# them; leaving the names off there is a nineteenth-century habit, the handbook default is short names.
SHORT_NAMES = {
    "piano": "Pno.", "violin": "Vln.", "viola": "Vla.", "cello": "Vc.", "violoncello": "Vc.", "double bass": "D.B.",
    "contrabass": "Cb.", "bass": "B.", "soprano": "S.", "alto": "A.", "tenor": "T.", "baritone": "Bar.",
    "flute": "Fl.", "oboe": "Ob.", "clarinet": "Cl.", "bassoon": "Bsn.", "horn": "Hn.", "trumpet": "Tpt.",
    "trombone": "Trb.", "tuba": "Tba.", "timpani": "Timp.", "harp": "Hp.", "organ": "Org.", "guitar": "Gtr.",
    "harpsichord": "Hpsd.", "voice": "Vo.", "piccolo": "Picc.", "english horn": "E.H.",
}


class ScoreError(ValueError):
    """The input could not be read as a MusicXML score."""


@dataclass
class Engraving:
    svgs: list[str]

    @property
    def page_count(self) -> int:
        return len(self.svgs)

    def png(self, page: int = 1, width: int = 1400, colors: int = 128) -> bytes:
        """One page as a palette PNG, small enough to send inline in a chat."""
        image = self._raster(page, width)
        top, bottom = self._ink(image)
        image = image.crop((0, top, image.width, bottom))
        # Max-coverage keeps the few annotation colours exact; median cut spends the palette on greys.
        image = image.quantize(colors, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE)
        out = io.BytesIO()
        image.save(out, "PNG", optimize=True)
        return out.getvalue()

    def pdf(self) -> bytes:
        """All pages as one vector PDF at A4 width, trimmed like the PNG, so it prints and zooms sharp."""
        try:
            import cairosvg
            import pikepdf
        except (ImportError, OSError):
            # The skill's sandbox may lack the cairo library; an image PDF still prints.
            pages = [Image.open(io.BytesIO(self.png(page, width=2100))).convert("RGB") for page in range(1, self.page_count + 1)]
            out = io.BytesIO()
            pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=254)
            return out.getvalue()
        documents = []
        for page in range(1, self.page_count + 1):
            svg = self.svgs[page - 1]
            box = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', svg)
            x, y, w, h = map(float, box.groups())
            image = self._raster(page, round(w))
            top, bottom = self._ink(image)
            scale = h / image.height
            # The page goes inside a cropping frame; changing its own viewBox would rescale the nested music.
            page_svg = svg.replace("<svg ", f'<svg width="{w:g}" height="{h:g}" ', 1)
            if page_svg.startswith("<?xml"):
                page_svg = page_svg[page_svg.index("?>") + 2 :]
            trimmed = (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:g} {y + top * scale:g} {w:g} {(bottom - top) * scale:g}">'
                f"{page_svg}</svg>"
            )
            # cairosvg measures in CSS pixels, 0.75 pt each: 794 px is the 595 pt width of A4.
            documents.append(pikepdf.Pdf.open(io.BytesIO(cairosvg.svg2pdf(bytestring=trimmed.encode(), output_width=794))))
        merged = pikepdf.Pdf.new()
        for document in documents:
            merged.pages.extend(document.pages)
        out = io.BytesIO()
        merged.save(out)
        return out.getvalue()

    def _raster(self, page: int, width: int) -> Image.Image:
        raw = bytes(
            resvg_py.svg_to_bytes(
                svg_string=self.svgs[page - 1],
                background="#ffffff",
                width=width,
                # Verovio lays text out with Times metrics; Score Serif (Liberation Serif) matches them.
                skip_system_fonts=True,
                font_files=FONT_FILES,
                font_family=TEXT_FONT,
                serif_family=TEXT_FONT,
            )
        )
        return Image.open(io.BytesIO(raw)).convert("RGB")

    @staticmethod
    def _ink(image: Image.Image) -> tuple[int, int]:
        """Rows to keep: the music with a small margin, without the empty page above and below it.
        The width stays, so the scale matches across pages."""
        ink = ImageChops.difference(image, Image.new("RGB", image.size, "#ffffff")).getbbox()
        if not ink:
            return 0, image.height
        pad = round(image.width * 0.025)
        return max(ink[1] - pad, 0), min(ink[3] + pad, image.height)


def load_toolkit(score: bytes, options: dict | None = None) -> verovio.toolkit:
    """Load plain (.musicxml) or compressed (.mxl) MusicXML into a Verovio toolkit."""
    # Verovio's default resource path only applies on the main thread, so it is set per toolkit.
    toolkit = verovio.toolkit(False)
    toolkit.setResourcePath(RESOURCE_PATH)
    toolkit.setOptions({**VEROVIO_OPTIONS, **(options or {})})
    if score[:2] == b"PK":
        loaded = toolkit.loadZipDataBase64(base64.b64encode(score).decode())
    else:
        # Older notation programs write a byte-order mark, which Verovio rejects, or Latin-1 text.
        try:
            text = score.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = score.decode("latin-1")
        # Verovio guesses the format of anything else, and some files (a PDF read as Plaine & Easie) crash it,
        # taking the whole server down with it.
        if not re.search(r"<score-(?:partwise|timewise)\b", text[:5000]):
            raise ScoreError("This file is not MusicXML" + (" but a PDF" if score[:5] == b"%PDF-" else ""))
        loaded = toolkit.loadData(text)
    if not loaded:
        raise ScoreError("Verovio could not read this file as MusicXML")
    _tidy(toolkit, _readable_names(score))
    # The "//" between systems is for large scores, where the eye needs help finding where a system
    # starts; piano, song and chamber editions leave it out.
    if len(set(re.findall(r'<staffDef\b[^>]*\bn="(\d+)"', toolkit.getMEI()))) <= LARGE_SCORE_STAVES:
        toolkit.setOptions({"systemDivider": "none"})
        toolkit.redoLayout()
    return toolkit


def _tidy(toolkit: verovio.toolkit, names: dict[str, str]) -> None:
    """Engraving fixes Verovio does not make by itself, applied to its MEI."""
    mei = toolkit.getMEI()
    patched = mei
    # Verovio's staff ids are the MusicXML part ids.
    for part, name in names.items():
        patched = re.sub(rf'(<staffDef\b[^>]*xml:id="{re.escape(part)}"[^>]*>\s*<label\b[^>]*>)[^<]*', lambda m: m.group(1) + escape(name), patched)
    # MuseScore writes a flat in a part name as the symbol's name ("BaccidentalFlat Clarinet") and
    # escapes "&" twice ("Cl. 2 &amp;amp; 3"), so both print literally.
    patched = re.sub(
        r"<(label|labelAbbr)\b[^>]*>.*?</\1>",
        lambda m: re.sub(r"accidental(Flat|Sharp|Natural)", lambda a: {"Flat": "♭", "Sharp": "♯", "Natural": "♮"}[a.group(1)], m.group(0)).replace("&amp;amp;", "&amp;"),
        patched,
        flags=re.S,
    )
    # Verovio turns a chord symbol's root into ♭/♯ but prints a file's own kind text as typed ("Am7b5").
    patched = re.sub(
        r"<harm\b[^>]*>[^<]*</harm>",
        lambda m: re.sub(r"(?<=[^>])([b#])(?=1?\d)", lambda a: "♭" if a.group(1) == "b" else "♯", m.group(0)),
        patched,
    )
    # MusicXML implies a treble clef when a staff has none (MuseScore exports sometimes omit it); Verovio draws nothing.
    patched = re.sub(
        r"(<staffDef\b[^>]*?(?<!/)>)((?:(?!</staffDef>).)*?</staffDef>)",
        lambda m: m.group(0) if "<clef" in m.group(2) or "clef.shape" in m.group(1) else m.group(1) + '<clef shape="G" line="2" />' + m.group(2),
        patched,
        flags=re.S,
    )
    patched = re.sub(r'<staffDef\b(?![^>]*clef\.shape)([^>]*?)/>', r'<staffDef\1><clef shape="G" line="2" /></staffDef>', patched)
    # A clef followed at once by another is cancelled before any note, but Verovio draws both, one on the other.
    cancelled = re.findall(r'<clef\b[^>]*xml:id="([^"]+)"[^>]*/>(?=\s*<clef\b)', patched)
    for clef in cancelled:
        patched = re.sub(rf'<clef\b[^>]*(?:xml:id="{clef}"|sameas="#{clef}")[^>]*/>', "", patched)
    # Dynamics and hairpins of one staff share a vertical group, so Verovio sets them on one line
    # instead of stepping each one around its neighbours.
    # Files often give each mark its own group already, which would keep them apart, so it is replaced.
    patched = re.sub(
        r'<(dynam|hairpin)\b([^>]*?)\s*\bvgrp="[^"]*"([^>]*>)',
        r"<\1\2\3",
        patched,
    )
    patched = re.sub(
        r'<(dynam|hairpin)\b([^>]*?\bstaff="(\d+)")',
        lambda m: f'<{m.group(1)} vgrp="{900 + int(m.group(3))}"{m.group(2)}',
        patched,
    )
    patched = _short_names_and_bracket(patched)
    patched = re.sub(r"<scoreDef\b(?![^>]*\boptimize=)", '<scoreDef optimize="true"', patched, count=1)
    patched = _drop_title_text(patched)
    # Pedal brackets look like analysis brackets on an annotated page, so pedalling is left out.
    patched = re.sub(r"<pedal\b[^>]*/>", "", patched)
    # The same goes for pedal words ("Ped.", "Ped. simile", "*") that some files write as plain directions.
    patched = re.sub(r"<dir\b[^>]*>(?:(?!</dir>).)*?\bPed(?:al|\.)(?:(?!</dir>).)*?</dir>", "", patched, flags=re.S)
    # MuseScore stores a tempo's words and its metronome mark as separate runs with no space between.
    patched = re.sub(r"(<tempo\b[^>]*>(?:(?!</tempo>).)*?</rend>)\(", r"\1 (", patched, flags=re.S)
    patched = re.sub(r"<measure\b.*?</measure>", _end_hairpins_at_dynamics, patched, flags=re.S)
    patched = re.sub(r"<measure\b.*?</measure>", _join_words_to_dynamics, patched, flags=re.S)
    patched = re.sub(r"<measure\b.*?</measure>", _drop_duplicate_marks, patched, flags=re.S)
    patched = re.sub(r"<measure\b.*?</measure>", _merge_simultaneous_dynamics, patched, flags=re.S)
    patched = re.sub(r"<measure\b.*?</measure>", _unalign_crowded_dynamics, patched, flags=re.S)
    patched = _separate_hairpins(patched)
    patched = _repair_broken_ties(patched)
    patched = _drop_doubled_notes(patched)
    patched = _spread_ties(patched)
    patched = _slurs_to_chords(patched)
    patched = _clefs_before_barlines(patched)
    if patched != mei:
        toolkit.loadData(patched)


def _short_name(name: str) -> str:
    """Short name for a part name: "Violin 2" -> "Vln. II", "1st Violin" -> "Vln. I"."""
    name = re.sub(r"<[^>]+>", "", unescape(name)).strip()
    number = re.search(r"\b([1-4])(?:st|nd|rd|th)?\b|\b(I{1,3}|IV)\b", name)
    base = re.sub(r"\b(?:[1-4](?:st|nd|rd|th)?|I{1,3}|IV)\b|\bin [A-G][♭♯b#]?\b|[()]", " ", name).strip().lower()
    base = " ".join(base.split())
    short = SHORT_NAMES.get(base)
    if not short and base:
        # Plurals ("Violins") and names already short ("Cl.") fall back to the first word.
        word = base.split()[0]
        short = SHORT_NAMES.get(word) or SHORT_NAMES.get(word.removesuffix("s")) or (word.capitalize() if word.endswith(".") else word[:3].capitalize() + ".")
    if number and short:
        short += " " + (ROMAN.get(int(number.group(1))) if number.group(1) else number.group(2))
    return short or ""


def _short_names_and_bracket(mei: str) -> str:
    """Short names on later systems for every staff, and one bracket over a multi-staff score that groups none.

    Verovio prints a staff's <labelAbbr> on systems 2+ and nothing when there is none."""

    def add_abbr(match: re.Match) -> str:
        label, abbr = match.group(1), match.group(2)
        short = _short_name(label)
        # Audiveris writes the full name as the abbreviation, which would repeat "Piano" on every system.
        if not short or (abbr and re.sub(r"<[^>]+>", "", abbr).strip() != re.sub(r"<[^>]+>", "", label).strip()):
            return match.group(0)
        return label + f"<labelAbbr>{escape(short)}</labelAbbr>"

    # The label sits on a staff, or on the group of a piano's two staves.
    mei = re.sub(r"(<label\b[^>]*>.*?</label>)\s*(<labelAbbr\b[^>]*>.*?</labelAbbr>)?", add_abbr, mei, flags=re.S)
    # Piano and other grouped scores keep what the file defines (a piano's brace).
    if "<grpSym" not in mei and len(re.findall(r"<staffDef\b", mei)) > 2:
        mei = re.sub(r"(<staffGrp\b[^>]*?)>", r'\1 bar.thru="true"><grpSym symbol="bracket" />', mei, count=1)
    return mei


def _clefs_before_barlines(mei: str) -> str:
    """Move a clef change written before a bar's first note to the end of the bar before it.

    Verovio draws such a clef full size after the barline; print sets it small before the barline,
    which is where Verovio puts a clef that ends a bar. Only one-voice staves are moved: other voices
    hold copies of the clef."""
    texts = re.findall(r"<measure\b.*?</measure>", mei, flags=re.S)
    staff = r'<staff\b[^>]*\bn="{}"[^>]*>.*?</staff>'
    for i in range(1, len(texts)):
        for body in re.findall(r"<staff\b.*?</staff>", texts[i], flags=re.S):
            n = re.search(r'\bn="(\d+)"', body).group(1)
            previous = re.search(staff.format(n), texts[i - 1], flags=re.S)
            leading = re.match(r"(.*?)(<clef\b[^>]*/>)", body, flags=re.S)
            if (
                not previous
                or not leading
                or re.search(r"<(note|rest|chord|space|mRest|mSpace)\b", leading.group(1))
                or len(re.findall(r"<layer\b", body)) != 1
                or len(re.findall(r"<layer\b", previous.group(0))) != 1
            ):
                continue
            texts[i] = texts[i].replace(body, body.replace(leading.group(2), "", 1), 1)
            moved = re.sub(r"(</layer>\s*</staff>)$", lambda m: leading.group(2) + m.group(1), previous.group(0))
            texts[i - 1] = texts[i - 1][: previous.start()] + moved + texts[i - 1][previous.end() :]
    parts = re.split(r"<measure\b.*?</measure>", mei, flags=re.S)
    return "".join(part + text for part, text in zip(parts, texts)) + parts[-1]


def _drop_title_text(mei: str) -> str:
    """Remove text in the music that names the piece or its composer.

    Some files write the title block as ordinary directions over the first bars (MuseScore pages
    do this), which then print inside the music; the page around our excerpt already says what it is."""
    head = mei[: mei.find("</meiHead>")]
    names = [unescape(name).strip() for name in re.findall(r"<(?:title|persName)\b[^>]*>([^<]+)<", head)]

    def drop(match: re.Match) -> str:
        text = " ".join(unescape(re.sub(r"<[^>]+>", " ", match.group(0))).split())
        heading = re.fullmatch(r"Movement [IVX\d]+", text)
        return "" if heading or any(name and name in text for name in names) else match.group(0)

    return re.sub(r"<dir\b.*?</dir>", drop, mei, flags=re.S)


def _readable_names(score: bytes) -> dict[str, str]:
    """Names to print for parts named like identifiers ("oboe1", "piccolotrumpet2"), by part id.

    Such files keep the readable name in <instrument-name>, which Verovio does not import."""
    if score[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(score)) as archive:
            root = re.search(rb'full-path="([^"]+)"', archive.read("META-INF/container.xml"))
            score = archive.read(root.group(1).decode()) if root else b""
    text = score.decode("utf-8", errors="replace")
    names = {}
    for part in re.finditer(r'<score-part\b[^>]*\bid="([^"]+)"(.*?)</score-part>', text, flags=re.S):
        label = re.search(r"<part-name\b[^>]*>\s*([a-z]+)(\d*)\s*</part-name>", part.group(2))
        instrument = re.search(r"<instrument-name>([^<]+)</instrument-name>", part.group(2))
        if not label or not instrument:
            continue
        name = re.sub(r"^([A-G][♭♯b#]?) (.+)$", r"\2 in \1", instrument.group(1).strip())  # "A Clarinet" -> "Clarinet in A"
        if label.group(2):
            number = ROMAN.get(int(label.group(2)), label.group(2))
            name = name.replace(" in ", f" {number} in ", 1) if " in " in name else f"{name} {number}"
        names[part.group(1)] = name
    return names


def _end_hairpins_at_dynamics(measure: re.Match) -> str:
    """A hairpin that runs past a dynamic on its own line would be drawn through it; it stops there instead."""
    text = measure.group(0)
    dynamics = [(staff, float(beat)) for staff, beat in re.findall(r'<dynam\b(?=[^>]*\bstaff="(\d+)")(?=[^>]*\btstamp="([\d.]+)")', text)]

    def shorten(match: re.Match) -> str:
        tag = match.group(0)
        staff, begin = re.search(r'\bstaff="(\d+)"', tag), re.search(r'\btstamp="([\d.]+)"', tag)
        finish = re.search(r'\btstamp2="0m\+([\d.]+)"', tag)
        if not (staff and begin and finish):
            return tag
        inside = [beat for s, beat in dynamics if s == staff.group(1) and float(begin.group(1)) < beat < float(finish.group(1))]
        if not inside:
            return tag
        return tag.replace(finish.group(0), f'tstamp2="0m+{min(inside):g}"')

    return re.sub(r"<hairpin\b[^>]*/>", shorten, text)


def _join_words_to_dynamics(measure: re.Match) -> str:
    """A word written just after a dynamic under the same staff ("p dolce") becomes part of it.

    Verovio sets the word as a separate direction at its own height, so the two read as unrelated."""
    text = measure.group(0)
    for dynam in re.finditer(r'<dynam\b(?=[^>]*\bplace="below")(?=[^>]*\bstaff="(\d+)")(?=[^>]*\btstamp="([\d.]+)")[^>]*>([^<]+)</dynam>', text):
        staff, beat = dynam.group(1), float(dynam.group(2))
        for word in re.finditer(r'<dir\b(?=[^>]*\bplace="below")[^>]*>\s*(?:<rend\b[^>]*>)?\s*([a-zà-ÿ][a-zà-ÿ. ]*)(?:</rend>)?\s*</dir>', text):
            at = re.search(r'\btstamp="([\d.]+)"', word.group(0))
            if f'staff="{staff}"' in word.group(0) and at and beat <= float(at.group(1)) <= beat + 1:
                joined = dynam.group(0).replace(f">{dynam.group(3)}</dynam>", f">{dynam.group(3)} {word.group(1).strip()}</dynam>")
                return text.replace(word.group(0), "", 1).replace(dynam.group(0), joined, 1)
    return text


def _drop_duplicate_marks(measure: re.Match) -> str:
    """The same chord symbol, word or dynamic written twice at one spot prints as one heavy smudge
    (some uploaded files repeat a chord symbol five times), so only the first is kept."""
    seen = set()

    def keep_first(mark: re.Match) -> str:
        key = re.sub(r'\s*xml:id="[^"]*"', "", re.sub(r'\s+xml:id="[^"]*"', "", mark.group(0)))
        key = re.sub(r"\s+", " ", key)
        if key in seen:
            return ""
        seen.add(key)
        return mark.group(0)

    return re.sub(r"<(harm|dir|dynam|tempo)\b[^>]*>.*?</\1>", keep_first, measure.group(0), flags=re.S)


def _merge_simultaneous_dynamics(measure: re.Match) -> str:
    """Two dynamics on one staff at one moment ("p" and "cresc.") become one: "p cresc.".

    They share a vertical group (see _tidy), so Verovio draws them at the same spot, one over the other."""
    text = measure.group(0)
    groups: dict[tuple[str, str, str], list[re.Match]] = {}
    for dynam in re.finditer(r"<dynam\b[^>]*>.*?</dynam>", text, flags=re.S):
        tag = dynam.group(0)[: dynam.group(0).index(">")]
        key = tuple((re.search(rf'\b{name}="([^"]*)"', tag) or [None, ""])[1] for name in ("staff", "tstamp", "place"))
        groups.setdefault(key, []).append(dynam)
    for marks in groups.values():
        if len(marks) < 2:
            continue
        # The mark with a value (p, mp) comes first, the words after it.
        marks.sort(key=lambda mark: 'val="' not in mark.group(0)[: mark.group(0).index(">")])
        first = marks[0].group(0)
        inner = " ".join(re.sub(r"^<dynam\b[^>]*>|</dynam>$", "", mark.group(0)).strip() for mark in marks)
        text = text.replace(first, first[: first.index(">") + 1] + inner + "</dynam>", 1)
        for mark in marks[1:]:
            text = text.replace(mark.group(0), "", 1)
    return text


def _unalign_crowded_dynamics(measure: re.Match) -> str:
    """A dynamic less than a beat after the one before it on its staff ("mp" then "ff") leaves the
    shared line: there is seldom room for both side by side, and on one line they print over each other.
    Out of the group, Verovio sets it just clear of its neighbour."""
    text = measure.group(0)
    last: dict[str, float] = {}
    for dynam in re.finditer(r'<dynam\b(?=[^>]*\bvgrp=")(?=[^>]*\bstaff="(\d+)")(?=[^>]*\btstamp="([\d.]+)")[^>]*>', text):
        staff, beat = dynam.group(1), float(dynam.group(2))
        if staff in last and beat - last[staff] < 1:
            text = text.replace(dynam.group(0), re.sub(r'\s*\bvgrp="[^"]*"', "", dynam.group(0)), 1)
        last[staff] = beat
    return text


def _separate_hairpins(mei: str) -> str:
    """A hairpin that ends where the next one on its staff begins stops half a beat short.

    Verovio draws the two end to end, so a crescendo and the diminuendo after it read as one
    closed diamond; printed editions leave a gap between them."""
    measures = re.findall(r"<measure\b.*?</measure>", mei, flags=re.S)
    starts = {
        (position, staff, float(beat))
        for position, measure in enumerate(measures)
        for staff, beat in re.findall(r'<hairpin\b(?=[^>]*\bstaff="(\d+)")(?=[^>]*\btstamp="([\d.]+)")', measure)
    }

    def shorten(position: int, tag: str) -> str:
        staff = re.search(r'\bstaff="(\d+)"', tag)
        finish = re.search(r'\btstamp2="(\d+)m\+([\d.]+)"', tag)
        if not staff or not finish:
            return tag
        bars, beat = int(finish.group(1)), float(finish.group(2))
        if (position + bars, staff.group(1), beat) not in starts or beat - 0.5 < 1:
            return tag
        return tag.replace(finish.group(0), f'tstamp2="{bars}m+{beat - 0.5:g}"')

    for position, measure in enumerate(measures):
        mei = mei.replace(measure, re.sub(r"<hairpin\b[^>]*/>", lambda m: shorten(position, m.group(0)), measure), 1)
    return mei


def _drop_doubled_notes(mei: str) -> str:
    """Keep one copy of a cross-staff note or chord that the other staff also writes at that moment.

    Some files write such a chord on both staves; Verovio draws both, so the noteheads and ties are
    doubled. Usually the cross-staff copy goes and only its beam is lost. When the file hid the
    stem of the staff's own copy, the cross-staff copy is the one it shows, beam and all: that copy
    stays, and the staff's own copy goes with any rest the beam passes over, as in print. The ties,
    slurs and written accidentals of the copy that goes pass to the one that stays."""
    index = ScoreIndex(mei)
    playing = {(m.number, e.staff, e.onset, e.pitch): e.id for m in index.measures for e in m.events if e.pitch}
    events = {e.id: (m.number, e.onset, e.pitch, e.staff) for m in index.measures for e in m.events}
    rests = {(m.number, e.staff, e.layer, e.onset): e.id for m in index.measures for e in m.events if not e.pitch}
    layers = {e.id: e.layer for m in index.measures for e in m.events}
    moved: dict[str, str] = {}  # silenced id -> the id that stands for it
    accidentals: dict[str, str] = {}  # kept note -> accidental the copy wrote out
    hidden: set[str] = set()  # the staff's own copies that go, and the rests under their beams

    def silence(match: re.Match) -> str:
        element, target = match.group(0), int(match.group(4))
        notes = re.findall(r'<note\b[^>]*xml:id="([^"]+)"[^>]*?(?:/>|>(.*?)</note>)', element, flags=re.S)
        if not notes or not all(
            id in events and events[id][3] != target and (events[id][0], target, events[id][1], events[id][2]) in playing for id, _ in notes
        ):
            return element
        copies = [playing[(events[id][0], target, events[id][1], events[id][2])] for id, _ in notes]
        own = re.search(rf'<chord\b[^>]*xml:id="([^"]+)"[^>]*>((?:(?!</chord>).)*?xml:id="{re.escape(copies[0])}".*?)</chord>', mei, flags=re.S)
        beam = re.search(rf'<beamSpan\b[^>]*startid="#([^"]+)"[^>]*endid="#{re.escape(match.group(3))}"', mei)
        if own and beam and 'stem.visible="false"' in own.group(0)[: own.group(0).index(">")] and sorted(
            re.findall(r'<note\b[^>]*xml:id="([^"]+)"', own.group(2))
        ) == sorted(copies):
            hidden.add(own.group(1))
            moved[own.group(1)] = match.group(3)
            for (id, _), copy in zip(notes, copies):
                moved[copy] = id
            measure, onset = events[copies[0]][0], events[copies[0]][1]
            first = events[beam.group(1)][1] if beam.group(1) in events else onset
            hidden.update(id for (m, staff, l, at), id in rests.items() if (m, staff, l) == (measure, target, layers[copies[0]]) and first <= at < onset)
            return element
        for id, body in notes:
            kept = playing[(events[id][0], target, events[id][1], events[id][2])]
            moved[id] = kept
            written = re.search(r'<accid\b[^>]*\baccid="([^"]+)"', body or "") or re.search(
                rf'<note\b[^>]*xml:id="{re.escape(id)}"[^>]*\baccid="([^"]+)"', element
            )
            if written:
                accidentals[kept] = written.group(1)
        moved[match.group(3)] = moved[notes[0][0]]
        return _space(match.group(1))

    # Only the chord or note that carries the other staff's number moves; the notes it repeats stay.
    patched = re.sub(
        r'(<(chord|note)\b(?=[^>]*xml:id="([^"]+)")(?=[^>]*\bstaff="(\d+)")[^>]*?)(?:/>|>.*?</\2>)',
        silence,
        mei,
        flags=re.S,
    )
    patched = re.sub(
        r'(<(chord|rest)\b(?=[^>]*xml:id="([^"]+)")[^>]*?)(?:/>|>.*?</\2>)',
        lambda match: _space(match.group(1)) if match.group(3) in hidden else match.group(0),
        patched,
        flags=re.S,
    )
    for old, new in moved.items():
        if old not in hidden:
            patched = re.sub(rf'<beamSpan\b[^>]*"#{re.escape(old)}"[^>]*/>', "", patched)
        patched = re.sub(rf'(<(?:tie|slur)\b[^>]*(?:startid|endid)=)"#{re.escape(old)}"', rf'\1"#{new}"', patched)
    # Both copies often carried the same slur or tie; keep one.
    seen: set[tuple[str, ...]] = set()

    def once(match: re.Match) -> str:
        key = (match.group(1), *re.findall(r'(?:startid|endid)="([^"]+)"', match.group(0)))
        if key in seen or (len(key) == 3 and key[1] == key[2]):
            return ""
        seen.add(key)
        return match.group(0)

    patched = re.sub(r"<(tie|slur)\b[^>]*/>", once, patched)
    for id, accid in accidentals.items():
        if re.search(rf'<note\b[^>]*xml:id="{re.escape(id)}"[^>]*>\s*<accid\b[^>]*\baccid=', patched):
            continue
        patched = re.sub(rf'<note\b(?![^>]*\baccid=)(?=[^>]*xml:id="{re.escape(id)}")', f'<note accid="{accid}"', patched, count=1)
    # Such files hide the stem of the copy that stays, since the other copy drew one.
    for id in set(moved.values()):
        patched = re.sub(
            rf'(<chord\b[^>]*?)\s+stem\.visible="false"([^>]*>(?:(?!</chord>).)*?xml:id="{re.escape(id)}")', r"\1\2", patched, flags=re.S
        )
    return patched


def _spread_ties(mei: str) -> str:
    """Ties from notes struck together on a staff curve away from each other: the highest above, the lowest below.

    Verovio curves a tie away from its note's stem, so ties from different voices whose stems point
    at each other, or from a chord drawn on the other staff, bend into the same space and cross."""
    index = ScoreIndex(mei)
    events = {e.id: e for m in index.measures for e in m.events if e.pitch}
    drawn_on = {
        id: int(match.group(2))
        for match in re.finditer(r'<(chord|note)\b[^>]*\bstaff="(\d+)"(?:[^>]*/>|.*?</\1>)', mei, flags=re.S)
        for id in re.findall(r'xml:id="([^"]+)"', match.group(0))
    }
    groups: dict[tuple, list[tuple[int, str]]] = {}
    for tie, first in re.findall(r'<tie\b(?![^>]*curvedir)[^>]*xml:id="([^"]+)"[^>]*startid="#([^"]+)"', mei):
        if first in events:
            note = events[first]
            groups.setdefault((note.measure, drawn_on.get(first, note.staff), note.onset), []).append((midi(note.pitch), tie))
    for ties in groups.values():
        if len(ties) < 2:
            continue
        ties.sort()
        for (_, tie), side in ((ties[0], "below"), (ties[-1], "above")):
            mei = mei.replace(f'<tie xml:id="{tie}"', f'<tie xml:id="{tie}" curvedir="{side}"', 1)
    return mei


def _slurs_to_chords(mei: str) -> str:
    """A slur on one note of a chord is attached to the whole chord.

    MusicXML puts a chord's slur on its first note, often the lowest; Verovio then starts a slur
    above the chord from inside it, where it cannot clear the notes beside it. On the chord,
    Verovio uses the outer note on the slur's side."""
    chord_of = {
        note: chord.group(1)
        for chord in re.finditer(r'<chord\b[^>]*xml:id="([^"]+)"[^>]*>(.*?)</chord>', mei, flags=re.S)
        for note in re.findall(r'<note\b[^>]*xml:id="([^"]+)"', chord.group(2))
    }

    def retarget(tag: re.Match) -> str:
        return re.sub(r'\b(startid|endid)="#([^"]+)"', lambda m: f'{m.group(1)}="#{chord_of.get(m.group(2), m.group(2))}"', tag.group(0))

    return re.sub(r"<slur\b[^>]*/>", retarget, mei)


def _space(start_tag: str) -> str:
    length = " ".join(re.findall(r'\b(?:dur|dots)="[^"]+"', start_tag))
    return f"<space {length} />"


def _repair_broken_ties(mei: str) -> str:
    """Reconnect or remove ties that run backwards or skip past the next bar.

    MuseScore sometimes exports a tie whose end is lost, and Verovio then ties the note to the next
    one of that pitch, however many bars later, drawing a long line across the staff. Such a tie is
    moved to the next note of its pitch on its staff within the following bar, and removed if there
    is none. A tie with a short gap inside a bar is kept: piano music ties across voices that way."""
    index = ScoreIndex(mei)
    start, bar, events = {}, {}, {}
    time = Fraction(0)
    for position, measure in enumerate(index.measures):
        for event in measure.events:
            start[event.id], bar[event.id], events[event.id] = time + event.onset, position, event
        time += measure.length

    def repair(match: re.Match) -> str:
        tag = match.group(0)
        ids = re.findall(r'(?:startid|endid)="#([^"]+)"', tag)
        if len(ids) != 2 or not all(id in start for id in ids):
            return tag
        first, last = ids
        if start[first] < start[last] and bar[last] <= bar[first] + 1:
            return tag
        note = events[first]
        following = [
            id for id, event in events.items()
            if event.staff == note.staff and event.pitch == note.pitch and start[id] > start[first] and bar[id] <= bar[first] + 1
        ]
        if not following:
            return ""
        return tag.replace(f'endid="#{last}"', f'endid="#{min(following, key=start.get)}"')

    return re.sub(r"<tie\b[^>]*/>", repair, mei)


def incoming_ties(toolkit: verovio.toolkit, index: ScoreIndex, first: int, *, include_pickup: bool = True) -> set[str]:
    """Ids of the ties into an excerpt from a bar before it."""
    start = int(index.measure_range(first, first, include_pickup=include_pickup).split("-")[0])
    earlier = {e.id for m in index.measures if m.last_index < start for e in m.events}
    return {
        tie for tie, note in re.findall(r'<tie\b[^>]*xml:id="([^"]+)"[^>]*startid="#([^"]+)"', toolkit.getMEI()) if note in earlier
    }


SPACE = 180  # one staff space in Verovio's SVG units


def shorten_ties(svg: str, ties: set[str]) -> str:
    """Draw ties coming into an excerpt as a short arc that ends on the held note.

    Verovio starts them at the time signature, so the arc seems to grow out of the "C"; a printed
    excerpt shows a short tie clear of it, which still tells the reader the note is held over."""

    def shorten(match: re.Match) -> str:
        if match.group(1) not in ties:
            return match.group(0)
        xs = [float(x) for x in re.findall(r"([-\d.]+),[-\d.]+", match.group(2))]
        left, right = min(xs), max(xs)
        start = max(left + SPACE * 3 / 4, right - 2 * SPACE)
        if right - left <= 0 or start >= right:
            return match.group(0)
        scale = (right - start) / (right - left)
        path = re.sub(r"([-\d.]+),([-\d.]+)", lambda p: f"{right + (float(p.group(1)) - right) * scale:.0f},{p.group(2)}", match.group(2))
        return match.group(0).replace(match.group(2), path)

    # A tie whose start is outside the excerpt is drawn as a "spanning" group named by class, not id.
    return re.sub(r'<g class="tie id-([^" ]+) spanning">(?:\s*<g id="bbox-[^"]*"[^>]*>.*?</g>)?\s*<path d="([^"]+)"', shorten, svg, flags=re.S)


def engrave(score: bytes, measures: tuple[int, int] | None = None, *, include_pickup: bool = True) -> Engraving:
    """Engrave the score or a cropped range, including the pickup at 1 by default."""
    if not measures:
        toolkit = load_toolkit(score)
    else:
        toolkit = load_toolkit(score, {"adjustPageHeight": True, "pageHeight": 60000})
        index = ScoreIndex(toolkit.getMEI())
        ties = incoming_ties(toolkit, index, measures[0], include_pickup=include_pickup)
        toolkit.select({"measureRange": index.measure_range(*measures, include_pickup=include_pickup)})
        toolkit.redoLayout()
        return Engraving([shorten_ties(toolkit.renderToSVG(page), ties) for page in range(1, toolkit.getPageCount() + 1)])
    return Engraving([toolkit.renderToSVG(page) for page in range(1, toolkit.getPageCount() + 1)])


def engrave_pages(score: bytes, measures: tuple[int, int]) -> Engraving:
    """Printed measures first..last on ordinary pages, a few systems each, for someone to read.

    `engrave` puts an excerpt on one tall page, which an image viewer shrinks until it cannot be read."""
    toolkit = load_toolkit(score)
    index = ScoreIndex(toolkit.getMEI())
    ties = incoming_ties(toolkit, index, measures[0])
    toolkit.select({"measureRange": index.measure_range(*measures)})
    toolkit.redoLayout()
    return Engraving([shorten_ties(toolkit.renderToSVG(page), ties) for page in range(1, toolkit.getPageCount() + 1)])
