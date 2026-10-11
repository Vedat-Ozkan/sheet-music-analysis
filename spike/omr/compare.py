"""Compare OMR MusicXML with ground-truth MusicXML.

usage: compare.py truth.mxl omr1.(mxl|musicxml) [omr2 ...]   (several files = pages of one piece, joined in order)

Method: every pitched note (chord notes counted separately, grace notes included, ties not merged) becomes a MIDI
number with a duration in quarter notes; all parts and staves of a measure are pooled. Bars are aligned by dynamic
programming over the two bar sequences, maximising shared pitches, skipped bars allowed ("aligned"); the "ordinal"
figure pairs bar k with bar k instead.
  pitch      = shared pitches (multiset overlap per bar) / truth notes
  rhythm     = among the shared pitches, the share whose duration is also the same (per bar, per pitch, multiset)
  key, meter = share of aligned bars whose key signature (fifths) / time signature equals the truth's in that bar;
               the state in force carries over from earlier bars and pages. Also first key / first meter.
Prints one JSON line.
"""
import sys, json, zipfile, collections
from fractions import Fraction
import xml.etree.ElementTree as ET

STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

def read(path):
    if path.endswith(".mxl"):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            return z.read(name)
    return open(path, "rb").read()

def bars(path, state):
    """-> list of (notes Counter{(midi, dur): n}, key, meter); state carries key/meter across files."""
    root = ET.fromstring(read(path))
    parts = [list(p.iter("measure")) for p in root.iter("part")]
    out = []
    for k in range(max((len(p) for p in parts), default=0)):
        c = collections.Counter()
        for pi, p in enumerate(parts):
            if k >= len(p): continue
            div = 1
            for el in p[k].iter():
                if el.tag == "divisions": div = int(float(el.text))
                elif el.tag == "key" and pi == 0 and el.findtext("fifths") is not None: state["key"] = int(el.findtext("fifths"))
                elif el.tag == "time" and pi == 0 and el.findtext("beats"): state["meter"] = f"{el.findtext('beats')}/{el.findtext('beat-type')}"
            # divisions can be declared in an earlier measure: remember per part
            state.setdefault("div", {})
            if p[k].find("attributes/divisions") is not None: state["div"][pi] = div
            div = state["div"].get(pi, div)
            for note in p[k].iter("note"):
                pitch = note.find("pitch")
                if pitch is None: continue
                m = (int(pitch.findtext("octave")) + 1) * 12 + STEP[pitch.findtext("step")] + int(round(float(pitch.findtext("alter") or 0)))
                d = note.findtext("duration")
                dur = Fraction(int(float(d)), div) if d is not None and note.find("grace") is None else Fraction(0)
                c[(m, dur)] += 1
        out.append((c, state.get("key", 0), state.get("meter")))  # no <key> element = C major, as Audiveris writes it
    return out

def pitches(c):
    r = collections.Counter()
    for (m, _), n in c.items(): r[m] += n
    return r

def shared(a, b): return sum((pitches(a) & pitches(b)).values())

def rhythm_match(a, b):
    """notes with equal pitch and equal duration, counted per pitch."""
    total = 0
    for m in set(pitches(a)) & set(pitches(b)):
        da = collections.Counter({d: n for (mm, d), n in a.items() if mm == m})
        db = collections.Counter({d: n for (mm, d), n in b.items() if mm == m})
        total += sum((da & db).values())
    return total

def align(t, o):
    n, m = len(t), len(o)
    S = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            S[i][j] = max(S[i-1][j], S[i][j-1], S[i-1][j-1] + shared(t[i-1][0], o[j-1][0]))
    i, j, pairs = n, m, []
    while i > 0 and j > 0:
        if S[i][j] == S[i-1][j-1] + shared(t[i-1][0], o[j-1][0]) and shared(t[i-1][0], o[j-1][0]) > 0 or (S[i][j] == S[i-1][j-1] and S[i][j] != S[i-1][j] and S[i][j] != S[i][j-1]):
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif S[i][j] == S[i-1][j]: i -= 1
        else: j -= 1
    return pairs[::-1], S[n][m]

if __name__ == "__main__":
    ts = {}; truth = bars(sys.argv[1], ts); os_ = {}; omr = []
    for f in sys.argv[2:]: omr += bars(f, os_)
    tn, on = (sum(sum(b[0].values()) for b in x) for x in (truth, omr))
    ordinal = sum(shared(truth[k][0], omr[k][0]) for k in range(min(len(truth), len(omr))))
    pairs, al = align([(b[0],) for b in truth], [(b[0],) for b in omr])
    rh = sum(rhythm_match(truth[i][0], omr[j][0]) for i, j in pairs)
    key = sum(truth[i][1] == omr[j][1] for i, j in pairs) / max(len(pairs), 1)
    met = sum(truth[i][2] == omr[j][2] for i, j in pairs) / max(len(pairs), 1)
    print(json.dumps({"truth_bars": len(truth), "omr_bars": len(omr), "truth_notes": tn, "omr_notes": on,
                      "pitch_ordinal": round(ordinal / tn, 3), "pitch_aligned": round(al / tn, 3),
                      "rhythm_of_matched": round(rh / al, 3) if al else 0,
                      "key_bars_ok": round(key, 3), "meter_bars_ok": round(met, 3), "aligned_bars": len(pairs),
                      "first_key": [truth[0][1], omr[0][1]] if omr else None, "first_meter": [truth[0][2], omr[0][2]] if omr else None}))
