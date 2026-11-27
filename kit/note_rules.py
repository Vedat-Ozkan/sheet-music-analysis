import re
from fractions import Fraction

MAX_CHARS = 200_000
MAX_STAVES = 32
MAX_VOICES = 8
MAX_BARS = 1000
MAX_BAR_LENGTH = 64
MAX_OPEN_SLURS = 16
HEADING = 'The note list must start with a "N1 page=… div=… ts=… ks=…" line, where page= is the page\'s number in the PDF'
HEADER = re.compile(r"N1 page=([1-9][0-9]*) div=([1-9][0-9]*) ts=([^\s?]*)(\??) ks=(\S+)")
BAR_LINE = re.compile(r"m(0|[1-9][0-9]*) len=([0-9]+)((?: (?:ts|ks|rep|ending)=\S+)*)")
REPEATS = ("start", "end", "both")
ENDING = re.compile(r"[1-9]")
INSTRUMENT = re.compile(r"([1-9][0-9]*)=(\S.*)")
METER = re.compile(r"[1-9][0-9]*/[1-9][0-9]*")
KEY = re.compile(r"0|[1-7][sf]")
VOICE_LABEL = re.compile(r"([0-9]+)\.([0-9]+)")
WORDS_LABEL = re.compile(r"([0-9]+)\.([0-9]+)w")
CHORD_ENTRY = re.compile(r"[^@\s]+@([0-9]+)")
CLEF = re.compile(r"clef=(G|F|C|T)(?:([_^])(8|15))?")
OCTAVE_LINE = re.compile(r"(8va|8vb|15ma|15mb)\(|\)(8va|8vb|15ma|15mb)")
LINE_OCTAVES = {"8va": 1, "8vb": -1, "15ma": 2, "15mb": -2}
NAMED_PITCH = re.compile(r"([A-G](?:#+|b+)?)([0-9])")
MARKED = re.compile(r"(\(*)(.+?)([.>]*)(\)*)")
PITCH = re.compile(r"[A-G](?:#+|b+)?[0-9]~?")
MARK = re.compile(
    r"(?P<pedal>P[du])@(?P<at1>[\d.]+)"
    r"|q=(?P<tempo>[\d.]+|[a-z]+)@(?P<at2>[\d.]+)"
    r"|(?P<hairpin>[<>])@(?P<at3>[\d.]+)\+(?P<length>[\d.]+)"
    r"|(?P<ornament>tr|mu|ml|tu|tl)@(?P<at4>[\d.]+):(?P<pitch>[A-G][#b]*\d)(?:\^(?P<upper>[a-z]+))?(?:_(?P<lower>[a-z]+))?"
    r"|(?P<dynamic>[a-z]+)@(?P<at5>[\d.]+)"
)
NOT_TEXT = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
NOTE_TYPES = ("duplex-maxima", "maxima", "longa", "breve", "whole", "half", "quarter", "eighth", "16th", "32nd", "64th",
              "128th", "256th", "512th", "1024th", "2048th")
TYPE_LENGTHS = {name: Fraction(64, 2 ** power) for power, name in enumerate(NOTE_TYPES)}
TUPLET_NUMBERS = (3, 5, 7, 11, 13)
INEXPRESSIBLE = ([("inexpressible", 0)], None)


def written_as(duration: Fraction) -> tuple[list[tuple[str, int]], tuple[int, int, str, int] | None]:
    if exact := _dotted_type(duration, 0):
        return [exact], None
    if dotted := _dotted_type(duration, 4):
        return [dotted], None
    smaller = _type_below(duration)
    if smaller is None or smaller[0] == NOTE_TYPES[0]:
        return INEXPRESSIBLE
    if tuplet := _tuplet(duration):
        return [tuplet[2:]], tuplet
    parts, left = [(smaller[0], 0)], duration - TYPE_LENGTHS[smaller[0]]
    for _ in range(8):
        if dotted := _dotted_type(left, 4):
            return parts + [dotted], None
        if (smaller := _type_below(left)) is None:
            break
        left -= TYPE_LENGTHS[smaller[0]]
        parts.append((smaller[0], 0))
    ratio = (1 / duration).limit_denominator(65535)
    spread = ratio
    while spread.numerator < spread.denominator:
        spread *= 2
    while spread.numerator > spread.denominator * 2:
        spread /= 2
    unit = _type_below(duration / spread.denominator)
    if unit is None:
        return INEXPRESSIBLE
    shown = _dotted_type(spread / ratio, 4) or INEXPRESSIBLE[0][0]
    return [shown], (spread.numerator, spread.denominator, unit[0], 0)


