from __future__ import annotations

import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fractions import Fraction
from importlib.resources import files
from xml.sax.saxutils import escape, unescape

import resvg_py
import verovio
from PIL import Image, ImageChops

from engine.reduce import midi
from engine.score import TOLERANCE, PositionError, ScoreIndex
from engine.text import FONT_DIR, FONT_FILES, MAIN as TEXT_FONT

os.environ.setdefault("FONTCONFIG_FILE", str(FONT_DIR / "fonts.conf"))

RESOURCE_PATH = str(files("verovio") / "data")
VEROVIO_OPTIONS = {
    "xmlIdChecksum": True,
    "svgViewBox": True,
    "pageWidth": 2100,
    "pageHeight": 2970,
    "scale": 40,
    "header": "none",
    "footer": "none",
    "breaks": "auto",
    "condense": "encoded",
    "defaultTopMargin": 1.0,
    "defaultBottomMargin": 1.0,
}


LARGE_SCORE_STAVES = 4

BRACKET_MAX_STAVES = 5

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}

_SHORT_NAME_SOURCE = {
    "Vln.": "violin, violino, violini, violine, violinen, violon, violons, violins",
    "Vla.": "viola, viole, bratsche, bratschen, violas",
    "Vc.": "cello, violoncello, violoncelli, violoncelle, violoncelles, violoncellos, cellos",
    "D.B.": "double bass, double basses, contrabass, contrabasses, contrabasso, contrabbasso, contrabbassi, kontrabass, contrebasse",
    "Fl.": "flute, flauto, flauti, flöte, flöten, flûte, flûtes, flutes",
    "Picc.": "piccolo, flauto piccolo, kleine flöte, petite flûte",
    "Ob.": "oboe, oboi, oboen, hautbois, oboes",
    "E.H.": "english horn, cor anglais, corno inglese, englischhorn",
    "Cl.": "clarinet, clarinetto, clarinetti, klarinette, klarinetten, clarinette, clarinettes, clarinets",
    "B. Cl.": "bass clarinet, clarinetto basso, bassklarinette, clarinette basse",
    "Bsn.": "bassoon, fagotto, fagotti, fagott, fagotte, basson, bassons, bassoons",
    "Cbsn.": "contrabassoon, contrafagotto, kontrafagott, contrebasson",
    "Hn.": "horn, horns, corno, corni, waldhorn, waldhörner, hörner, cor, cors, french horn, french horns",
    "Tpt.": "trumpet, trumpets, tromba, trombe, trompete, trompeten, trompette, trompettes",
    "Trb.": "trombone, trombones, tenor trombone, trombone tenore, tromboni, posaune, posaunen",
    "B. Trb.": "bass trombone, trombone basso, bassposaune",
    "Tba.": "tuba",
    "Timp.": "timpani, timpano, timbales, pauken",
    "Hp.": "harp, arpa, harfe, harpe",
    "Org.": "organ, organo, orgel, orgue",
    "Gtr.": "guitar, chitarra, gitarre, guitare",
    "Hpsd.": "harpsichord, clavicembalo, cembalo, clavecin",
    "Pno.": "piano, pianoforte, klavier",
    "S.": "soprano, sopran, s, s.",
    "A.": "alto, contralto, a, a.",
    "T.": "tenor, tenore, t, t.",
    "B.": "bass, basso, bassus, b, b.",
    "Bar.": "baritone, baritono, bariton",
    "Vo.": "voice, voices, vocals, vocalist",
    "Ch.": "choir, chorus, coro, chor, choeur",
    "S. Sax.": "soprano saxophone, soprano sax",
    "A. Sax.": "alto saxophone, alto sax",
    "T. Sax.": "tenor saxophone, tenor sax",
    "B. Sax.": "baritone saxophone, baritone sax",
    "Rec.": "recorder, recorders",
    "Cel.": "celesta",
}
SHORT_NAMES = {name: abbr for abbr, names in _SHORT_NAME_SOURCE.items() for name in names.split(", ")}


class ScoreError(ValueError):
    pass


