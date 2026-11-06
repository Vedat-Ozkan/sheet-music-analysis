import collections
import json
import statistics
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pikepdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract as ex  # noqa: E402
import vector_notes as vn  # noqa: E402

BENCH = Path(__file__).resolve().parents[2] / "bench"
LADDER = ["breve", "whole", "half", "quarter", "eighth", "16th", "32nd", "64th", "128th"]
HEAD_WIDTH = {"black": 1.18, "half": 1.18, "whole": 1.69, "breve": 2.0}


def truth_bars(path: Path):
    data = path.read_bytes()
    if data[:2] == b"PK":
        archive = zipfile.ZipFile(path)
        name = next(n for n in archive.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
        data = archive.read(name)
    root = ET.fromstring(data)
    staves = []
    for part in root.iter("part"):
        count = 1
        bars = []
        for measure in part.iter("measure"):
            for element in measure.iter("staves"):
                count = int(element.text)
            events = collections.defaultdict(collections.Counter)
            for note in measure.iter("note"):
                if note.find("chord") is not None or note.find("grace") is not None or note.find("cue") is not None:
                    continue
                if note.get("print-object") == "no":
                    continue
                rest = note.find("rest")
                kind = note.findtext("type")
                if rest is not None and (rest.get("measure") == "yes" or kind is None):
                    kind = "whole"
                staff = int(note.findtext("staff") or 1)
                events[staff][(rest is not None, kind, len(note.findall("dot")))] += 1
            bars.append(events)
        for staff in range(1, count + 1):
            staves.append([bar[staff] for bar in bars])
    return staves


def read_pdf(path: Path):
    pdf = pikepdf.open(path)
    rows = []
    for page in pdf.pages:
        glyphs, lines, polygons = ex.page_drawing(page)
        horizontals, verticals, beams = ex.segments(lines, polygons)
        staves = sorted(vn.staves(horizontals), key=lambda s: -s["high"])
        if not staves:
            continue
        sizes = [g[4] for g in glyphs if g[0] == "head"]
        normal = statistics.median(sizes) if sizes else 0
        for index, staff in enumerate(staves):
            rows.append(staff_bars(staff, staves, glyphs, verticals, beams, normal))
    return rows


def nearest_staff(y, staves):
    return min(range(len(staves)), key=lambda i: 0 if staves[i]["low"] <= y <= staves[i]["high"]
               else min(abs(y - staves[i]["low"]), abs(y - staves[i]["high"])))


def staff_bars(staff, staves, glyphs, verticals, beams, normal):
    s = staff["space"]
    me = staves.index(staff)
    mine = [g for g in glyphs if nearest_staff(g[3], staves) == me]
    heads = [g for g in mine if g[0] == "head" and g[4] >= 0.8 * normal]
    rests = [g for g in mine if g[0] == "rest"]
    flags = [g for g in mine if g[0] == "flag" and g[4] >= 0.8 * normal]
    dots = [g for g in mine if g[0] == "dot"]
    bounds = [b for other in staves for b in (other["low"], other["high"])]
    every_head = [g for g in glyphs if g[0] == "head"]

    def on_line(y):
        return any(abs(y - b) < 0.25 * s for b in bounds)

    def touches_head(x, y):
        return any(abs(h[3] - y) < 0.8 * s and h[2] - 0.5 * s <= x <= h[2] + 2.2 * s for h in every_head)

    barlines = [(x, y0, y1) for x, y0, y1, w in verticals
                if y0 <= staff["low"] + 0.3 * s and y1 >= staff["high"] - 0.3 * s and staff["x0"] - s <= x <= staff["x1"] + s
                and on_line(y0) and on_line(y1) and not touches_head(x, y0) and not touches_head(x, y1)]
    bars = sorted({round(x, 1) for x, y0, y1 in barlines})
    merged = []
    for x in bars:
        if merged and x - merged[-1] < 1.5 * s:
            merged[-1] = x
        else:
            merged.append(x)
    edges = [x for x in merged if x > staff["x0"] + 1.5 * s]
    if not edges or edges[-1] < staff["x1"] - 1.5 * s:
        edges.append(staff["x1"])
    stems = [(x, y0, y1) for x, y0, y1, w in verticals
             if w < 0.3 * s and 1.5 * s <= y1 - y0 <= 9 * s and staff["x0"] <= x <= staff["x1"]
             and (x, y0, y1) not in barlines]
    attached = collections.defaultdict(list)
    loose = []
    for head in heads:
        _, kind, x, y, _ = head
        width = HEAD_WIDTH[kind] * s
        options = [(min(abs(sx - x), abs(sx - x - width)), i) for i, (sx, y0, y1) in enumerate(stems)
                   if x - 0.3 * s <= sx <= x + width + 0.3 * s and y0 - 0.6 * s <= y <= y1 + 0.6 * s]
        if options and kind in ("black", "half"):
            attached[min(options)[1]].append(head)
        else:
            loose.append(head)
    events = []
    for i, members in attached.items():
        sx, y0, y1 = stems[i]
        head_ys = [h[3] for h in members]
        far = y1 if abs(min(head_ys) - y0) < abs(max(head_ys) - y1) else y0
        kind = "black" if any(h[1] == "black" for h in members) else members[0][1]
        level = LADDER.index("quarter") if kind == "black" else LADDER.index(kind)
        if kind == "black":
            flag = [f[1] for f in flags if abs(f[2] - sx) < 0.6 * s and abs(f[3] - far) < 1.5 * s]
            toward = 1 if statistics.mean(head_ys) > far else -1
            stacked, reach, used = 0, 1.1 * s, set()
            for offset, index in sorted(((beam_y(b, sx) - far) * toward, k) for k, b in enumerate(beams)
                                        if b[0] - 0.2 * s <= sx <= b[1] + 0.2 * s):
                if -0.3 * s <= offset <= reach:
                    stacked += 1
                    used.add(index)
                    reach = offset + 1.0 * s
            level += max(flag) if flag else stacked
        else:
            used = set()
        events.append({"x": sx, "members": members, "value": LADDER[min(level, len(LADDER) - 1)], "rest": False,
                       "up": far > statistics.mean(head_ys), "beams": used})
    columns = []
    for head in sorted(loose, key=lambda h: h[2]):
        if columns and abs(head[2] - columns[-1][0][2]) < 0.6 * s and head[1] == columns[-1][0][1]:
            columns[-1].append(head)
        else:
            columns.append([head])
    for column in columns:
        kind = column[0][1]
        events.append({"x": column[0][2], "members": column, "value": "quarter" if kind == "black" else kind,
                       "rest": False, "up": None, "beams": set()})
    for mark in (g for g in mine if g[0] == "tuplet" and g[1] > 1):
        events.append({"x": mark[2], "members": [mark], "value": None, "rest": False, "up": None, "beams": set(),
                       "tuplet": mark[1]})
    for rest in rests:
        events.append({"x": rest[2], "members": [rest], "value": rest[1], "rest": True,
                       "up": rest[3] > (staff["low"] + staff["high"]) / 2, "beams": set()})
    bars_out = [[] for _ in edges]
    for event in events:
        members = event["members"]
        right = max(m[2] for m in members) + 1.4 * s
        columns_x = sorted({round(d[2] / (0.3 * s)) for d in dots
                            if right - 0.2 * s <= d[2] <= right + 1.6 * s and any(abs(d[3] - m[3]) <= 0.75 * s for m in members)})
        event["dots"] = min(len(columns_x), 2)
        event["middle"] = (staff["low"] + staff["high"]) / 2
        event["space"] = s
        position = next((k for k, edge in enumerate(edges) if event["x"] < edge), None)
        if position is not None:
            bars_out[position].append(event)
    return bars_out


def symbols(bar):
    return collections.Counter((event["rest"], event["value"], event["dots"]) for event in bar if "tuplet" not in event)


def align(read, truth):
    rows, cols = len(read), len(truth)
    cost = [[0.0] * (cols + 1) for _ in range(rows + 1)]
    for r in range(1, rows + 1):
        cost[r][0] = r
    for t in range(1, cols + 1):
        cost[0][t] = t
    for r in range(1, rows + 1):
        for t in range(1, cols + 1):
            same = 0 if read[r - 1] == truth[t - 1] else 0.9
            cost[r][t] = min(cost[r - 1][t - 1] + same, cost[r - 1][t] + 1, cost[r][t - 1] + 1)
    pairs, r, t = [], rows, cols
    while r and t:
        same = 0 if read[r - 1] == truth[t - 1] else 0.9
        if cost[r][t] == cost[r - 1][t - 1] + same:
            pairs.append((r - 1, t - 1))
            r, t = r - 1, t - 1
        elif cost[r][t] == cost[r - 1][t] + 1:
            r -= 1
        else:
            t -= 1
    return pairs


def beam_y(beam, x):
    x0, x1, y0, y1, _ = beam
    return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def main():
    manifest = json.loads((BENCH / "manifest.json").read_text())["pieces"]
    totals = collections.Counter()
    reasons = collections.Counter()
    per_pdf = []
    for pdf in sorted((BENCH / "pdfs").glob("*--*.pdf")):
        piece, engraver = pdf.stem.rsplit("--", 1)
        if engraver not in ("ms", "ly"):
            continue
        truth = truth_bars(BENCH / manifest[piece]["truth"])
        rows = read_pdf(pdf)
        n = len(truth)
        if n == 0 or len(rows) % n:
            per_pdf.append((pdf.stem, "staves", len(rows), n))
            totals[(engraver, "unaligned")] += 1
            continue
        systems = [rows[k:k + n] for k in range(0, len(rows), n)]
        read = [[symbols(bar) for system in systems for bar in system[i]] for i in range(n)]
        matched = total = 0
        for i in range(n):
            pairs = align(read[i], truth[i])
            total += len(truth[i])
            paired = {t: r for r, t in pairs}
            for t, want in enumerate(truth[i]):
                got = read[i][paired[t]] if t in paired else collections.Counter()
                if got == want:
                    matched += 1
                else:
                    for key, count in (want - got).items():
                        reasons[("missing", key)] += count
                    for key, count in (got - want).items():
                        reasons[("extra", key)] += count
        totals[(engraver, "aligned")] += 1
        totals[(engraver, "staff-bars")] += total
        totals[(engraver, "matched")] += matched
        per_pdf.append((pdf.stem, round(matched / total, 3), total))
    for row in per_pdf:
        print(row)
    print(dict(totals))
    for engraver in ("ms", "ly"):
        if totals[(engraver, "staff-bars")]:
            print(engraver, "matched share", round(totals[(engraver, "matched")] / totals[(engraver, "staff-bars")], 4))
    all_bars = totals[("ms", "staff-bars")] + totals[("ly", "staff-bars")]
    if all_bars:
        print("all", round((totals[("ms", "matched")] + totals[("ly", "matched")]) / all_bars, 4), "of", all_bars)
    print("top mismatch reasons:")
    for key, count in reasons.most_common(15):
        print(" ", count, key)


if __name__ == "__main__":
    main()
