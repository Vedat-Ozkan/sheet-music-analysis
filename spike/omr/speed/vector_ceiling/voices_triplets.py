import collections
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assembly
import ceiling

assembly.ONE_VOICE_FIRST = True

ON_MIDDLE_LINE = 0.25
SAME_START = 1.3
COLUMN_TOLERANCE = 1.0


def head_x(event):
    return min(member[2] for member in event["members"])


def against_middle_line(event):
    if event["rest"] or event["up"] is None or event["beams"]:
        return False
    offsets = [member[3] - event["middle"] for member in event["members"]]
    farthest = max(abs(offset) for offset in offsets)
    if farthest <= ON_MIDDLE_LINE * event["space"]:
        return False
    sides = {offset > 0 for offset in offsets if abs(offset) == farthest}
    return sides == {event["up"]}


def two_stems_at_one_start(events):
    stemmed = [e for e in events if not e["rest"] and e["up"] is not None]
    return any(a["up"] != b["up"] and abs(head_x(a) - head_x(b)) <= SAME_START * a["space"]
               for i, a in enumerate(stemmed) for b in stemmed[i + 1:])


def stem_rule_fires(events):
    return any(against_middle_line(e) for e in events) or two_stems_at_one_start(events)


def split_by_stem(events):
    return [[e for e in events if e["up"] or (e["up"] is None and not e["rest"])],
            [e for e in events if e["up"] is False]]


def marks_near(voice, marks):
    return [m for m in marks if voice and min(abs(e["x"] - m["x"]) for e in voice) < 30]


def voices_of(bar, bar_length, use_stem_rule=False, columns=None):
    events = sorted((e for e in bar if "tuplet" not in e), key=lambda e: e["x"])
    marks = [e for e in bar if "tuplet" in e]
    stems = {e["up"] for e in events if not e["rest"] and e["up"] is not None}
    fired = use_stem_rule and stem_rule_fires(events)
    groups = clock_groups(events, columns) if columns else []
    if len(stems) > 1 and not fired:
        single, total = assembly.place(events, marks, bar_length, groups)
        if total == bar_length:
            return [(events, single)], len(groups), fired
    voices = [events] if len(stems) <= 1 else split_by_stem(events)
    placed, count = [], 0
    for voice in voices:
        known = clock_groups(voice, columns) if columns else []
        count += len(known)
        out, _ = assembly.place(voice, marks_near(voice, marks), bar_length, known)
        placed.append((voice, out))
    return placed, count, fired


def clock_columns(bar, bar_length):
    placed, _, _ = voices_of(bar, bar_length)
    columns = {}
    for voice, out in placed:
        if voice and sum(length for _, length, _ in out) != bar_length:
            return None
        for event, (start, _, _) in zip(voice, out):
            columns[start] = min(columns.get(start, float("inf")), head_x(event))
    columns[0] = float("-inf")
    columns[bar_length] = float("inf")
    return columns


def clock_groups(voice, columns):
    chosen = []
    for t, left in columns.items():
        for right_time, right in columns.items():
            distance = right_time - t
            if distance <= 0 or t % distance:
                continue
            inside = [k for k, e in enumerate(voice)
                      if left - COLUMN_TOLERANCE * e["space"] <= head_x(e) < right - COLUMN_TOLERANCE * e["space"]]
            if len(inside) != 3:
                continue
            members = [voice[k] for k in inside]
            if any(e["rest"] for e in members) or len({(e["value"], e["dots"]) for e in members}) != 1:
                continue
            if 2 * assembly.length_of(members[0]) == distance:
                chosen.extend(inside)
    return sorted(set(chosen))


def counter_of(placed):
    total = collections.Counter()
    for _, out in placed:
        total.update(out)
    return total


def has_triplet_length(events):
    return any(length.denominator % 3 == 0 for _, length, _ in events)


