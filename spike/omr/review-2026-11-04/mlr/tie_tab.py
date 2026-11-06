import pickle, collections, sys
rows = pickle.load(open(sys.argv[1], "rb"))
def label_m(r):
    if not r["a"]: return "M0 start note not in reading"
    if not r["endfound"]: return "M1 truth has no end note (dangling)"
    if not r["b"]: return "M2 end note not in reading" + (" (cross-bar)" if r["cross"] else "")
    x = "cross-system" if r["newsys"] else ("cross-bar" if r["cross"] else "in-bar")
    if r["slurab"]: return f"M3 reading has slur on same two heads [{x}]"
    if r["aslur"] and r["bslur"]: return f"M4 both heads have different slurs [{x}]"
    if r["aslur"]: return f"M5 slur start on left head only [{x}]"
    if r["bslur"]: return f"M6 slur stop on right head only [{x}]"
    return f"M7 no slur on either head [{x}]"
def label_e(r):
    if not r["a"]: return "E0 start note not in truth"
    if not r["endfound"]: return "E1 reading tie with no end"
    if not r["b"]: return "E2 end note not in truth"
    x = "cross-system" if r["newsys"] else ("cross-bar" if r["cross"] else "in-bar")
    if r["slurab"]: return f"E3 truth has slur on same two heads [{x}]"
    if r["chordslur"] and r["chordslurb"]: return f"E4 truth slur on both chords, other notes [{x}]"
    if r["chordslur"] or r["chordslurb"]: return f"E5 truth slur at one end only [{x}]"
    return f"E6 no truth slur at either end [{x}]"
for kind, lab in (("missing", label_m), ("extra", label_e)):
    c, co = collections.Counter(), collections.Counter()
    for r in rows:
        if r["kind"] == kind:
            c[lab(r)] += r["n"]
            if r["only"]: co[lab(r)] += r["n"]
    print(kind, sum(c.values()), "in only-ties bars", sum(co.values()))
    for k in sorted(c): print(f"  {k:60} all {c[k]:5}  only {co[k]:5}")
e = collections.Counter()
for r in rows:
    e[(r["set"], r["kind"], r["only"])] += r["n"]
for k in sorted(e): print(k, e[k])
eng = collections.Counter()
for r in rows:
    eng[(r["eng"], r["kind"])] += r["n"]
print(sorted(eng.items()))
