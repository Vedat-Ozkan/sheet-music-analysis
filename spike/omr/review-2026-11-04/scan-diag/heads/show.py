import json, sys, collections, re
rows = json.load(open(sys.argv[1]))
for r in rows:
    if r["stage"] == "removed":
        ex = re.sub(r"#\d+", "", r["excl"])[:90]
        print("R", r["name"][8:26] if r["name"].startswith("olimpic") else r["name"][5:16], r["bar"], r["midi"], r["rule"].split("@")[0].split(".")[1], r["shape"][9:], r["grade"], "p", r["p"], ex, r["frames"][0].split(".")[-1] if r["frames"] else "", r["conf"][:3])
for r in rows:
    if r["kind"] == "extra" and r["stage"] == "extra_head":
        print("E", r["name"][8:26] if r["name"].startswith("olimpic") else r["name"][5:16], r["bar"], r["midi"], r["shape"][9:], r["grade"], "p", r["p"], "x", r["x"], "y", r["y"], "st", r["staff"])
