import json, os, sys, collections, glob
from datetime import datetime
p = os.path.realpath(sys.argv[1])
rows = [json.loads(l) for l in open(p, errors="replace") if l.strip()]
def ts(r):
    t = r.get("timestamp")
    return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None
times = [ts(r) for r in rows if ts(r)]
print("minutes", round((max(times) - min(times)).total_seconds() / 60, 1))
seen = {}
tools = collections.Counter(); targets = collections.Counter(); idseen = set()
compact = 0
for r in rows:
    if r.get("type") == "system" and r.get("subtype") == "compact_boundary":
        compact += 1
    if r.get("type") == "assistant":
        m = r.get("message") or {}
        u = m.get("usage") or {}
        seen[m.get("id")] = (u.get("output_tokens") or 0, u.get("input_tokens") or 0, u.get("cache_read_input_tokens") or 0, u.get("cache_creation_input_tokens") or 0)
        c = m.get("content")
        if isinstance(c, list):
            for b in c:
                if b.get("type") == "tool_use" and b.get("id") not in idseen:
                    idseen.add(b.get("id"))
                    tools[b.get("name")] += 1
                    i = b.get("input") or {}
                    f = i.get("file_path") or i.get("command") or i.get("pattern") or i.get("url") or ""
                    targets[os.path.relpath(f, sys.argv[2]) if str(f).startswith("/") else str(f)[:80]] += 1
out, inp, cr, cw = (sum(v[k] for v in seen.values()) for k in range(4))
cost = (inp * 3 + out * 15 + cr * 0.30 + cw * 3.75) / 1e6
print("turns", len(seen), "output", out, "input", inp, "cache read", cr, "cache write", cw, "compactions", compact)
print("est cost at Sonnet $3/$15 (cache read .30, write 3.75, from memory): $%.2f" % cost, "peak context", max(v[1] + v[2] + v[3] for v in seen.values()))
print("tools", dict(tools))
print("targets outside the 5 crops and answers:", [t for t in targets if not (t[:2] in ("00","01","02","03","04") or t.startswith("answers/"))])
print("repeat reads:", {t: n for t, n in targets.items() if n > 1})
for f in sorted(glob.glob(sys.argv[2] + "/answers/*.json")):
    try:
        d = json.load(open(f))
        print(os.path.basename(f), "valid; n", d.get("n"), "staves", list(d.get("staves", {}))[:4], "events", sum(len(v) for v in d.get("staves", {}).values()))
    except Exception as e:
        print(os.path.basename(f), "BAD", e)
