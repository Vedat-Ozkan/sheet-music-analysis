import collections
import json
import statistics
import sys

rows = json.load(open(sys.argv[1]))
TOL = sys.argv[2] if len(sys.argv) > 2 else "tol1"
GRADES = (0.0, 0.1, 0.3, 0.5)
DESIGN = {"rest_missing", "dot", "type", "grace_as_real", "note_extra", "tuplet"}


def group(bucket):
    if bucket.startswith("combo"):
        return "multi-cause"
    if bucket.startswith("voice"):
        return "voice-only"
    base = bucket.replace(" (+voice/offset)", "")
    return base if base in ("rest_missing", "dot", "type", "grace_as_real", "note_missing", "note_extra") else "other"


def covered(row, g, loose):
    if not row["needed"] or not row["items"]:
        return False
    for item in row["items"]:
        if item["need"] == "no_ink":
            continue
        if item["need"] != "ink" or (not loose and item["cause"] not in DESIGN):
            return False
        hit = item.get(TOL)
        if not hit or hit["grade"] < g:
            return False
    return True


def any_ink(row):
    return any(item["need"] == "ink" for item in row["items"])


rows = [r for r in rows if not r["truth_flagged"]]
order = ["rest_missing", "dot", "type", "grace_as_real", "note_missing", "note_extra", "multi-cause", "voice-only", "other"]
by = collections.defaultdict(list)
for r in rows:
    by[group(r["bucket"])].append(r)
print(f"{len(rows)} flagged bars (truth not flagged), {len({r['pdf'] for r in rows})} PDFs, x tolerance {TOL}")
print(f"{'bucket':14}{'bars':>5}{'no-ink':>7}" + "".join(f"{'ev>=' + str(g):>9}" for g in GRADES) + f"{'items':>7}{'w/ ev':>7}{'median':>8}{'>0.3':>6}{'>0.5':>6}{'oth.set':>8}")
for b in order:
    sel = by.get(b, [])
    if not sel:
        continue
    noink = sum(1 for r in sel if r["items"] and not any_ink(r) and covered(r, 0, True))
    cov = [sum(covered(r, g, False) for r in sel) for g in GRADES]
    its = [i for r in sel for i in r["items"] if i["need"] == "ink"]
    hits = [i[TOL]["grade"] for i in its if i.get(TOL)]
    other = sum(1 for i in its if not i.get(TOL) and i.get("other_setting"))
    med = f"{statistics.median(hits):.2f}" if hits else "-"
    print(f"{b:14}{len(sel):5}{noink:7}" + "".join(f"{c:9}" for c in cov) +
          f"{len(its):7}{len(hits):7}{med:>8}{sum(h > 0.3 for h in hits):6}{sum(h > 0.5 for h in hits):6}{other:8}")

core = [r for r in rows if group(r["bucket"]) in ("rest_missing", "dot", "type")]
print("\nabandon rule (rest/dot/type bars, every needed edit backed; no-ink edits count as backed):")
for g in GRADES:
    n = sum(covered(r, g, False) for r in core)
    print(f"  grade >= {g}: {n}/{len(core)} = {n / max(1, len(core)):.0%}")

voice = len(by.get("voice-only", []))
print("\nceiling = voice-only bars + bars whose every needed edit is backed:")
for g in GRADES:
    strict = sum(covered(r, g, False) for r in rows)
    loose = sum(covered(r, g, True) for r in rows)
    tup = sum(covered(r, g, False) for r in rows if group(r["bucket"]) == "other")
    print(f"  grade >= {g}: strict {voice + strict} (design edits only; {tup} of them tuplet-only bars), loose {voice + loose} (head alt also fixes note_missing)")

print("\ncontrol: same probe at correctly read notes in the same flagged bars (hit rate)")
ctl = collections.defaultdict(list)
for r in rows:
    for c in r.get("control", []):
        ctl[c["sub"]].append(c.get(TOL))
need = collections.defaultdict(list)
for r in rows:
    for i in r["items"]:
        if i["need"] == "ink":
            need[i["sub"] if i["sub"] in ctl else ("flag_up" if i["sub"] == "flag_up" else i["sub"])].append(i.get(TOL))
for sub in sorted(set(ctl) | set(need)):
    def rate(xs, g):
        return f"{sum(1 for x in xs if x and x['grade'] >= g) / len(xs):.0%}" if xs else "-"
    print(f"  {sub:16} needed n={len(need[sub]):4} " + " ".join(f">={g}:{rate(need[sub], g):>4}" for g in GRADES) +
          f" | control n={len(ctl[sub]):5} " + " ".join(f">={g}:{rate(ctl[sub], g):>4}" for g in GRADES))

print("\nwhere evidence comes from (needed items, best hit):", dict(collections.Counter(i[TOL]["loss"] for r in rows for i in r["items"] if i.get(TOL))))
print("other buckets:", dict(collections.Counter(r["bucket"] for r in by.get("other", []))))