@dataclass
class Engraving:
    svgs: list[str]

    @property
    def page_count(self) -> int:
        return len(self.svgs)

    def png(self, page: int = 1, width: int = 1400, colors: int = 128) -> bytes:
        image = self._raster(page, width)
        top, bottom = self._ink(image)
        image = image.crop((0, top, image.width, bottom))
        image = image.quantize(colors, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE)
        out = io.BytesIO()
        image.save(out, "PNG", optimize=True)
        return out.getvalue()

    def pdf(self) -> bytes:
        try:
            import cairosvg
            import pikepdf
        except (ImportError, OSError):
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
            page_svg = svg.replace("<svg ", f'<svg width="{w:g}" height="{h:g}" ', 1)
            if page_svg.startswith("<?xml"):
                page_svg = page_svg[page_svg.index("?>") + 2 :]
            trimmed = (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:g} {y + top * scale:g} {w:g} {(bottom - top) * scale:g}">'
                f"{page_svg}</svg>"
            )
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
                skip_system_fonts=True,
                font_files=FONT_FILES,
                font_family=TEXT_FONT,
                serif_family=TEXT_FONT,
            )
        )
        return Image.open(io.BytesIO(raw)).convert("RGB")

    @staticmethod
    def _ink(image: Image.Image) -> tuple[int, int]:
        ink = ImageChops.difference(image, Image.new("RGB", image.size, "#ffffff")).getbbox()
        if not ink:
            return 0, image.height
        pad = round(image.width * 0.025)
        return max(ink[1] - pad, 0), min(ink[3] + pad, image.height)


def load_toolkit(score: bytes, options: dict | None = None, *, keep_pedals: bool = False) -> verovio.toolkit:
    toolkit = verovio.toolkit(False)
    toolkit.setResourcePath(RESOURCE_PATH)
    toolkit.setOptions({**VEROVIO_OPTIONS, **(options or {})})
    data = _musicxml(score)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if not re.search(r"<score-(?:partwise|timewise)\b", text[:5000]):
        raise ScoreError("This file is not MusicXML" + (" but a PDF" if score[:5] == b"%PDF-" else ""))
    loaded = toolkit.loadData(_separate_reused_voices(text))
    if not loaded:
        raise ScoreError("Verovio could not read this file as MusicXML")
    _tidy(toolkit, _readable_names(score), keep_pedals)
    if len(set(re.findall(r'<staffDef\b[^>]*\bn="(\d+)"', toolkit.getMEI()))) <= LARGE_SCORE_STAVES:
        toolkit.setOptions({"systemDivider": "none"})
        toolkit.redoLayout()
    return toolkit


def _tidy(toolkit: verovio.toolkit, names: dict[str, str], keep_pedals: bool = False) -> None:
    mei = toolkit.getMEI()
    patched = re.sub(r"<measure\b(?:(?!</measure>).)*?<multiRest\b.*?</measure>", _expand_multi_rest, mei, flags=re.S)
    for part, name in names.items():
        patched = re.sub(rf'(<staffDef\b[^>]*xml:id="{re.escape(part)}"[^>]*>\s*<label\b[^>]*>)[^<]*', lambda m: m.group(1) + escape(name), patched)
    patched = re.sub(
        r"<(label|labelAbbr)\b[^>]*>.*?</\1>",
        lambda m: re.sub(r"accidental(Flat|Sharp|Natural)", lambda a: {"Flat": "♭", "Sharp": "♯", "Natural": "♮"}[a.group(1)], m.group(0)).replace("&amp;amp;", "&amp;"),
        patched,
        flags=re.S,
    )
    patched = re.sub(
        r"<harm\b[^>]*>[^<]*</harm>",
        lambda m: re.sub(r"(?<=[^>])([b#])(?=1?\d)", lambda a: "♭" if a.group(1) == "b" else "♯", m.group(0)),
        patched,
    )
    patched = re.sub(
        r"(<staffDef\b[^>]*?(?<!/)>)((?:(?!</staffDef>).)*?</staffDef>)",
        lambda m: m.group(0) if "<clef" in m.group(2) or "clef.shape" in m.group(1) else m.group(1) + '<clef shape="G" line="2" />' + m.group(2),
        patched,
        flags=re.S,
    )
    patched = re.sub(r'<staffDef\b(?![^>]*clef\.shape)([^>]*?)/>', r'<staffDef\1><clef shape="G" line="2" /></staffDef>', patched)
    cancelled = re.findall(r'<clef\b[^>]*xml:id="([^"]+)"[^>]*/>(?=\s*<clef\b)', patched)
    for clef in cancelled:
        patched = re.sub(rf'<clef\b[^>]*(?:xml:id="{clef}"|sameas="#{clef}")[^>]*/>', "", patched)
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
    if len(re.findall(r"<staffDef\b", patched)) > BRACKET_MAX_STAVES:
        patched = re.sub(r"<scoreDef\b(?![^>]*\boptimize=)", '<scoreDef optimize="true"', patched, count=1)
    patched = _drop_title_text(patched)
    if not keep_pedals:
        patched = re.sub(r"<pedal\b[^>]*/>", "", patched)
    patched = re.sub(r"<dir\b[^>]*>(?:(?!</dir>).)*?\bPed(?:ale?|\b)(?:(?!</dir>).)*?</dir>", "", patched, flags=re.S)
    patched = re.sub(r"<dir\b[^>]*>(?:\s|<[^>]+>)*\*(?:\s|<[^>]+>)*</dir>", "", patched)
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
    patched = _number_unmarked_pickup(patched)
    if patched != mei:
        toolkit.loadData(patched)


