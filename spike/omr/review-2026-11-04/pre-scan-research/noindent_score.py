import glob,pathlib,sys
from lib import *
import merge3 as M3
from scoreone import score
R=pathlib.Path(sys.argv[1])
for k in ("01","05","06","08"):
    f=R/"noindent"/k/"score.musicxml"
    if not f.exists():continue
    tf=glob.glob(str(pathlib.Path.home()/f"data/sheet-music-corpora/lieder/scores/Parratt*/Choral*/{k}_*/lc*.mxl"))[0];td=open(tf,"rb").read()
    print("piece",k)
    score(td,"one movement, current",f.read_bytes())
    h=(R/"parratt1-after-4cpu" if k=="01" else R/"book"/k)/"homr.musicxml"
    d,info=M3.merge(f,h);score(td,"merged: "+info["reason"][:12],d)
