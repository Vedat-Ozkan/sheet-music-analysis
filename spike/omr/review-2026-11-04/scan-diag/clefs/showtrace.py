import re, sys, collections
from pathlib import Path
R = Path("/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/clefs/runs") / sys.argv[1]
for n in sys.argv[2:]:
    L = (R / n / "trace.txt").read_text(errors="replace").splitlines()
    print("==", n)
    hdr = collections.defaultdict(list)
    for l in L:
        if l.startswith("CLEFH "):
            p = l.split()
            hdr[(p[1], p[2])].append(p)
    for (sh, st), ps in sorted(hdr.items(), key=lambda kv: (int(kv[0][0]), int(kv[0][1]))):
        best = {}
        for p in ps:
            for e in p[9:]:
                s, g = e.split("=")
                g = float(g)
                if "CLEF" in s and g > best.get(s, (0,))[0]:
                    best[s] = (g, p[3], p[4], p[5], p[6], p[7], p[8])
        b = max(ps, key=lambda p: float(p[9].split("=")[1]) if len(p) > 9 else 0)
        print(f" head s{sh} st{st} tries={len(ps)} top={b[9:12]} box={b[3:7]} clefbest=", {k: v[0] for k, v in best.items()})
    for l in L:
        if l.startswith(("CLEFHPICK", "CLEFEXP")) or (l.startswith("CLEFHRECT") and "best={}" in l):
            print(" ", l[:125])
    rem = [l for l in L if l.startswith("CLEFREM")]
    print(" removed", len(rem))
    for l in rem[:int(sys.argv[0] and 12)]:
        print(" ", l[:95], "|", l.split(" ")[-1][:110])
    print(" CLEFS lines", sum(l.startswith("CLEFS") for l in L))
