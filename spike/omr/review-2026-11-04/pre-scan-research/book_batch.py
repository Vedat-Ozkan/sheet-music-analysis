import json,os,pathlib,shutil,subprocess,sys,threading,time
from concurrent.futures import ThreadPoolExecutor
sys.dont_write_bytecode=True
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin")
import pikepdf,glob
import homrjoin
from engine import read_pdf as reader
OUT=pathlib.Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True)
BOOK=glob.glob("/home/kema/projects/sheet-music-plugin/spike/omr/bench-scan/incoming/*.pdf")[0]
AUD="/home/kema/projects/sheet-music-plugin/spike/omr/speed/launchers/marks1/bin/Audiveris"
RANGES={1:(6,13),2:(15,26),3:(28,39),4:(41,45),5:(47,55),6:(57,61),7:(63,70),8:(72,79),9:(81,84),10:(86,97),11:(99,107),12:(109,122),13:(124,130)}
slots=["8-11","12-15","16-19"]
lock=threading.Lock()
def one(k):
    with lock:
        cores=slots.pop()
    try:
        d=OUT/f"{k:02d}";d.mkdir(exist_ok=True);pdf=d/"piece.pdf"
        if not pdf.exists():
            src=pikepdf.open(BOOK);dst=pikepdf.Pdf.new()
            for i in range(RANGES[k][0]-1,RANGES[k][1]):dst.pages.append(src.pages[i])
            dst.save(pdf)
        work=d/"aud";work.mkdir(exist_ok=True);t=time.time()
        if not list(work.glob("*.mxl")):
            shutil.copy(pdf,work/"score.pdf")
            env={k2:v for k2,v in os.environ.items() if k2!="FONTCONFIG_FILE"}
            env.setdefault("TESSDATA_PREFIX",str(pathlib.Path(AUD).parent.parent/"tessdata"))
            env.update(HOME=str(work),_JAVA_OPTIONS="-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1")
            with open(work/"log.txt","wb") as f:
                subprocess.run(["taskset","-c",cores,AUD,"-batch",*reader.audiveris_options(0,False),"-export","-output",str(work),str(work/"score.pdf")],stdout=f,stderr=subprocess.STDOUT,env=env)
        ta=time.time()-t
        for m in sorted(work.glob("*.mxl")):
            x=reader.clean(m.read_bytes())
            for fn in (reader.infer_tuplet_rests,reader.infer_triplets):
                try:x=fn(x)
                except Exception:pass
            (d/(m.stem+".musicxml")).write_bytes(x)
        t=time.time()
        rows=homrjoin.read_pages(pdf,d,"4",("taskset","-c",cores))
        info=homrjoin.join(rows,d/"homr.musicxml");homrjoin.plain_join(rows,d/"homr-plain.musicxml")
        json.dump(dict(aud_seconds=round(ta),homr_seconds=round(time.time()-t),pages=rows,join=info),open(d/"facts.json","w"),default=str)
        print(k,"done",flush=True)
    finally:
        with lock:
            slots.append(cores)
with ThreadPoolExecutor(3) as ex:list(ex.map(one,[int(x) for x in sys.argv[2:]]))
print("ALL DONE",flush=True)
