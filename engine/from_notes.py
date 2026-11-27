from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field, replace
import xml.etree.ElementTree as ET
from fractions import Fraction

from engine import correct, notes
from engine.errors import UserError
from engine.reduce import midi
from engine.score import Measure, alteration
from kit import note_rules

REST_TYPES = ("whole", "half", "quarter", "eighth", "16th", "32nd", "64th", "128th")
DIVISIONS = 32
BAR_LINE = re.compile(r"m\d+ len=(?P<length>\d+)(?P<changes>(?: (?:ts|ks|rep|ending)=\S+)*)")
CHORD_NAME = re.compile(r"(?P<root>[A-G])(?P<sign>[#b♯♭]?)(?P<kind>.*?)(?:/(?P<bass>[A-G])(?P<bass_sign>[#b♯♭]?))?")
TRANSPOSING_NAME = re.compile(r"\bin [a-g](?:[b#♭♯]|[- ](?:flat|sharp))?\b|\bhorns?\b|\bsaxophones?\b|\bcor anglais\b",
                              re.IGNORECASE)
REGISTER_JUMP = 11
PITCH_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
STAVES, REGISTER, TIME, OPENING = (
    "pages agree on their staves", "a staff keeps its register over a page turn", "an assumed time signature fits the page before",
    "a short first bar completes the page before")


class WholePieceError(notes.NotesError):
    pass


@dataclass(frozen=True)
class Doubt:
    rule: str
    page: int
    reason: str
    said: str


@dataclass
class HandIn:
    score: bytes
    doubts: list[Doubt]
    bars: dict[int, list[int]]
    notes: list[str]


def score_from_pages(pages: list[str]) -> bytes:
    return hand_in(pages).score


def hand_in(pages: list[str]) -> HandIn:
    if not pages:
        raise notes.NotesError("No pages were handed in")
    numbered: dict[int, str] = {}
    for position, page in enumerate(pages, 1):
        number = note_rules.page_number(page)
        if found := note_rules.problems(page):
            raise notes.NotesError(f"{f'Page {number}' if number else f'Note list {position}'}: {found[0]}")
        if number in numbered:
            raise notes.NotesError(f"Two note lists say page={number}; hand in each page once")
        numbered[number] = page
    if found := note_rules.join_problems(pages):
        raise WholePieceError(found[0])
    numbers = sorted(numbered)
    pages = _clefs_moved([numbered[number] for number in numbers])
    for position, (number, page) in enumerate(zip(numbers, pages)):
        try:
            score_from_notes(join_pages([page]), after_a_rest_bar=position > 0)
        except UserError as error:
            raise notes.NotesError(f"Page {number}: {error}") from error
    joined = _join(pages)
    return HandIn(_named_bars(_with_instruments(joined.text, joined.instruments, joined.keys), joined.names),
                  joined.doubts, joined.bars, joined.notes)


def _named_bars(score: bytes, names: list[str]) -> bytes:
    if all(name.isdigit() for name in names):
        return score
    root = ET.fromstring(score)
    for part in root.iter("part"):
        for measure, name in zip(part.findall("measure"), names):
            measure.set("number", name)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def score_from_notes(text: str, *, after_a_rest_bar: bool = False) -> bytes:
    index = notes.decode(text)
    staves = max((voice[0] for line in text.splitlines() if (voice := notes.voice_label(line.partition(":")[0].strip()))), default=1)
    first = index.measures[0] if index.measures else None
    measures = [_rest_bar_before(first), *index.measures] if first and after_a_rest_bar else index.measures
    marks = [dict(part.split("=", 1) for part in found["changes"].split())
             for line in text.splitlines() if (found := BAR_LINE.fullmatch(line.strip()))]
    marks = [{}, *marks] if first and after_a_rest_bar else marks
    return correct.replace_bars(_empty_score(measures, marks, staves, _opening_clefs(text)), _with_every_staff(text, staves))