def _dotted_length(name: str, dots: int) -> Fraction:
    return TYPE_LENGTHS[name] * (2 - Fraction(1, 2 ** dots))


def _type_below(duration: Fraction) -> tuple[str, bool] | None:
    if not duration:
        return None
    if exact := next((name for name, length in TYPE_LENGTHS.items() if length == duration), None):
        return exact, True
    if below := next((name for name, length in TYPE_LENGTHS.items() if duration / 2 < length < duration), None):
        return below, False
    return (NOTE_TYPES[0], False) if duration > 128 else None


def _dotted_type(duration: Fraction, most_dots: int) -> tuple[str, int] | None:
    for dots in range(most_dots + 1):
        found = _type_below(duration / (2 - Fraction(1, 2 ** dots)))
        if found and found[1]:
            return found[0], dots
    return None


def _tuplet(duration: Fraction) -> tuple[int, int, str, int] | None:
    for name in reversed(NOTE_TYPES):
        for notes in TUPLET_NUMBERS:
            for taken in range(1, notes):
                for dots in (0, 1):
                    if _dotted_length(name, dots) / notes * taken == duration:
                        return notes, taken, name, dots
    return None


def writable(duration: Fraction) -> bool:
    shapes, tuplet = written_as(duration)
    return shapes[0][0] != "inexpressible" and (tuplet is None or tuplet[2] == shapes[0][0])


def page_number(text: str) -> int | None:
    head = HEADER.fullmatch(next((line.strip() for line in text.splitlines() if line.strip()), ""))
    return int(head[1]) if head else None


def problems(text: str) -> list[str]:
    if len(text) > MAX_CHARS:
        return ["The note list is too long"]
    if NOT_TEXT.search(text):
        return ["The note list holds a control character; write only plain text"]
    numbered = [(number, line.strip()) for number, line in enumerate(text.splitlines(), 1) if line.strip()]
    head = HEADER.fullmatch(numbered[0][1]) if numbered else None
    if not head:
        return [HEADING]
    div = int(head[2])
    found = _signature_problems(head[3], head[5])
    if found:
        return found
    meter, bars, named = head[3], [], None
    for number, line in numbered[1:]:
        if line.startswith("m"):
            bar = BAR_LINE.fullmatch(line)
            if not bar:
                return found + [f"a bar line looks like 'm3 len=96', not {line!r}"]
            changes = dict(change.split("=", 1) for change in bar[3].split())
            if signatures := _signature_problems(changes.get("ts", meter), changes.get("ks", "0")) + _bar_line_problems(changes):
                return found + signatures
            meter = changes.get("ts", meter)
            bars.append({"name": bar[1], "units": int(bar[2]), "meter": meter, "lines": []})
        elif not bars and line.startswith("i:") and named is None:
            named = instruments(line)
            if named is None:
                return found + [f"Line {number}: the instruments line looks like 'i: 1=Flute 2=Clarinet in Bb', one "
                                f"number=name for each staff, numbered 1 to {MAX_STAVES} from the top"]
        elif not bars:
            kind = {"x:": "a marks line", "c:": "a chord symbol line"}.get(line[:2], "a voice line")
            found.append(f"Line {number}: {kind} needs a bar line like 'm3 len=96' before it")
        elif line.startswith(("x:", "c:")):
            bars[-1]["lines"].append((line[0], line[2:].split()))
        else:
            label, _, body = line.partition(":")
            if not VOICE_LABEL.fullmatch(label) and not WORDS_LABEL.fullmatch(label):
                found.append(f"Line {number}: expected 'staff.voice: tokens', e.g. '1.1: 24 C4'")
            else:
                bars[-1]["lines"].append((label, body.split()))
    if not bars:
        return found or ["The note list has no measures"]
    if len(bars) > MAX_BARS:
        found.append(f"The note list has {len(bars)} bars; at most {MAX_BARS} can be built")
    found += _bar_problems(bars, div)
    if named is not None:
        found += [f"Staff {staff} has no name in the i: line; name every staff of the page there"
                  for staff in sorted({int(label.split(".")[0]) for bar in bars for label, _ in bar["lines"]
                                       if VOICE_LABEL.fullmatch(label)} - set(named))]
    return found


