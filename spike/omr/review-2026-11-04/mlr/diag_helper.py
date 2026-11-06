import json, os, sys, collections
from datetime import datetime
p = os.path.realpath(sys.argv[1])
rows = []
for line in open(p, errors="replace"):
    try:
        rows.append(json.loads(line))
    except Exception:
        rows.append({"type": "BAD"})
print("file", os.path.basename(p), "lines", len(rows), "bytes", os.path.getsize(p), collections.Counter(r.get("type") for r in rows).most_common(8))
def ts(r):
    t = r.get("timestamp")
    return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None
out = []
prev = None
reads = collections.Counter()
for k, r in enumerate(rows):
    t = ts(r)
    gap = (t - prev).total_seconds() if t and prev else 0
    if t:
        prev = t
    m = r.get("message") or {}
    c = m.get("content")
    blocks = c if isinstance(c, list) else ([{"type": "text", "text": c}] if isinstance(c, str) else [])
    desc = []
    for b in blocks:
        ty = b.get("type")
        if ty == "tool_use":
            i = b.get("input") or {}
            name = b.get("name")
            size = len(json.dumps(i))
            target = os.path.basename(str(i.get("file_path", ""))) if isinstance(i, dict) else ""
            if name == "Read":
                reads[target] += 1
            desc.append(f"USE {name} {target} input={size}")
        elif ty == "tool_result":
            cc = b.get("content")
            size = len(json.dumps(cc))
            err = b.get("is_error")
            desc.append(f"RESULT size={size}" + (" ERROR " + json.dumps(cc)[:300] if err else ""))
        elif ty == "thinking":
            desc.append(f"THINK len={len(b.get('thinking') or '')} sig={len(b.get('signature') or '')}")
        elif ty == "text":
            desc.append(f"TEXT len={len(b.get('text') or '')}: {(b.get('text') or '')[:160]!r}")
        elif ty:
            desc.append(ty)
    u = m.get("usage") or {}
    out.append((k, r.get("type"), round(gap), m.get("stop_reason"), u.get("output_tokens"), u.get("input_tokens"), u.get("cache_read_input_tokens"), desc, r.get("isApiErrorMessage"), r.get("error")))
first = next((ts(r) for r in rows if ts(r)), None); last = next((ts(r) for r in reversed(rows) if ts(r)), None)
print("span", first, last)
print("reads per file beyond one:", {k: v for k, v in reads.items() if v > 1})
print("distinct files read:", len(reads))
print("gaps over 60 s:")
for o in out:
    if o[2] > 60:
        print(" ", o[0], o[1], "gap", o[2], "stop", o[3], "out", o[4], str(o[7])[:240])
print("output tokens by turn (assistant), largest 8:", sorted((o[4] or 0, o[0]) for o in out if o[1] == "assistant")[-8:])
print("stop reasons:", collections.Counter(o[3] for o in out if o[1] == "assistant"))
print("all output tokens", sum(o[4] or 0 for o in out if o[1] == "assistant"))
print("API errors:", [(o[0], str(o[9])[:120]) for o in out if o[8] or o[9]][:8])
print("non-Read tool uses and errors:")
for o in out:
    d = [x for x in o[7] if ("USE" in x and "USE Read" not in x) or "ERROR" in x]
    if d:
        print(" ", o[0], o[2], str(d)[:420])
print("last 8 entries:")
for o in out[-8:]:
    print(" ", o[0], o[1], "gap", o[2], "stop", o[3], "out", o[4], str(o[7])[:300])