def _with_instruments(text: str, instruments: dict[int, str], keys: list[dict[int, str]]) -> bytes:
    own = {staff for in_force in keys for staff in in_force}
    if not instruments and not own:
        return score_from_notes(text)
    staves = max([*instruments, *(int(label.split(".")[0]) for line in text.splitlines()
                                   if (label := line.partition(":")[0].strip()) and notes.VOICE_LABEL.fullmatch(label))])
    groups: list[list[int]] = []
    for staff in range(1, staves + 1):
        named_alike = instruments.get(staff) and instruments.get(staff) == instruments.get(groups[-1][-1]) if groups else False
        unnamed_alike = groups and not instruments and staff not in own and groups[-1][-1] not in own
        if named_alike or unnamed_alike:
            groups[-1].append(staff)
        else:
            groups.append([staff])
    root = None
    for number, group in enumerate(groups, 1):
        name = instruments.get(group[0], "")
        built = ET.fromstring(score_from_notes(_part_text(text, group, keys)))
        part = built.find("part")
        part.set("id", f"P{number}")
        if root is None:
            root = built
            root.remove(part)
            root.find("part-list").clear()
        ET.SubElement(ET.SubElement(root.find("part-list"), "score-part", id=f"P{number}"), "part-name").text = name
        root.append(part)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _plain(name: str) -> str:
    return " ".join(name.lower().replace("♭", "b").replace("-flat", "b").replace(" flat", "b").split())


def _part_text(text: str, staves: list[int], keys: list[dict[int, str]]) -> str:
    places = {staff: position for position, staff in enumerate(staves, 1)}
    lines, page_key, shown, bar = [], "0", None, -1
    for line in filter(None, map(str.strip, text.splitlines())):
        label, _, body = line.partition(":")
        voice = notes.voice_label(label.rstrip("w"))
        if line.startswith("N1 "):
            page_key = re.search(r" ks=(\S+)", line)[1]
            shown = keys[0].get(staves[0], page_key) if keys else page_key
            lines.append(re.sub(r"(?<= ks=)\S+", shown, line))
        elif line.startswith("m"):
            bar += 1
            page_key = found[1] if (found := re.search(r" ks=(\S+)", line)) else page_key
            key = keys[bar].get(staves[0], page_key)
            line = re.sub(r" ks=\S+", "", line)
            lines.append(f"{line} ks={key}" if key != shown and bar else line)
            shown = key
        elif voice and voice[0] in places:
            lines.append(f"{places[voice[0]]}.{voice[1]}{'w' if label.endswith('w') else ''}:{body}")
        elif not voice and 1 in places:
            lines.append(line)
    return "\n".join(lines)


def _clefs_moved(pages: list[str]) -> list[str]:
    pending: dict[int, tuple[int, list[str]]] = {}
    moved = []
    for page in pages:
        bars = [[]]
        for line in page.splitlines():
            if line.strip().startswith("m"):
                bars.append([])
            bars[-1].append(line)
        for bar in bars[1:]:
            voices = [(position, voice) for position, line in enumerate(bar)
                      if (voice := notes.voice_label(line.partition(":")[0].strip()))]
            for staff, (layer, clefs) in list(pending.items()):
                lines = [position for position, voice in voices if voice[0] == staff]
                if lines:
                    target = next((position for position, voice in voices if voice == (staff, layer)), lines[0])
                    label, _, body = bar[target].partition(":")
                    bar[target] = f"{label}: {' '.join(clefs)} {body.strip()}"
                    del pending[staff]
            for position, (staff, layer) in voices:
                label, _, body = bar[position].partition(":")
                tokens = body.split()
                end = max((at for at, token in enumerate(tokens) if not token.isdigit() and not notes.CLEF.fullmatch(token)
                           and not note_rules.OCTAVE_LINE.fullmatch(token)),
                          default=-1) + 1
                if trailing := [token for token in tokens[end:] if notes.CLEF.fullmatch(token)]:
                    kept = [token for token in tokens[end:] if not notes.CLEF.fullmatch(token)]
                    bar[position] = f"{label}: {' '.join(tokens[:end] + kept)}"
                    pending[staff] = (layer, trailing)
        moved.append("\n".join(line for bar in bars for line in bar))
    return moved


