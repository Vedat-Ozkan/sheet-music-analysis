import sys
sys.argv = ["x", "base"]
src = open("ivscore.py").read().split("base = run(sys.argv[1])")[0]
exec(src)
base = run("base"); v = run("gapoff")
for n, ids in bucket.items():
    if n not in truth or not ids: continue
    print(n.replace("olimpic-", "")[:24], [(i, base[n][1][i][0], v[n][1][i][0], base[n][1][i][1], v[n][1][i][1], base[n][1][i][2]) for i in sorted(ids) if i in base[n][1] and i in v[n][1]])
for n in truth:
    if not base[n][1] or not v[n][1]: continue
    g = [i for i in base[n][1] if v[n][1].get(i, (False,))[0] and not base[n][1][i][0]]; l = [i for i in base[n][1] if base[n][1][i][0] and not v[n][1].get(i, (False,))[0]]
    if g or l: print("all-bars", n[:24], "gain", g, "lost", l)
