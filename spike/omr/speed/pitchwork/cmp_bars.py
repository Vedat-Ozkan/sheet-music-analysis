import sys, json, collections
sys.path[:0] = ["/home/kema/projects/sheet-music-plugin", "/home/kema/projects/sheet-music-plugin/spike/omr", "/home/kema/projects/sheet-music-plugin/spike/omr/bench"]
from engine_check import load
from engine.read_pdf import clean
from compare import align
from score_one import fill
OMR = "/home/kema/projects/sheet-music-plugin/spike/omr/"
def p(c):
    out = collections.Counter()
    for (x, _), n in c.items():
        out[x] += n
    return out
setname, piece = sys.argv[1], sys.argv[2]
m = json.load(open(OMR + setname + "/manifest.json"))["pieces"]
t, _, _ = load(open(OMR + setname + "/" + m[piece.rsplit("--", 1)[0]]["truth"], "rb").read())
for f in sys.argv[3:]:
    data = open(f, "rb").read()
    o, _, _ = load(clean(data) if f.endswith(".mxl") else data)
    pairs = dict(fill(align([(b,) for b in t], [(b,) for b in o])[0], len(t), len(o)))
    bad = [i + 1 for i in range(len(t)) if pairs.get(i) is None or p(t[i]) != p(o[pairs[i]])]
    print(f.split("/")[-2] if f.endswith(".mxl") else f.split("/")[-1], "pitch-wrong bars", len(bad), bad)