def _opening_clefs(text: str) -> dict[int, str]:
    opening: dict[int, str] = {}
    sounded: set[int] = set()
    sounding: set[int] = set()
    for line in text.splitlines():
        if BAR_LINE.match(line):
            sounded |= sounding
            continue
        label, _, body = line.partition(":")
        if not notes.VOICE_LABEL.fullmatch(label.strip()):
            continue
        staff = int(label.split(".")[0])
        if staff in sounded or staff in opening:
            continue
        for written in body.split():
            if change := notes.CLEF.fullmatch(written):
                opening[staff] = change[1]
                break
            if not written.isdigit() and notes.token(written).sounding != "r":
                sounding.add(staff)
                break
    return opening


def _rest_bar_before(first: Measure) -> Measure:
    return replace(first, number=first.number - 1, name=str(first.number - 1), declared_length=_full_length(first), events=[], chord_symbols=[])


@dataclass
class _Bar:
    length: int
    changes: dict[str, str]
    voices: dict[str, str] = field(default_factory=dict)
    words: dict[str, str] = field(default_factory=dict)
    chord_symbols: list[tuple[str, int]] = field(default_factory=list)
    other: list[str] = field(default_factory=list)
    pages: set[int] = field(default_factory=set)
    continues: bool = False
    keys: dict[int, str] = field(default_factory=dict)
    opens_page: bool = False


@dataclass
class _Page:
    number: int
    div: int
    meter: str
    assumed: bool
    key: str
    named: dict[int, str]
    lines: list[str]
    bars: list[_Bar] = field(default_factory=list)
    places: dict[int, int] = field(default_factory=dict)

    @property
    def staves(self) -> int:
        return max([*self.named, *(int(label.split(".")[0]) for bar in self.bars for label in bar.voices)], default=1)


@dataclass
class _Joined:
    text: str
    names: list[str]
    instruments: dict[int, str]
    keys: list[dict[int, str]]
    doubts: list[Doubt]
    bars: dict[int, list[int]]
    notes: list[str]


def join_pages(pages: list[str]) -> str:
    return _join(pages).text


