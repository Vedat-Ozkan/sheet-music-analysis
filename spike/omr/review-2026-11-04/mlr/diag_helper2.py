import json, os, sys, collections
from datetime import datetime
p = os.path.realpath(sys.argv[1])
rows = [json.loads(l) for l in open(p, errors="replace") if l.strip()]
def ts(r):
    t = r.get("timestamp")
    return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None
start = next(ts(r) for r in rows if ts(r))
# unique assistant messages
seen = {}
for r in rows:
    if r.get("type") == "assistant":
        m = r.get("message") or {}
        mid = m.get("id")
        u = m.get("usage") or {}
        seen[mid] = (ts(r), u.get("output_tokens") or 0, u.get("input_tokens") or 0, u.get("cache_read_input_tokens") or 0, u.get("cache_creation_input_tokens") or 0)
print("assistant messages", len(seen), "output tokens", sum(v[1] for v in seen.values()), "input", sum(v[2] for v in seen.values()), "cache read", sum(v[3] for v in seen.values()), "cache write", sum(v[4] for v in seen.values()))
print("biggest turns (minute, output tokens):", sorted(((round((v[0]-start).total_seconds()/60,1), v[1]) for v in seen.values()), key=lambda x:-x[1])[:6])
print("peak context (input+cache read+write):", max(v[2]+v[3]+v[4] for v in seen.values()))
# first and later reads over time
reads = []
for k, r in enumerate(rows):
    if r.get("type") == "assistant":
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            for b in c:
                if b.get("type") == "tool_use" and b.get("name") == "Read":
                    reads.append((round((ts(r)-start).total_seconds()/60,1), os.path.basename(b["input"].get("file_path",""))))
seen_f = {}
for t, f in reads:
    seen_f.setdefault(f, []).append(t)
pngs = sorted(f for f in seen_f if f.endswith(".png"))
print("first read of 00.png, 23.png at min:", seen_f.get("00.png",[None])[0], seen_f.get("23.png",[None])[0])
print("all read times of 00.png, 13.png, 23.png:", seen_f.get("00.png"), seen_f.get("13.png"), seen_f.get("23.png"))
print("read minute histogram (10 min bins):", sorted(collections.Counter(int(t//10)*10 for t, _ in reads).items()))
for k, r in enumerate(rows):
    if r.get("type") == "system":
        print("system entry", k, "minute", round((ts(r)-start).total_seconds()/60,1) if ts(r) else None, {x: (str(r[x])[:120]) for x in r if x in ("subtype","content","compactMetadata","level")})
    if r.get("isCompactSummary") or r.get("isVisibleInTranscriptOnly"):
        print("compact summary at", k, "minute", round((ts(r)-start).total_seconds()/60,1) if ts(r) else None)
others = collections.Counter()
for r in rows:
    if r.get("type") == "assistant":
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            for b in c:
                if b.get("type") == "tool_use":
                    others[b.get("name")] += 1
print("tool calls (with repeats from logging):", others)