def instruments(line: str) -> dict[int, str] | None:
    entries = [INSTRUMENT.fullmatch(entry) for entry in re.split(r"\s+(?=[0-9]+=)", re.sub(r"^concert\s+", "", line[2:].strip()))]
    if not all(entries) or len({entry[1] for entry in entries}) != len(entries) or any(int(entry[1]) > MAX_STAVES for entry in entries):
        return None
    return {int(entry[1]): " ".join(entry[2].split()) for entry in entries}


def clef_octaves(clef: re.Match) -> int:
    return 0 if not clef[2] else (1 if clef[3] == "8" else 2) * (1 if clef[2] == "^" else -1)


def as_sounding(voices: list[tuple[str, list[str]]], div: int, octaves: dict[int, tuple[int, int]]) -> list[tuple[str, list[str]]]:
    changes, placed = {}, []
    for label, tokens in voices:
        staff, cursor, duration, kept = int(label.split(".")[0]), 0, 0, []
        for token in tokens:
            if token.isdigit():
                duration = int(token)
            elif clef := CLEF.fullmatch(token):
                changes.setdefault(staff, []).append((cursor, 0, clef_octaves(clef)))
            elif line := OCTAVE_LINE.fullmatch(token):
                changes.setdefault(staff, []).append((cursor, 1, LINE_OCTAVES.get(line[1], 0)))
                continue
            else:
                kept.append((cursor, token))
                cursor += 0 if token.lstrip("(").startswith(("g", "u")) else duration
                continue
            kept.append((None, token))
        placed.append((label, staff, kept))
    sounding = []
    for label, staff, kept in placed:
        tokens = []
        for onset, token in kept:
            if onset is not None:
                state = list(octaves.get(staff, (0, 0)))
                for at, kind, value in sorted(changes.get(staff, []), key=lambda change: change[0]):
                    if at <= onset:
                        state[kind] = value
                token = NAMED_PITCH.sub(lambda pitch: f"{pitch[1]}{int(pitch[2]) + sum(state)}", token) if sum(state) else token
            tokens.append(token)
        sounding.append((label, tokens))
    for staff, found in changes.items():
        state = list(octaves.get(staff, (0, 0)))
        for _, kind, value in sorted(found, key=lambda change: change[0]):
            state[kind] = value
        octaves[staff] = tuple(state)
    return sounding


def join_problems(pages: list[str]) -> list[str]:
    bars = sum(1 for page in pages for line in page.splitlines() if line.strip().startswith("m"))
    if bars > MAX_BARS:
        return [f"The pages have {bars} bars together; at most {MAX_BARS} can be built"]
    if sum(map(len, pages)) > MAX_CHARS:
        return [f"The pages are longer than {MAX_CHARS} characters together"]
    return []


def _signature_problems(meter: str, key: str) -> list[str]:
    if not METER.fullmatch(meter):
        return [f"A time signature looks like ts=3/4, not ts={meter}"]
    if not KEY.fullmatch(key):
        return [f"A key signature looks like ks=0, ks=2s or ks=3f, not ks={key}"]
    return []


