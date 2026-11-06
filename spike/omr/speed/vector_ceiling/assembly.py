import collections
import itertools
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ceiling  # noqa: E402

LENGTH = {"breve": Fraction(8), "whole": Fraction(4), "half": Fraction(2), "quarter": Fraction(1),
          "eighth": Fraction(1, 2), "16th": Fraction(1, 4), "32nd": Fraction(1, 8), "64th": Fraction(1, 16),
          "128th": Fraction(1, 32)}


def truth_timing(path: Path):
    data = path.read_bytes()
    if data[:2] == b"PK":
        archive = zipfile.ZipFile(path)
        name = next(n for n in archive.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
        data = archive.read(name)
    root = ET.fromstring(data)
    staves = []
    for part in root.iter("part"):
        count, divisions, length = 1, 1, Fraction(4)
        bars = []
        for measure in part.iter("measure"):
            for element in measure.iter("staves"):
                count = int(element.text)
            for element in measure.iter("divisions"):
                divisions = int(element.text)
            for element in measure.iter("time"):
                beats, kind = element.findtext("beats"), element.findtext("beat-type")
                if beats and kind and beats.isdigit():
                    length = Fraction(int(beats) * 4, int(kind))
            cursor, last, end = Fraction(0), Fraction(0), Fraction(0)
            events = collections.defaultdict(collections.Counter)
            for child in measure:
                if child.tag == "backup":
                    cursor -= Fraction(int(child.findtext("duration")), divisions)
                elif child.tag == "forward":
                    cursor += Fraction(int(child.findtext("duration")), divisions)
                elif child.tag == "note":
                    if child.find("grace") is not None or child.find("cue") is not None:
                        continue
                    duration = Fraction(int(child.findtext("duration") or 0), divisions)
                    if child.find("chord") is not None:
                        continue
                    start = cursor
                    cursor += duration
                    end = max(end, cursor)
                    if child.get("print-object") == "no":
                        continue
                    staff = int(child.findtext("staff") or 1)
                    events[staff][(start, duration, child.find("rest") is not None)] += 1
            bars.append((events, min(length, end) if end else length, length))
        for staff in range(1, count + 1):
            staves.append([(bar[0][staff], bar[1], bar[2]) for bar in bars])
    return staves


def length_of(event, factor=Fraction(1)):
    base = LENGTH[event["value"]]
    return base * (2 - Fraction(1, 2 ** event["dots"])) * factor


def beam_groups(voice):
    groups, seen = [], set()
    for i, event in enumerate(voice):
        if i in seen or not event["beams"]:
            continue
        group, frontier = {i}, [i]
        while frontier:
            k = frontier.pop()
            for j, other in enumerate(voice):
                if j not in group and other["beams"] & voice[k]["beams"]:
                    group.add(j)
                    frontier.append(j)
        seen |= group
        groups.append(sorted(group))
    return groups


def tuplet_factor(number):
    lower = 1
    while lower * 2 < number:
        lower *= 2
    return Fraction(lower, number)


def place(voice, marks, bar_length, known_triplets=()):
    groups = beam_groups(voice)
    factors = [Fraction(1)] * len(voice)
    for k in known_triplets:
        factors[k] = Fraction(2, 3)
    for mark in marks:
        if groups:
            group = min(groups, key=lambda g: min(abs(voice[k]["x"] - mark["x"]) for k in g))
        else:
            group = sorted(range(len(voice)), key=lambda k: abs(voice[k]["x"] - mark["x"]))[:mark["tuplet"]]
        for k in group:
            factors[k] = tuplet_factor(mark["tuplet"])

    def timed(chosen):
        local = list(factors)
        for group in chosen:
            for k in group:
                local[k] = Fraction(2, 3)
        out, cursor = [], Fraction(0)
        for event, factor in zip(voice, local):
            length = length_of(event, factor)
            out.append((cursor, length, event["rest"]))
            cursor += length
        return out, cursor

    out, total = timed([])
    if total == bar_length or not voice:
        return out, total
    candidates = [g for g in groups if len(g) in (3, 6) and len({voice[k]["value"] for k in g}) == 1
                  and all(factors[k] == 1 for k in g)]
    for size in range(1, min(len(candidates), 8) + 1):
        for chosen in itertools.combinations(candidates, size):
            attempt, total = timed(chosen)
            if total == bar_length:
                return attempt, total
    return out, total


ONE_VOICE_FIRST = "--one-voice-first" in sys.argv


def assemble(bar, bar_length):
    events = sorted((e for e in bar if "tuplet" not in e), key=lambda e: e["x"])
    marks = [e for e in bar if "tuplet" in e]
    stems = {e["up"] for e in events if not e["rest"] and e["up"] is not None}
    if ONE_VOICE_FIRST and len(stems) > 1:
        single, total = place(events, marks, bar_length)
        if total == bar_length:
            return collections.Counter(single), 1, bool(marks)
    if len(stems) <= 1:
        voices = [events]
    else:
        voices = [[e for e in events if e["up"] or (e["up"] is None and not e["rest"])],
                  [e for e in events if e["up"] is False]]
    placed = collections.Counter()
    for voice in voices:
        mine = [m for m in marks if voice and min(abs(e["x"] - m["x"]) for e in voice) < 30]
        out, _ = place(voice, mine, bar_length)
        placed.update(out)
    return placed, len(voices), bool(marks)


def main():
    manifest = json.loads((ceiling.BENCH / "manifest.json").read_text())["pieces"]
    totals = collections.Counter()
    for pdf in sorted((ceiling.BENCH / "pdfs").glob("*--*.pdf")):
        piece, engraver = pdf.stem.rsplit("--", 1)
        if engraver not in ("ms", "ly"):
            continue
        truth_path = ceiling.BENCH / manifest[piece]["truth"]
        symbols_truth = ceiling.truth_bars(truth_path)
        timing = truth_timing(truth_path)
        rows = ceiling.read_pdf(pdf)
        n = len(symbols_truth)
        if n == 0 or len(rows) % n or len(timing) != n:
            continue
        systems = [rows[k:k + n] for k in range(0, len(rows), n)]
        bars = [[bar for system in systems for bar in system[i]] for i in range(n)]
        for i in range(n):
            read_symbols = [ceiling.symbols(bar) for bar in bars[i]]
            for r, t in ceiling.align(read_symbols, symbols_truth[i]):
                if read_symbols[r] != symbols_truth[i][t] or not symbols_truth[i][t]:
                    continue
                want, content, written = timing[i][t]
                got, voices, marked = assemble(bars[i][r], content)
                kind = "one voice" if voices == 1 else "two voices"
                has_tuplet = any(length.denominator % 3 == 0 for _, length, _ in want)
                ok = got == want
                for key in ("all", engraver, kind) + (("tuplets",) if has_tuplet else ()) + (("printed tuplet",) if marked else ()):
                    totals[(key, "tested")] += 1
                    totals[(key, "matched")] += ok
    for key in ("all", "ms", "ly", "one voice", "two voices", "tuplets", "printed tuplet"):
        tested = totals[(key, "tested")]
        if tested:
            print(f"{key:15} {totals[(key, 'matched')]}/{tested} = {totals[(key, 'matched')] / tested:.3f}")


if __name__ == "__main__":
    main()