def _expand_multi_rest(match: re.Match) -> str:
    measure = match.group(0)
    opening = measure[: measure.index(">") + 1]
    number = re.search(r'\bn="(\d+)"', opening)
    if not number:
        return measure
    count = int(re.search(r'<multiRest\b[^>]*\bnum="(\d+)"', measure).group(1))
    right = re.search(r'\sright="[^"]*"', opening)
    if right and count > 1:
        measure = measure.replace(opening, opening.replace(right.group(0), ""), 1)
    staves = "".join(f'<staff n="{n}"><layer n="1"><mRest /></layer></staff>' for n in re.findall(r'<staff\b[^>]*\bn="(\d+)"', measure))
    copies = [f'<measure n="{int(number.group(1)) + k}"{right.group(0) if right and k == count - 1 else ""}>{staves}</measure>' for k in range(1, count)]
    return re.sub(r"<multiRest\b[^>]*/>", "<mRest />", measure) + "".join(copies)


def _number_unmarked_pickup(mei: str) -> str:
    measures = ScoreIndex(mei).measures
    if len(measures) < 2 or measures[0].number != 1 or measures[1].number != 2 or not measures[0].meter:
        return mei
    first = measures[0]
    count, unit = first.meter.split("/")
    full = Fraction(int(count) * 4, int(unit))
    if not Fraction(0) < first.content_length < full - TOLERANCE:
        return mei
    completed_at_the_end = abs(first.content_length + measures[-1].content_length - full) <= TOLERANCE
    lengths = {}
    for event in first.events:
        lengths[event.staff] = max(lengths.get(event.staff, Fraction(0)), event.onset + event.duration)
    every_staff_even = set(lengths) == {event.staff for measure in measures for event in measure.events} and len(set(lengths.values())) == 1
    if not (completed_at_the_end or every_staff_even):
        return mei
    mei = re.sub(r'(<measure\b[^>]*\bn=")(\d+)(")', lambda m: f"{m.group(1)}{int(m.group(2)) - 1}{m.group(3)}", mei)
    opening = re.search(rf'<measure\b[^>]*xml:id="{re.escape(first.id)}"[^>]*>', mei).group(0)
    marked = opening if "metcon=" in opening else opening.replace("<measure", '<measure metcon="false"', 1)
    return mei.replace(opening, marked, 1)


def _short_name(name: str) -> str:
    name = re.sub(r"<[^>]+>", "", unescape(name)).strip()
    numbers = [
        int(m.group(1)) if m.group(1) else {"I": 1, "II": 2, "III": 3, "IV": 4}[m.group(2)]
        for m in re.finditer(r"(?<![\w.])(?:([1-4])(?:st|nd|rd|th)?|(I{1,3}|IV))(?![\w])", name)
    ]
    base = re.sub(r"(?<![\w.])(?:[1-4](?:st|nd|rd|th)?|I{1,3}|IV)(?!\w)|\bin [A-G][♭♯b#]?(?!\w)|[()&,]", " ", name)
    base = " ".join(base.lower().split())
    short = SHORT_NAMES.get(base)
    if not short:
        return ""
    return short + (" " + ", ".join(ROMAN[n] for n in numbers) if numbers else "")


