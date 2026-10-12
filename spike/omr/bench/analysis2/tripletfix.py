"""Prototype post-fix (not engine code): in a voice whose bar is longer than the time signature, mark beamed groups of three
equal notes as triplets (3:2) when exactly one set of such groups removes the overflow. Operates on an ElementTree root in place."""
import itertools
from fractions import Fraction
import xml.etree.ElementTree as ET

STATS = {"bars_fixed": 0, "groups_marked": 0, "bars_ambiguous": 0, "bars_overflow_no_solution": 0, "bars_overflow": 0}

def _events(measure):
    """voice -> list of events; event = list of note elements (first is non-chord). Grace notes skipped."""
    voices = {}; cur = None
    for n in measure.findall("note"):
        if n.find("grace") is not None: continue
        key = (n.findtext("staff"), n.findtext("voice"))
        if n.find("chord") is not None and cur is not None and cur[0] == key: cur[1].append(n); continue
        cur = (key, [n]); voices.setdefault(key, []).append(cur[1])
    return voices

def _beam(ev):
    b = ev[0].find("beam")
    return b.text if b is not None else None

def _plain(ev, typ):
    n = ev[0]
    return n.find("time-modification") is None and not n.findall("dot") and n.findtext("type") == typ

def _candidates(evs):
    """first-event indexes of triples. A run of consecutive plain events of one short type (no dot, no tuplet) whose length is a
    multiple of 3 is cut into triples from its start; a triple is accepted when its notes are beamed and it does not straddle
    two beam groups (no beam end before its last note, no beam begin after its first)."""
    out = []; i = 0
    while i < len(evs):
        typ = evs[i][0].findtext("type")
        if typ not in ("eighth", "16th", "32nd") or not _plain(evs[i], typ): i += 1; continue
        j = i
        while j < len(evs) and _plain(evs[j], typ):
            j += 1
            if _beam(evs[j - 1]) in ("end", None) and evs[j - 1][0].find("rest") is None: break  # a beam group ends here
        if (j - i) % 3 == 0:
            for s in range(i, j, 3):
                w = evs[s:s + 3]; notes = [(k, _beam(e)) for k, e in enumerate(w) if e[0].find("rest") is None]
                if len(notes) >= 2 and all(bm is not None for _, bm in notes) and \
                   all(bm != "end" for k, bm in notes if k < 2) and all(bm != "begin" for k, bm in notes if k > 0) and \
                   all(bm in ("begin", "continue", "end") for _, bm in notes):
                    out.append(s)
        i = j
    return out

def _backup_targets(m):
    """(backup element, onset it goes back to) in the bar as printed now; chords and grace notes do not advance time."""
    cur = 0; out = []
    for el in m:
        if el.tag == "note":
            if el.find("grace") is None and el.find("chord") is None: cur += int(float(el.findtext("duration") or 0))
        elif el.tag == "forward": cur += int(float(el.findtext("duration")))
        elif el.tag == "backup":
            d = int(float(el.findtext("duration"))); out.append((el, cur - d)); cur -= d
    return out

def _retarget(m, targets):
    """after the notes got shorter, point each backup at the same onset as before (durations already scaled by 3)."""
    cur = 0; t = {id(e): v * 3 for e, v in targets}
    for el in m:
        if el.tag == "note":
            if el.find("grace") is None and el.find("chord") is None: cur += int(el.findtext("duration"))
        elif el.tag == "forward": cur += int(el.findtext("duration"))
        elif el.tag == "backup":
            d = cur - t[id(el)]; el.find("duration").text = str(d); cur -= d

def fix(root):
    for part in root.iter("part"):
        ts = None; div = 1; todo = []
        ms = part.findall("measure")
        has_tm = [m.find(".//time-modification") is not None for m in ms]
        for mi, m in enumerate(ms):
            a = m.find("attributes")
            if a is not None:
                if a.find("divisions") is not None: div = int(float(a.findtext("divisions")))
                t = a.find("time")
                if t is not None and t.find("beats") is not None:
                    try: ts = Fraction(int(t.findtext("beats")), int(t.findtext("beat-type")))
                    except ValueError: ts = None
            if ts is not None and ts.denominator == 8 and ts.numerator % 3 == 0 and ts.numerator >= 6: continue  # 6/8, 9/8, 12/8: groups of three eighths are normal there
            if ts is None or m.get("implicit") == "yes" or m.get("number") in ("0",): continue
            if not any(has_tm[max(0, mi - 3):mi + 4]): continue  # no triplet printed nearby: the overflow has another cause
            for key, evs in _events(m).items():
                total = sum(Fraction(int(float(e[0].findtext("duration") or 0)), div) for e in evs)
                over = total - ts * 4
                if over <= 0: continue
                STATS["bars_overflow"] += 1
                cand = _candidates(evs)
                ds = [Fraction(int(float(evs[i][0].findtext("duration"))), div) for i in cand]
                sols = [c for r in range(1, len(cand) + 1) for c in itertools.combinations(range(len(cand)), r) if sum(ds[k] for k in c) == over] if len(cand) <= 14 else []
                if len(sols) == 1:
                    todo.append((m, [evs[cand[k]:cand[k] + 3] for k in sols[0]], _backup_targets(m)))
                    STATS["bars_fixed"] += 1
                else:
                    STATS["bars_ambiguous" if sols else "bars_overflow_no_solution"] += 1
        if not todo: continue
        # scale the whole part by 3 so the new durations stay whole numbers
        for e in part.iter():
            if e.tag in ("divisions", "duration") and e.text: e.text = str(int(float(e.text)) * 3)
        for m, groups, targets in todo:
            for g in groups:
                for ev in g:
                    for n in ev:
                        d = n.find("duration"); d.text = str(int(d.text) * 2 // 3)
                        tm = ET.Element("time-modification"); ET.SubElement(tm, "actual-notes").text = "3"; ET.SubElement(tm, "normal-notes").text = "2"
                        # schema order: after type/dot/accidental, before stem
                        idx = next((k for k, c in enumerate(list(n)) if c.tag in ("stem", "notehead", "staff", "beam", "notations")), len(n))
                        n.insert(idx, tm)
                STATS["groups_marked"] += 1
            _retarget(m, targets)
