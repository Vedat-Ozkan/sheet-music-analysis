import pickle, collections, sys
rows = pickle.load(open(sys.argv[1], "rb"))
E=[r for r in rows if r["kind"]=="extra" and r["a"] and r["endfound"] and r["b"]]
c=collections.Counter()
for r in E:
    sl = "slurab" if r["slurab"] else ("chordslur" if r["chordslur"] and r["chordslurb"] else ("oneend" if r["chordslur"] or r["chordslurb"] else "none"))
    c[(sl, "consecutive" if r["consecutive"] else "non-consec", r["only"])]+=r["n"]
for k in sorted(c): print(k,c[k])
c=collections.Counter()
for r in rows:
    if r["kind"]=="missing" and r["a"] and r["b"] and not r["aslur"] and not r["bslur"]:
        c[(r["eng"], "x" if r["newsys"] else "c" if r["cross"] else "i")]+=r["n"]
print(sorted(c.items()))
c=collections.Counter()
for r in rows:
    if r["kind"]=="missing" and r["a"] and r["b"]:
        c[("staffdiff",r["staffdiff"])]+=r["n"]; c[("voicediff",r["voicediff"])]+=r["n"]; c[("chord",min(r["chordsize"],3))]+=r["n"]; c[("dup",r["dup"])]+=r["n"]
print(c)
p=collections.Counter()
for r in rows:
    if r["kind"]=="missing" and r["a"] and r["b"] and not r["aslur"] and not r["bslur"]: p[r["set"]+"/"+r["stem"]]+=r["n"]
print(p.most_common(15))
p=collections.Counter()
for r in rows:
    if r["kind"]=="extra" and r["a"] and r["b"]: p[r["set"]+"/"+r["stem"]]+=r["n"]
print(p.most_common(15))