def _full(meter: str) -> Fraction:
    beats, unit = meter.split("/")
    return Fraction(4 * int(beats), int(unit))


def _bar_problems(bars: list[dict], div: int) -> list[str]:
    found = []
    previous = None
    staves = max([int(VOICE_LABEL.fullmatch(label)[1]) for bar in bars for label, tokens in bar["lines"]
                  if VOICE_LABEL.fullmatch(label) and any(_pitched(token) for token in tokens)] or [1])
    held, open_slurs, taken, octaves, open_lines = {}, {}, 0, {}, {}
    for bar in bars:
        name, length, full = bar["name"], Fraction(bar["units"], div), _full(bar["meter"])
        if previous is not None and int(name) <= int(previous):
            found.append(f"Bar {name}: bar numbers go up from one bar to the next, and m{previous} comes before it")
        previous = name
        if length > MAX_BAR_LENGTH:
            found.append(f"Bar {name}: len= makes this bar longer than {MAX_BAR_LENGTH} quarter notes")
        if length != full and (not length or (length * 32).denominator != 1):
            found.append(f"Bar {name}: len= gives a length no bar can have")
        voices, written = {}, set()
        lines = bar["lines"]
        played = [position for position, (label, _) in enumerate(lines) if VOICE_LABEL.fullmatch(label)]
        for position, (label, tokens) in zip(played, as_sounding([lines[position] for position in played], div, octaves)):
            lines = lines[:position] + [(label, tokens)] + lines[position + 1:]
            staff = int(label.split(".")[0])
            for token in bar["lines"][position][1]:
                if line := OCTAVE_LINE.fullmatch(token):
                    open_lines[staff] = open_lines.get(staff, 0) + (1 if line[1] else -1)
                    if open_lines[staff] < 0:
                        found.append(f"Bar {name}, staff {staff}: an octave line ends here that was never started; "
                                     "write 8va( before the first note under it")
                        open_lines[staff] = 0
        for label, tokens in lines:
            if label == "x":
                found += _mark_problems(tokens)
            elif label == "c":
                found += [f"Bar {name}: a chord symbol is written as symbol@position, without spaces, with the position "
                          f"in units from the start of the bar and below its len, e.g. D7@0, not {entry!r}"
                          for entry in tokens if not (at := CHORD_ENTRY.fullmatch(entry)) or Fraction(int(at[1]), div) >= length]
            elif words := WORDS_LABEL.fullmatch(label):
                voice = (int(words[1]), int(words[2]))
                if voice not in voices:
                    found.append(f"Bar {name}: the words line {label} needs its voice line {label[:-1]} before it")
                    continue
                sung = _sung(voices[voice][1], held.get(voice + ("before",), False))
                if len(tokens) != sung:
                    found.append(f"Bar {name}, {label}: {len(tokens)} entries for {sung} sung notes; write one entry for "
                                 "each note that is not a rest, a grace note or the continuation of a tie, and _ where no "
                                 "syllable is printed")
            else:
                staff, number = map(int, VOICE_LABEL.fullmatch(label).groups())
                if staff > MAX_STAVES or number > MAX_VOICES:
                    found.append(f"Staves are numbered 1 to {MAX_STAVES} from the top and voices 1 to {MAX_VOICES}")
                    continue
                if not staff or not number or (staff, number) in voices:
                    found.append(f"Bar {name}: invalid or repeated voice {label}")
                    continue
                if staff > staves:
                    found.append(f"Bar {name}: include all {staves} staves")
                written.add(staff)
                total, groups, problems_here = _read_voice(tokens, div, name, length)
                found += problems_here
                if not problems_here and total != length:
                    found.append(f"Bar {name}, voice {staff}.{number} adds up to {total}; expected {length} quarter notes")
                voices[(staff, number)] = (total, groups)
                held[(staff, number, "before")] = held.get((staff, number), False)
                held[(staff, number)] = _held_after(groups, held[(staff, number, "before")])
        for staff in set(range(1, staves + 1)) - written:
            held[(staff, 1)] = False
        if any(grace or names != "r" for _, groups in voices.values() for names, grace, _, _ in groups) \
                or any(number != 1 for _, number in voices):
            for voice in sorted(voices):
                for names, grace, opened, closed in voices[voice][1]:
                    for _ in range(opened):
                        if taken == MAX_OPEN_SLURS:
                            found.append(f"Bar {name}, voice {voice[0]}.{voice[1]}: more than {MAX_OPEN_SLURS} slurs are open at once")
                            break
                        taken += 1
                        open_slurs[voice] = open_slurs.get(voice, 0) + 1
                    for _ in range(closed):
                        if not open_slurs.get(voice):
                            found.append(f"Bar {name}, voice {voice[0]}.{voice[1]}: a slur ends here that was never "
                                         "started; write ( before its first note")
                            break
                        taken -= 1
                        open_slurs[voice] -= 1
    found += [f"A slur starts in voice {staff}.{number} and never ends; close it with ) after its last note"
              for (staff, number), count in open_slurs.items() if count]
    found += [f"An octave line starts in staff {staff} and never ends; close it with )8va (or )8vb, )15ma, )15mb) "
              "after the last note under it" for staff, count in open_lines.items() if count]
    return found