def _short_names_and_bracket(mei: str) -> str:

    def add_abbr(match: re.Match) -> str:
        label, abbr = match.group(1), match.group(2)
        short = _short_name(label)
        if not short or (abbr and re.sub(r"<[^>]+>", "", abbr).strip() != re.sub(r"<[^>]+>", "", label).strip()):
            return match.group(0)
        return label + f"<labelAbbr>{escape(short)}</labelAbbr>"

    mei = re.sub(r"(<label\b[^>]*>.*?</label>)\s*(<labelAbbr\b[^>]*>.*?</labelAbbr>)?", add_abbr, mei, flags=re.S)
    staves = set(re.findall(r'<staffDef\b[^>]*\bn="(\d+)"', mei))
    if "<grpSym" not in mei and 2 < len(staves) <= BRACKET_MAX_STAVES:
        mei = re.sub(r"(<staffGrp\b[^>]*?)>", r'\1 bar.thru="true"><grpSym symbol="bracket" />', mei, count=1)
    return mei


def _clefs_before_barlines(mei: str) -> str:
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
    head = mei[: mei.find("</meiHead>")]
    names = [unescape(name).strip() for name in re.findall(r"<(?:title|persName)\b[^>]*>([^<]+)<", head)]

    def drop(match: re.Match) -> str:
        text = " ".join(unescape(re.sub(r"<[^>]+>", " ", match.group(0))).split())
        heading = re.fullmatch(r"Movement [IVX\d]+", text)
        named = any(name == text or len(name.split()) > 1 and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text) for name in names)
        return "" if heading or named else match.group(0)

    return re.sub(r"<dir\b.*?</dir>", drop, mei, flags=re.S)


def _musicxml(score: bytes) -> bytes:
    if score[:2] != b"PK":
        return score
    with zipfile.ZipFile(io.BytesIO(score)) as archive:
        root = re.search(rb'full-path="([^"]+)"', archive.read("META-INF/container.xml"))
        return archive.read(root.group(1).decode()) if root else b""


def _separate_reused_voices(text: str) -> str:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return text
    renumbered = [_separate_voices_in(segment) for segment in root.iter() if segment.find("note") is not None]
    return ET.tostring(root, encoding="unicode") if any(renumbered) else text


def _separate_voices_in(segment: ET.Element) -> bool:
    numbers = [int(voice) for voice in (note.findtext("voice", "1") for note in segment.iter("note")) if voice.isdigit()]
    next_voice = max(numbers, default=1) + 1
    ends: dict[str, float] = {}
    renamed: dict[str, str] = {}
    time = onset = 0.0
    for element in segment:
        if element.tag == "backup":
            time -= float(element.findtext("duration", "0"))
            renamed = {}
        elif element.tag == "forward":
            time += float(element.findtext("duration", "0"))
        elif element.tag == "note":
            chord = element.find("chord") is not None
            onset = onset if chord else time
            duration = 0.0 if element.find("grace") is not None else float(element.findtext("duration", "0"))
            voice = element.findtext("voice", "1")
            if voice not in renamed and duration and onset < ends.get(voice, 0.0) and not chord:
                renamed[voice] = str(next_voice)
                next_voice += 1
            target = renamed.get(voice, voice)
            if target != voice:
                (element.find("voice") if element.find("voice") is not None else ET.SubElement(element, "voice")).text = target
            ends[target] = max(ends.get(target, 0.0), onset + duration)
            time = time if chord else onset + duration
    return next_voice > max(numbers, default=1) + 1


def _readable_names(score: bytes) -> dict[str, str]:
    text = _musicxml(score).decode("utf-8", errors="replace")
    names = {}
    for part in re.finditer(r'<score-part\b[^>]*\bid="([^"]+)"(.*?)</score-part>', text, flags=re.S):
        label = re.search(r"<part-name\b[^>]*>\s*([a-z]+)(\d*)\s*</part-name>", part.group(2))
        instrument = re.search(r"<instrument-name>([^<]+)</instrument-name>", part.group(2))
        if not label or not instrument:
            continue
        name = re.sub(r"^([A-G][♭♯b#]?) (.+)$", r"\2 in \1", instrument.group(1).strip())
        if label.group(2):
            number = ROMAN.get(int(label.group(2)), label.group(2))
            name = name.replace(" in ", f" {number} in ", 1) if " in " in name else f"{name} {number}"
        names[part.group(1)] = name
    return names


