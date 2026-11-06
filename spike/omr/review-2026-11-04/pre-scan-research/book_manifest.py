import glob,json,pathlib,shutil,sys
from truth_shapes import meta,split
R=pathlib.Path(sys.argv[1]);OUT=pathlib.Path(sys.argv[2]);OUT.mkdir(parents=True,exist_ok=True)
L=pathlib.Path.home()/"data/sheet-music-corpora/lieder/scores"
BOOK=glob.glob("/home/kema/projects/sheet-music-plugin/spike/omr/bench-scan/incoming/*.pdf")[0]
RANGES={1:(6,13),2:(15,26),3:(28,39),4:(41,45),5:(47,55),6:(57,61),7:(63,70),8:(72,79),9:(81,84),10:(86,97),11:(99,107),12:(109,122),13:(124,130)}
man=[]
for k,(a,b) in RANGES.items():
    t=glob.glob(str(L/f"Parratt*/Choral*/{k:02d}_*/lc*.mxl"))[0];i=int(pathlib.Path(t).stem[2:])
    src=R/"parratt1-after-4cpu" if k==1 else R/"book"/f"{k:02d}"
    d=OUT/str(i);d.mkdir(exist_ok=True)
    first=sorted(src.glob("current.musicxml"))+sorted(src.glob("score*.musicxml"))
    if first and not (d/"current.musicxml").exists():shutil.copy(first[0],d/"current.musicxml")
    if (src/"homr.musicxml").exists() and not (d/"homr.musicxml").exists():shutil.copy(src/"homr.musicxml",d/"homr.musicxml")
    man.append(dict(id=i,k=k,pdf=BOOK,pages=[a,b],truth=t,off_split=i not in split["tuning"]))
json.dump(man,open(sys.argv[3],"w"),indent=0)
print(len(man),[ (m["id"],m["off_split"]) for m in man][:3])