def _bar_line_problems(changes: dict[str, str]) -> list[str]:
    found = []
    if changes.get("rep", "start") not in REPEATS:
        found.append(f"A repeat sign is written rep=start, rep=end or rep=both, not rep={changes['rep']}")
    if not ENDING.fullmatch(changes.get("ending", "1")):
        found.append(f"An ending is written ending=1, ending=2 and so on, not ending={changes['ending']}")
    return found


def _pitched(token: str) -> bool:
    return not token.isdigit() and not CLEF.fullmatch(token) and not OCTAVE_LINE.fullmatch(token) and MARKED.fullmatch(token)[2] != "r"


def _read_voice(tokens: list[str], div: int, name: str, length: Fraction):
    duration, total, groups, found = None, Fraction(0), [], []
    for written in tokens:
        if written.isdigit():
            duration = Fraction(int(written), div)
            if not duration:
                found.append(f"Bar {name}: duration must be positive")
            continue
        if CLEF.fullmatch(written):
            continue
        opened, sounding, _, closed = MARKED.fullmatch(written).groups()
        grace = sounding.startswith(("g", "u"))
        names = sounding[1:] if grace else sounding
        if grace and names == "r":
            found.append("Grace rests are not supported")
            continue
        if names != "r" and any(not PITCH.fullmatch(pitch) for pitch in names.split("+")):
            found.append(f"Bar {name}: invalid pitch {names!r}")
            continue
        if not grace and duration is None:
            found.append(f"Bar {name}: note/rest has no duration")
            continue
        groups.append((names, grace, len(opened), len(closed)))
        if not grace:
            total += duration
            if duration and not (writable(duration) or duration == length):
                found.append(f"Bar {name}: a duration of {duration * div} at div={div} cannot be written as one note; use "
                             "plain or dotted note values, notes of a simple tuplet such as a triplet, or tied notes")
    return total, groups, list(dict.fromkeys(found))


def _held_after(groups: list[tuple], held: bool) -> bool:
    for names, grace, _, _ in groups:
        if not grace:
            held = names != "r" and "~" in names
    return held


def _sung(groups: list[tuple], held: bool) -> int:
    sung = 0
    for names, grace, _, _ in groups:
        if grace or names == "r":
            held = held and grace
            continue
        sung += not held
        held = "~" in names
    return sung


def _mark_problems(tokens: list[str]) -> list[str]:
    found = []
    for token in tokens:
        mark = MARK.fullmatch(token)
        try:
            [Fraction(value) for key, value in mark.groupdict().items() if value and (key.startswith("at") or key == "length")]
        except (AttributeError, ValueError):
            found.append(f"The note list could not be read: unknown mark {token!r}")
    return found
