import json, re, subprocess, sys, zipfile, collections
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HOME = Path(__file__).parent
tag = sys.argv[1]; extra = sys.argv[2:]
items = json.loads((HOME / "items" / tag / "items.json").read_text())
def one(it):
    out = HOME / "books" / (tag + ("-" + "x".join(e.split(".")[-1] for e in extra if "=" in e) if extra else "")) / it["name"]
    if not list(out.glob("*.omr")):
        subprocess.run([str(HOME / "book.sh"), str(out), it["pdf"], *extra], timeout=500)
    omr = list(out.glob("*.omr"))
    heads = 0; shapes = collections.Counter(); inter = []
    if omr:
        z = zipfile.ZipFile(omr[0])
        for n in z.namelist():
            if re.search(r"sheet#\d+\.xml$", n):
                s = z.read(n).decode("utf8", "replace")
                heads += len(re.findall(r"<head [^>]*", s))
    return it["name"], heads
with ThreadPoolExecutor(4) as pool:
    res = dict(pool.map(one, items))
(HOME / "results" / f"heads-{tag}{'-x' if extra else ''}.json").write_text(json.dumps(res))
print(sum(res.values()))
