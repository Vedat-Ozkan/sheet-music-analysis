import glob, json, os, sys, time
T, A = sys.argv[1], sys.argv[2]
def cost():
    try:
        seen = {}
        for line in open(os.path.realpath(T), errors="replace"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("type") == "assistant":
                m = r.get("message") or {}
                u = m.get("usage") or {}
                seen[m.get("id")] = (u.get("output_tokens") or 0, u.get("input_tokens") or 0, u.get("cache_read_input_tokens") or 0, u.get("cache_creation_input_tokens") or 0)
        o, i, r_, w = (sum(v[k] for v in seen.values()) for k in range(4))
        return (i * 3 + o * 15 + r_ * 0.30 + w * 3.75) / 1e6, o
    except OSError:
        return 0.0, 0
start = time.time(); last = start; have = 0
while True:
    n = len([f for f in glob.glob(A + "/*.json") if os.path.basename(f)[:2] >= "05"])
    c, o = cost()
    now = time.time()
    if n > have:
        have, last = n, now
    if n >= 19:
        print(f"DONE: {n} files, {round(now-start)} s, est ${c:.2f}, output tokens {o}"); break
    if c > 3.3:
        print(f"OVER BUDGET: {n} files, {round(now-start)} s, est ${c:.2f}, output tokens {o}"); break
    if now - last > 600:
        print(f"STALLED: {n} files, no new file for 10 minutes, est ${c:.2f}"); break
    time.sleep(10)
