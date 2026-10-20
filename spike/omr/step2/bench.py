import json, os, re, subprocess, sys, time, shutil, glob
AUD = os.path.abspath(os.path.join(os.path.dirname(__file__), "../tools/audiveris-deb/x/opt/audiveris/bin/Audiveris"))
pdf, out = sys.argv[1], sys.argv[2]
shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
env = dict(os.environ, JAVA_TOOL_OPTIONS="-Xmx1g")
def run(cmd):
    t = time.time()
    p = subprocess.run(["taskset", "-c", "0,1", "/usr/bin/time", "-v"] + cmd, capture_output=True, text=True, env=env)
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", p.stderr)
    return p.returncode, time.time() - t, int(rss.group(1)) / 1024 if rss else None
rc, s, mb = run([AUD, "-batch", "-export", "-output", out, pdf])
res = {"pdf": os.path.basename(pdf), "rc": rc, "seconds": round(s, 1), "peak_mb": round(mb)}
omr = glob.glob(out + "/**/*.omr", recursive=True)
if rc != 0 and omr:
    rc2, s2, mb2 = run([AUD, "-batch", "-export", "-output", out, omr[0]])
    res.update(rc_reexport=rc2, seconds_reexport=round(s2, 1), peak_mb=round(max(mb, mb2)))
res["mxl"] = [os.path.basename(f) for f in glob.glob(out + "/**/*.mxl", recursive=True)]
print(json.dumps(res))
