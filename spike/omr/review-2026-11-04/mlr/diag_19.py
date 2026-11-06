import json, os, sys, collections
from datetime import datetime
p = os.path.realpath(sys.argv[1]); base = sys.argv[2]
rows = [json.loads(l) for l in open(p, errors="replace") if l.strip()]
times = [datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) for r in rows if r.get("timestamp")]
seen = {}; ids = set(); tools = collections.Counter(); targets = collections.Counter(); comp = 0
for r in rows:
    if r.get("type") == "system" and r.get("subtype") == "compact_boundary":
        comp += 1
    if r.get("type") == "assistant":
        m = r.get("message") or {}; u = m.get("usage") or {}
        seen[m.get("id")] = (u.get("output_tokens") or 0, u.get("input_tokens") or 0, u.get("cache_read_input_tokens") or 0, u.get("cache_creation_input_tokens") or 0)
        c = m.get("content")
        if isinstance(c, list):
            for b in c:
                if b.get("type") == "tool_use" and b.get("id") not in ids:
                    ids.add(b.get("id")); tools[b.get("name")] += 1
                    i = b.get("input") or {}
                    f = i.get("file_path") or i.get("command") or i.get("pattern") or i.get("url") or ""
                    targets[os.path.relpath(f, base) if str(f).startswith("/") else str(f)[:80]] += 1
o, i, cr, cw = (sum(v[k] for v in seen.values()) for k in range(4))
print("minutes", round((max(times) - min(times)).total_seconds() / 60, 1), "turns", len(seen), "output", o, "cache read", cr, "cache write", cw, "compactions", comp)
print("est cost $%.2f" % ((i * 3 + o * 15 + cr * 0.30 + cw * 3.75) / 1e6), "tools", dict(tools))
print("opened outside crops/answers:", [t for t in targets if t and not re.match(r"^(\d\d\.(png|txt)|answers/\d\d\.json)$", t)] if False else [t for t in targets if t and not (t[:2].isdigit() or t.startswith("answers/"))], "repeat reads", {t: n for t, n in targets.items() if n > 1 and t})
