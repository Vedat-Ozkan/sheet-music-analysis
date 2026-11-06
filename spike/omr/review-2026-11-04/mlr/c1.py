import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from tie_book import *
setname, stem, bars, out = sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3].split(",")], sys.argv[4]
s = choose_setting(setname, stem)
z, st = load_book(S / "mlr/tb" / stem / s)
ob = parse((HERE / "cache/runs/pitch51" / f"{setname}--{stem}.musicxml").read_bytes())
print(stem, s, "stacks", len(st), "bars", len(ob))
crop(z, st, bars, out, overlay=True)
print({k: st[bars[0]][k] for k in ("sheet", "sys", "left", "right", "il")}, sum(1 for i in st[bars[0]]["inters"].values() if i["tag"] == "slur"))