def truth_voice_events(path):
    data = path.read_bytes()
    if data[:2] == b"PK":
        archive = zipfile.ZipFile(path)
        name = next(n for n in archive.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
        data = archive.read(name)
    staves = []
    for part in ET.fromstring(data).iter("part"):
        count, bars = 1, []
        for measure in part.iter("measure"):
            for element in measure.iter("staves"):
                count = int(element.text)
            voices = collections.defaultdict(collections.Counter)
            for note in measure.iter("note"):
                if note.find("chord") is not None or note.find("grace") is not None or note.find("cue") is not None:
                    continue
                if note.get("print-object") == "no":
                    continue
                voices[int(note.findtext("staff") or 1)][note.findtext("voice") or "1"] += 1
            bars.append(voices)
        for staff in range(1, count + 1):
            staves.append([bar[staff] for bar in bars])
    return staves


def failure_cause(events, want, true_voices):
    up = sum(1 for e in events if e["up"] is True or (e["up"] is None and not e["rest"]))
    down = sum(1 for e in events if e["up"] is False)
    if has_triplet_length(want):
        return "triplets in the bar"
    if len(true_voices) <= 1:
        return "truth is one voice, it did not fill"
    if len(true_voices) > 2:
        return "three or more voices"
    if any(e["up"] is None and not e["rest"] for e in events):
        return "stemless heads (whole notes)"
    if sorted((up, down)) != sorted(true_voices.values()):
        return "stem directions do not partition the true voices"
    return "same note counts, starts wrong (a voice enters late or has gaps)"


class Score:
    def __init__(self):
        self.tested = collections.Counter()
        self.matched = collections.Counter()

    def add(self, keys, ok):
        for key in keys:
            self.tested[key] += 1
            self.matched[key] += ok

    def line(self, key):
        tested, matched = self.tested[key], self.matched[key]
        return f"{key:32} {matched}/{tested} = {matched / tested:.3f}" if tested else f"{key:32} 0/0"


def main():
    manifest = json.loads((ceiling.BENCH / "manifest.json").read_text())["pieces"]
    base, stem, clock = Score(), Score(), Score()
    counts = collections.Counter()
    causes = collections.Counter()
    for pdf in sorted((ceiling.BENCH / "pdfs").glob("*--*.pdf")):
        piece, engraver = pdf.stem.rsplit("--", 1)
        if engraver not in ("ms", "ly"):
            continue
        truth_path = ceiling.BENCH / manifest[piece]["truth"]
        symbols_truth = ceiling.truth_bars(truth_path)
        timing = assembly.truth_timing(truth_path)
        true_voices = truth_voice_events(truth_path)
        rows = ceiling.read_pdf(pdf)
        n = len(symbols_truth)
        if n == 0 or len(rows) % n or len(timing) != n:
            continue
        systems = [rows[k:k + n] for k in range(0, len(rows), n)]
        bars = [[bar for system in systems for bar in system[i]] for i in range(n)]
        system_of = [[index for index, system in enumerate(systems) for _ in system[i]] for i in range(n)]
        exact = []
        for i in range(n):
            read_symbols = [ceiling.symbols(bar) for bar in bars[i]]
            exact.append({t: r for r, t in ceiling.align(read_symbols, symbols_truth[i])
                          if read_symbols[r] == symbols_truth[i][t] and symbols_truth[i][t]})
        for i in range(n):
            for t, r in exact[i].items():
                want, content, _ = timing[i][t]
                bar = bars[i][r]
                baseline, _, _ = voices_of(bar, content)
                base_ok = counter_of(baseline) == want
                bucket = "one voice" if len(baseline) == 1 else "two voices"
                triplet_bar = has_triplet_length(want)
                truth_count = len(true_voices[i][t])
                truth_key = "truth one voice" if truth_count <= 1 else "truth two or more voices"
                keys = ["all", engraver, bucket, truth_key] + (["triplets"] if triplet_bar else ["non-triplet"])
                base.add(keys, base_ok)

                events = [e for e in bar if "tuplet" not in e]
                with_rule, _, fired = voices_of(bar, content, use_stem_rule=True)
                rule_ok = counter_of(with_rule) == want
                stem.add(keys, rule_ok)
                counts[("fires", bucket)] += fired
                counts[("fires", truth_key)] += fired
                counts[("stem", "worse" if base_ok and not rule_ok else "better" if rule_ok and not base_ok else "same", bucket)] += 1
                if bucket == "two voices" and not base_ok:
                    causes[failure_cause(events, want, true_voices[i][t])] += 1

                usable = []
                for j in range(n):
                    if j == i or t not in exact[j] or system_of[j][exact[j][t]] != system_of[i][r]:
                        continue
                    columns = clock_columns(bars[j][exact[j][t]], timing[j][t][1])
                    if columns:
                        usable.append(columns)
                merged = {}
                for columns in usable:
                    for time, x in columns.items():
                        merged[time] = min(merged.get(time, float("inf")), x)
                situation = "solo line" if n == 1 else "clock usable" if merged else "clock unusable"
                counts[("situation", "all", situation)] += 1
                if triplet_bar:
                    counts[("situation", "triplets", situation)] += 1
                timed, groups, _ = voices_of(bar, content, columns=merged or None)
                clock_ok = counter_of(timed) == want
                clock.add(keys, clock_ok)
                if triplet_bar:
                    clock.add(["triplets: " + situation], clock_ok)
                    base.add(["triplets: " + situation], base_ok)
                    counts[("triplet bars with a clock group",)] += bool(groups)
                else:
                    counts[("non-triplet bars with a clock group",)] += bool(groups)
                    counts[("non-triplet matched to unmatched",)] += base_ok and not clock_ok
                    counts[("non-triplet unmatched to matched",)] += clock_ok and not base_ok
                    counts[("non-triplet reading a triplet, baseline",)] += has_triplet_length(counter_of(baseline))
                    counts[("non-triplet reading a triplet, clock",)] += has_triplet_length(counter_of(timed))
    names = ("all", "ms", "ly", "one voice", "two voices", "triplets", "non-triplet", "truth one voice", "truth two or more voices")
    for title, score in (("baseline", base), ("test 4 stem rule", stem), ("test 5 clock", clock)):
        print(f"--- {title}")
        for key in names:
            print(score.line(key))
    print("--- triplet bars by situation: baseline, then clock")
    for situation in ("solo line", "clock unusable", "clock usable"):
        print(base.line("triplets: " + situation))
        print(clock.line("triplets: " + situation))
    print("--- counts")
    for key, value in sorted(counts.items(), key=str):
        print(key, value)
    print("--- baseline failures among the two-voice bucket, by cause (exploratory)")
    for key, value in causes.most_common():
        print(value, key)


if __name__ == "__main__":
    main()
