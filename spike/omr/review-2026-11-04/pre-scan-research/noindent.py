import os,pathlib,shutil,subprocess,sys
sys.dont_write_bytecode=True
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin")
from engine import read_pdf as reader
AUD="/home/kema/projects/sheet-music-plugin/spike/omr/speed/launchers/marks1/bin/Audiveris"
src,work=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]);work.mkdir(parents=True,exist_ok=True)
shutil.copy(src,work/"score.pdf")
env={k:v for k,v in os.environ.items() if k!="FONTCONFIG_FILE"}
env.setdefault("TESSDATA_PREFIX",str(pathlib.Path(AUD).parent.parent/"tessdata"))
env.update(HOME=str(work),_JAVA_OPTIONS="-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1")
opts=reader.audiveris_options(0,False)+["-option",reader._SWITCH+"indentations=false"]
with open(work/"log.txt","wb") as f:
    subprocess.run([AUD,"-batch",*opts,"-export","-output",str(work),str(work/"score.pdf")],stdout=f,stderr=subprocess.STDOUT,env=env)
for m in sorted(work.glob("*.mxl")):
    x=reader.clean(m.read_bytes())
    for fn in (reader.infer_tuplet_rests,reader.infer_triplets):
        try:x=fn(x)
        except Exception:pass
    (work/(m.stem+".musicxml")).write_bytes(x)
print(work.name,sorted(p.name for p in work.glob("*.mxl")),flush=True)