def _end_hairpins_at_dynamics(measure: re.Match) -> str:
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
    text = measure.group(0)
    groups: dict[tuple[str, str, str], list[re.Match]] = {}
    for dynam in re.finditer(r"<dynam\b[^>]*>.*?</dynam>", text, flags=re.S):
        tag = dynam.group(0)[: dynam.group(0).index(">")]
        key = tuple((re.search(rf'\b{name}="([^"]*)"', tag) or [None, ""])[1] for name in ("staff", "tstamp", "place"))
        groups.setdefault(key, []).append(dynam)
    for marks in groups.values():
        if len(marks) < 2:
            continue
        marks.sort(key=lambda mark: 'val="' not in mark.group(0)[: mark.group(0).index(">")])
        first = marks[0].group(0)
        inner = " ".join(re.sub(r"^<dynam\b[^>]*>|</dynam>$", "", mark.group(0)).strip() for mark in marks)
        text = text.replace(first, first[: first.index(">") + 1] + inner + "</dynam>", 1)
        for mark in marks[1:]:
            text = text.replace(mark.group(0), "", 1)
    return text


def _unalign_crowded_dynamics(measure: re.Match) -> str:
    text = measure.group(0)
    last: dict[str, float] = {}
    for dynam in re.finditer(r'<dynam\b(?=[^>]*\bvgrp=")(?=[^>]*\bstaff="(\d+)")(?=[^>]*\btstamp="([\d.]+)")[^>]*>', text):
        staff, beat = dynam.group(1), float(dynam.group(2))
        if staff in last and beat - last[staff] < 1:
            text = text.replace(dynam.group(0), re.sub(r'\s*\bvgrp="[^"]*"', "", dynam.group(0)), 1)
        last[staff] = beat
    return text


def _separate_hairpins(mei: str) -> str:
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
    index = ScoreIndex(mei)
    playing = {(m.number, e.staff, e.onset, e.pitch): e.id for m in index.measures for e in m.events if e.pitch}
    events = {e.id: (m.number, e.onset, e.pitch, e.staff) for m in index.measures for e in m.events}
    rests = {(m.number, e.staff, e.layer, e.onset): e.id for m in index.measures for e in m.events if not e.pitch}
    layers = {e.id: e.layer for m in index.measures for e in m.events}
    moved: dict[str, str] = {}
    accidentals: dict[str, str] = {}
    hidden: set[str] = set()

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
    for id in set(moved.values()):
        patched = re.sub(
            rf'(<chord\b[^>]*?)\s+stem\.visible="false"([^>]*>(?:(?!</chord>).)*?xml:id="{re.escape(id)}")', r"\1\2", patched, flags=re.S
        )
    return patched


def _spread_ties(mei: str) -> str:
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
    start = int(index.measure_range(first, first, include_pickup=include_pickup).split("-")[0])
    earlier = {e.id for m in index.measures if m.last_index < start for e in m.events}
    return {
        tie for tie, note in re.findall(r'<tie\b[^>]*xml:id="([^"]+)"[^>]*startid="#([^"]+)"', toolkit.getMEI()) if note in earlier
    }


SPACE = 180


def shorten_ties(svg: str, ties: set[str]) -> str:

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

    return re.sub(r'<g class="tie id-([^" ]+) spanning">(?:\s*<g id="bbox-[^"]*"[^>]*>.*?</g>)?\s*<path d="([^"]+)"', shorten, svg, flags=re.S)


def check_range(measures: tuple[int, int] | None) -> None:
    if measures and measures[0] > measures[1]:
        raise PositionError(f"Measures {measures[0]}-{measures[1]} run backwards; give the first bar first, e.g. {measures[1]}-{measures[0]}")


def engrave(score: bytes, measures: tuple[int, int] | None = None, *, include_pickup: bool = True) -> Engraving:
    check_range(measures)
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
    toolkit = load_toolkit(score)
    index = ScoreIndex(toolkit.getMEI())
    ties = incoming_ties(toolkit, index, measures[0])
    toolkit.select({"measureRange": index.measure_range(*measures)})
    toolkit.redoLayout()
    return Engraving([shorten_ties(toolkit.renderToSVG(page), ties) for page in range(1, toolkit.getPageCount() + 1)])