def _join(pages: list[str]) -> _Joined:
    read = [_page_heading(text) for text in pages]
    div = math.lcm(*(page.div for page in read))
    meter, key = read[0].meter, read[0].key
    doubts, in_force, before = [], meter, None
    for page in read:
        page_meter = page.meter
        if page.assumed and before and page_meter != in_force:
            if _units_in_bar(page_meter, div) == _units_in_bar(in_force, div):
                page_meter = in_force
            else:
                doubts.append(Doubt(TIME, page.number,
                                    f"Page {page.number} takes the time signature {page_meter} without one printed, but "
                                    f"page {before.number} ends in {in_force}, with bars of another length: look again for "
                                    f"a time signature printed on page {page.number}.",
                                    _disagreed(page.number, before.number, f"its time signature does not follow from page {before.number}")))
        page.bars = _page_bars(page.number, page.lines, div // page.div, page_meter, page.key)
        for bar in page.bars:
            in_force = bar.changes.get("ts", in_force)
        before = page
    reference = max(read, key=lambda page: (page.staves, -page.number))
    instruments = reference.named or next((page.named for page in read if page.staves == reference.staves and page.named), {})
    for page in read:
        page.places, unmatched = _staff_places(page, reference, instruments)
        if unmatched:
            doubts.append(_staves_doubt(page, reference, instruments, unmatched))
        page.bars = [_placed(bar, page.places, set(unmatched)) for bar in page.bars]
    bars, opening = _joined(read, div, meter, key)
    _sounding(bars, div)
    names = _bar_names(bars, div, meter)
    numbers = [int(name.rstrip("a")) for name in names]
    concert = any(re.match(r"i:\s*concert\b", line.strip()) for page in pages for line in page.splitlines())
    keys, printed_apart, split = _staff_keys(bars, key, instruments)
    doubts += opening + _register_doubts(bars, [page.number for page in read])
    apart = printed_apart | {place for place, name in instruments.items() if TRANSPOSING_NAME.search(name)}
    said = [] if concert or not apart else [_as_printed(instruments, sorted(apart))]
    return _Joined(_bars_as_text(bars, div, meter, key), names, instruments, keys, doubts,
                   {page.number: sorted({number for number, bar in zip(numbers, bars) if page.number in bar.pages}) for page in read},
                   said + [DRAWN_WITH_THE_TOP_KEY.format(name=name) for name in split])


def _disagreed(page: int, against: int, said: str) -> str:
    return f"Page {page} of my careful reading did not agree with page {against}: {said}"


def _staff_keys(bars: list[_Bar], key: str, instruments: dict[int, str]) -> tuple[list[dict[int, str]], set[int], list[str]]:
    own, in_force, apart, split = {}, [], set(), {}
    for bar in bars:
        key = bar.changes.get("ks", key)
        own = (({} if bar.opens_page else own) | bar.keys)
        in_force.append(own)
        apart |= {staff for staff, printed in own.items() if printed not in (key, "0")}
        split |= {name: True for staff, name in sorted(instruments.items())
                  if instruments.get(staff - 1) == name and note_rules.fifths(own.get(staff, key)) != note_rules.fifths(own.get(staff - 1, key))}
    return in_force, apart, list(split)


SHOWN_AS_PRINTED = ("My reading shows {parts} as printed: where an instrument is a transposing one, its notes sound at a "
                    "different pitch than shown, and the analysis across the parts may be off there.")
DRAWN_WITH_THE_TOP_KEY = ("The staves of the {name} part print different key signatures. My reading draws them all with the "
                          "top staff's key signature, and their notes keep their printed pitches.")


def _as_printed(instruments: dict[int, str], places: list[int]) -> str:
    names = [instruments.get(place, f"staff {place}") for place in places]
    named = [f"the {name} {'parts' if names.count(name) > 1 else 'part'}" if name in instruments.values() else f"the part on {name}"
             for name in dict.fromkeys(names)]
    listed = named[0] if len(named) == 1 else f"{', '.join(named[:-1])} and {named[-1]}"
    return SHOWN_AS_PRINTED.format(parts=listed)


def _page_heading(text: str) -> _Page:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    head = note_rules.HEADER.fullmatch(lines[0]) if lines else None
    if not head:
        raise notes.NotesError(note_rules.HEADING)
    opening = next((position for position, line in enumerate(lines) if line.startswith("m")), len(lines))
    named = next((note_rules.instruments(line) for line in lines[1:opening] if line.startswith("i:")), None)
    kept = [line for position, line in enumerate(lines[1:], 1) if position >= opening or not line.startswith("i:")]
    return _Page(int(head[1]), int(head[2]), head[3], bool(head[4]), head[5], named or {}, kept)


def _staff_places(page: _Page, reference: _Page, instruments: dict[int, str]) -> tuple[dict[int, int], list[int]]:
    if page.staves == reference.staves:
        return {}, []
    free, places, unmatched = dict(instruments), {}, []
    for staff in range(1, page.staves + 1):
        name = page.named.get(staff)
        place = next((place for place, known in sorted(free.items()) if name and _plain(known) == _plain(name)), None)
        if place is None:
            unmatched.append(staff)
        else:
            places[staff] = place
            del free[place]
    return places, unmatched


def _staves_doubt(page: _Page, reference: _Page, instruments: dict[int, str], unmatched: list[int]) -> Doubt:
    named = [page.named[staff] for staff in unmatched if staff in page.named]
    reason = (f"Page {page.number} has {_staves(page.staves)} in a system and page {reference.number} has "
              f"{_staves(reference.staves)}: count the staves again.")
    if named:
        reason += f" Page {reference.number} does not name {', '.join(named)}."
    if instruments:
        reason += (f" Page {reference.number} names these staves: {', '.join(instruments[staff] for staff in sorted(instruments))}; "
                   "write your i: line with these names for the staves your page shows.")
    listed = [f"{staff} ({page.named[staff]})" if staff in page.named else str(staff) for staff in unmatched]
    left_out = listed[0] if len(listed) == 1 else f"{', '.join(listed[:-1])} and {listed[-1]}"
    return Doubt(STAVES, page.number, reason, _disagreed(
        page.number, reference.number, f"it has {_staves(page.staves)} where page {reference.number} has "
        f"{_staves(reference.staves)}, and its {'staff' if len(unmatched) == 1 else 'staves'} {left_out} could not be "
        f"matched to one of page {reference.number}'s, so {'its' if len(unmatched) == 1 else 'their'} music is left out"))


def _placed(bar: _Bar, places: dict[int, int], left_out: set[int]) -> _Bar:
    if not places and not left_out:
        return bar

    def moved(label: str) -> str:
        staff, _, rest = label.partition(".")
        return f"{places.get(int(staff), int(staff))}.{rest}"

    def kept(label: str) -> bool:
        return int(label.partition(".")[0]) not in left_out

    return replace(bar, voices={moved(label): body for label, body in bar.voices.items() if kept(label)},
                   words={moved(label): body for label, body in bar.words.items() if kept(label)},
                   keys={places.get(staff, staff): key for staff, key in bar.keys.items() if staff not in left_out})


def _page_bars(number: int, lines: list[str], scale: int, meter: str, key: str) -> list[_Bar]:
    bars, opening_keys = [], {}
    for line in lines:
        label, _, body = line.partition(":")
        if stated := note_rules.staff_key(line):
            (bars[-1].keys if bars else opening_keys)[stated[0]] = stated[1]
        elif line.startswith("m"):
            found = BAR_LINE.fullmatch(line)
            if not found:
                raise notes.NotesError(f"Page {number}: a bar line looks like 'm3 len=96', not {line!r}")
            opening = {"ts": meter, "ks": key} if not bars else {}
            changes = {name: value for name, value in opening.items() if value} | dict(
                part.split("=", 1) for part in found["changes"].split())
            bars.append(_Bar(int(found["length"]) * scale, changes, pages={number},
                             keys=opening_keys if not bars else {}, opens_page=not bars))
        elif not bars:
            raise notes.NotesError(f"Page {number}: a voice line needs a bar line like 'm3 len=96' before it")
        elif label == "x":
            bars[-1].other.append(line)
        elif label == "c":
            entries = map(notes.CHORD_ENTRY.fullmatch, body.split())
            bars[-1].chord_symbols.extend((entry["symbol"], int(entry["at"]) * scale) for entry in entries)
        elif notes.WORDS_LABEL.fullmatch(label):
            bars[-1].words[label[:-1]] = body.strip()
        else:
            bars[-1].voices[label] = " ".join(str(int(entry) * scale) if entry.isdigit() else entry for entry in body.split())
    return bars


def _joined(pages: list[_Page], div: int, meter: str, key: str) -> tuple[list[_Bar], list[Doubt]]:
    bars, doubts, before = [], [], None
    for page in pages:
        for position, bar in enumerate(page.bars):
            turn = position == 0 and bool(bars)
            if bars and (turn or _repeat_between(bars[-1], bar)) and _completes(bars[-1], bar, div, meter, key):
                if _repeat_between(bars[-1], bar):
                    bars.append(replace(bar, continues=True))
                else:
                    bars[-1] = _one_bar(bars[-2] if len(bars) > 1 else None, bars[-1], bar, div)
                continue
            if turn and _short(bar, div, meter):
                doubts.append(Doubt(OPENING, page.number,
                                    f"Page {page.number} begins with a bar shorter than its time signature, and the last bar "
                                    f"of page {before.number} does not make up the rest: count the beats of the first bar of "
                                    f"page {page.number} again, and look for a time signature printed on it.",
                                    _disagreed(page.number, before.number, "its first bar is shorter than its time signature "
                                               f"and does not complete the last bar of page {before.number}")))
            if turn:
                bar = replace(bar, words={label: _words_after_the_turn(bars[-1].voices.get(label), bar.voices.get(label), words, div)
                                          for label, words in bar.words.items()})
            meter, key = bar.changes.get("ts", meter), bar.changes.get("ks", key)
            bars.append(bar)
        before = page
    return bars, doubts


def _repeat_between(before: _Bar, after: _Bar) -> bool:
    return before.changes.get("rep") in ("end", "both") or after.changes.get("rep") in ("start", "both")


def _short(bar: _Bar, div: int, meter: str) -> bool:
    full = _units_in_bar(bar.changes.get("ts", meter), div)
    return full is not None and bar.length < full


def _bar_names(bars: list[_Bar], div: int, meter: str) -> list[str]:
    names, number = [], 0 if bars and _short(bars[0], div, meter) else 1
    for bar in bars:
        if bar.continues:
            names.append(f"{names[-1]}a")
        else:
            names.append(str(number))
            number += 1
    return names


def _sounding(bars: list[_Bar], div: int) -> None:
    octaves: dict[int, tuple[int, int]] = {}
    for bar in bars:
        voices = note_rules.as_sounding([(label, body.split()) for label, body in bar.voices.items()], div, octaves)
        bar.voices = {label: " ".join(tokens) for label, tokens in voices}


def _register_doubts(bars: list[_Bar], numbers: list[int]) -> list[Doubt]:
    pitches: dict[tuple[int, int], list[int]] = {}
    clefs: dict[tuple[int, int], list[str]] = {}
    in_force: dict[int, str] = {}
    for bar in bars:
        for label, body in bar.voices.items():
            staff = int(label.split(".")[0])
            for token in body.split():
                if clef := notes.CLEF.fullmatch(token):
                    in_force[staff] = clef[1][0]
                elif not token.isdigit() and (sounding := notes.token(token).sounding) != "r" and not sounding.startswith(("g", "u")):
                    for page in bar.pages:
                        pitches.setdefault((page, staff), []).extend(midi(name.rstrip("~")) for name in sounding.split("+"))
                        clefs.setdefault((page, staff), [in_force.get(staff, "")] * 2)[1] = in_force.get(staff, "")
    doubts = []
    previous = dict(zip(numbers[1:], numbers))
    for (page, staff), heard in sorted(pitches.items()):
        before = pitches.get((previous.get(page), staff))
        if not before or clefs[(previous[page], staff)][1] != clefs[(page, staff)][0]:
            continue
        was, now = statistics.median(before), statistics.median(heard)
        if abs(now - was) >= REGISTER_JUMP:
            doubts.append(Doubt(REGISTER, page, f"Page {previous[page]} has staff {staff} around "
                                f"{_pitch_name(was)}, page {page} has it around {_pitch_name(now)} in the same clef: look at "
                                f"the clef of page {page} again; is there a small 8 on it, or an octave line?",
                                _disagreed(page, previous[page], f"staff {staff} sounds about an octave away from page {previous[page]}")))
    return doubts


def _staves(count: int) -> str:
    return "1 staff" if count == 1 else f"{count} staves"


def _pitch_name(number: float) -> str:
    return f"{PITCH_NAMES[round(number) % 12]}{round(number) // 12 - 1}"


def _completes(before: _Bar, after: _Bar, div: int, meter: str, key: str) -> bool:
    full = _units_in_bar(meter, div)
    unchanged = after.changes.get("ts", meter) == meter and after.changes.get("ks", key) == key
    one_ending = before.changes.get("ending") == after.changes.get("ending")
    return (unchanged and one_ending and not before.continues and full is not None and before.length < full
            and before.length + after.length == full)


def _one_bar(previous: _Bar | None, before: _Bar, after: _Bar, div: int) -> _Bar:
    labels = [*before.voices, *(label for label in after.voices if label not in before.voices)]
    voices = {label: f"{before.voices.get(label, f'{before.length} r')} {after.voices.get(label, f'{after.length} r')}"
              for label in labels}
    words = {}
    for label in [*before.words, *(label for label in after.words if label not in before.words)]:
        tied_in = bool(previous and label in previous.voices and correct.ends_tied(previous.voices[label], div, False))
        tied_across = label in before.voices and correct.ends_tied(before.voices[label], div, tied_in)
        first = before.words.get(label) or _unsung(before.voices.get(label), div, tied_in)
        second = (_words_after_the_turn(before.voices.get(label), after.voices.get(label), after.words[label], div)
                  if label in after.words else _unsung(after.voices.get(label), div, tied_across))
        words[label] = " ".join(filter(None, (first, second)))
    chord_symbols = before.chord_symbols + [(symbol, before.length + at) for symbol, at in after.chord_symbols]
    sides = (before.changes.get("rep") in ("start", "both"), after.changes.get("rep") in ("end", "both"))
    changes = {name: value for name, value in before.changes.items() if name != "rep"} | (
        {"rep": {(True, True): "both", (True, False): "start", (False, True): "end"}[sides]} if any(sides) else {})
    return _Bar(before.length + after.length, changes, voices, words, chord_symbols,
                before.other + after.other, before.pages | after.pages, keys=before.keys | after.keys,
                opens_page=before.opens_page or after.opens_page)


def _words_after_the_turn(before: str | None, after: str | None, words: str, div: int) -> str:
    tied_in = bool(before and correct.ends_tied(before, div, False))
    if not after or not tied_in or correct.sung_notes(after, div, True) == correct.sung_notes(after, div, False):
        return words
    return " ".join(words.split()[1:])


def _unsung(body: str | None, div: int, tied_into: bool) -> str:
    return " ".join("_" * (correct.sung_notes(body, div, tied_into) if body else 0))


def _bars_as_text(bars: list[_Bar], div: int, meter: str, key: str) -> str:
    lines = [f"{notes.VERSION} div={div} ts={meter} ks={key}"]
    for number, bar in enumerate(bars, 0 if bars and _short(bars[0], div, meter) else 1):
        line = f"m{number} len={bar.length}"
        if bar.changes.get("ts", meter) != meter:
            meter = bar.changes["ts"]
            line += f" ts={meter}"
        if bar.changes.get("ks", key) != key:
            key = bar.changes["ks"]
            line += f" ks={key}"
        line += "".join(f" {name}={bar.changes[name]}" for name in ("rep", "ending") if name in bar.changes)
        lines.append(line)
        if bar.chord_symbols:
            lines.append("c: " + " ".join(f"{symbol}@{at}" for symbol, at in bar.chord_symbols))
        for label, body in bar.voices.items():
            lines.append(f"{label}: {body}")
            if label in bar.words:
                lines.append(f"{label}w: {bar.words[label]}")
        lines.extend(f"{label}w: {body}" for label, body in bar.words.items() if label not in bar.voices)
        lines.extend(bar.other)
    return "\n".join(lines)


def _empty_score(measures: list[Measure], marks: list[dict[str, str]], staves: int, clefs: dict[int, str]) -> bytes:
    root = ET.Element("score-partwise", version="4.0")
    ET.SubElement(ET.SubElement(ET.SubElement(root, "part-list"), "score-part", id="P1"), "part-name")
    part = ET.SubElement(root, "part", id="P1")
    meter = key = None
    divisions = math.lcm(DIVISIONS, *(at.denominator for measure in measures for at, _ in measure.chord_symbols))
    for position, measure in enumerate(measures):
        full = _full_length(measure)
        bar = ET.SubElement(part, "measure", number=measure.name)
        ending, before, after = (marks[at].get("ending") if 0 <= at < len(marks) else None for at in (position, position - 1, position + 1))
        if measure.length != full:
            bar.set("implicit", "yes")
        if part[0] is bar or measure.meter != meter or measure.key_signature != key:
            attributes = ET.SubElement(bar, "attributes")
            if part[0] is bar:
                ET.SubElement(attributes, "divisions").text = str(divisions)
            if measure.key_signature != key:
                key = measure.key_signature
                ET.SubElement(ET.SubElement(attributes, "key"), "fifths").text = str(note_rules.fifths(key))
            if measure.meter != meter and measure.meter:
                meter = measure.meter
                time = ET.SubElement(attributes, "time")
                ET.SubElement(time, "beats").text, ET.SubElement(time, "beat-type").text = meter.split("/")
            if part[0] is bar:
                ET.SubElement(attributes, "staves").text = str(staves)
                for staff in range(1, staves + 1):
                    sign, line, octave = notes.CLEFS[clefs.get(staff, "F" if staff == staves > 1 else "G")]
                    clef = ET.SubElement(attributes, "clef", number=str(staff))
                    ET.SubElement(clef, "sign").text, ET.SubElement(clef, "line").text = sign, str(line)
                    if octave:
                        ET.SubElement(clef, "clef-octave-change").text = str(octave)
        _bar_line(bar, "left", marks[position].get("rep") in ("start", "both"), ending if ending != before else None, "start")
        for at, symbol in measure.chord_symbols:
            bar.append(_chord_symbol(symbol, int(at * divisions)))
        for staff in range(1, staves + 1):
            if staff > 1:
                ET.SubElement(ET.SubElement(bar, "backup"), "duration").text = str(int(measure.length * divisions))
            for kind, length in [(None, measure.length)] if measure.length == full else _rests(measure):
                note = ET.SubElement(bar, "note")
                ET.SubElement(note, "rest", {} if kind else {"measure": "yes"})
                ET.SubElement(note, "duration").text = str(int(length * divisions))
                ET.SubElement(note, "voice").text = str(staff)
                if kind:
                    ET.SubElement(note, "type").text = kind
                ET.SubElement(note, "staff").text = str(staff)
        _bar_line(bar, "right", marks[position].get("rep") in ("end", "both"), ending if ending != after else None, "stop")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _bar_line(bar: ET.Element, side: str, repeat: bool, ending: str | None, kind: str) -> None:
    if not repeat and not ending:
        return
    line = ET.SubElement(bar, "barline", location=side)
    if repeat:
        ET.SubElement(line, "bar-style").text = "heavy-light" if side == "left" else "light-heavy"
    if ending:
        ET.SubElement(line, "ending", number=ending, type=kind).text = ending + "."
    if repeat:
        ET.SubElement(line, "repeat", direction="forward" if side == "left" else "backward")


def _chord_symbol(symbol: str, offset: int) -> ET.Element:
    name = CHORD_NAME.fullmatch(symbol)
    harmony = ET.Element("harmony")
    root = ET.SubElement(harmony, "root")
    ET.SubElement(root, "root-step").text = name["root"] if name else "C"
    if name and name["sign"]:
        ET.SubElement(root, "root-alter").text = str(alteration(name["sign"]))
    ET.SubElement(harmony, "kind", text=name["kind"] if name else symbol).text = "other" if name else "none"
    if name and name["bass"]:
        bass = ET.SubElement(harmony, "bass")
        ET.SubElement(bass, "bass-step").text = name["bass"]
        if name["bass_sign"]:
            ET.SubElement(bass, "bass-alter").text = str(alteration(name["bass_sign"]))
    ET.SubElement(harmony, "offset").text = str(offset)
    return harmony


def _units_in_bar(meter: str, div: int) -> int | None:
    if not meter:
        return None
    beats, unit = meter.split("/")
    return 4 * int(beats) * div // int(unit)


def _full_length(measure: Measure) -> Fraction:
    if not measure.meter:
        return measure.length
    beats, unit = measure.meter.split("/")
    return Fraction(4 * int(beats), int(unit))


def _rests(measure: Measure) -> list[tuple[str, Fraction]]:
    rests, left = [], measure.length
    for power, kind in enumerate(REST_TYPES):
        length = Fraction(4, 2**power)
        while left >= length:
            rests.append((kind, length))
            left -= length
    if left or not rests:
        raise notes.NotesError(f"Bar {measure.number}: len= gives a length no bar can have")
    return rests


def _with_every_staff(text: str, staves: int) -> str:
    lines, written, length = [], set(range(1, staves + 1)), ""

    def fill():
        lines.extend(f"{staff}.1: {length} r" for staff in range(1, staves + 1) if staff not in written)

    for line in filter(None, map(str.strip, text.splitlines())):
        if line.startswith("c:"):
            continue
        if line.startswith("m") and lines:
            fill()
            written, length = set(), line.split("len=", 1)[1].split()[0]
        elif line[0].isdigit() and not notes.WORDS_LABEL.fullmatch(line.partition(":")[0]):
            written.add(int(line.split(".", 1)[0]))
        lines.append(line)
    fill()
    return "\n".join(lines)
