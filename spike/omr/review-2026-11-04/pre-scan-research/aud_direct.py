import os,pathlib,subprocess,sys,shutil
sys.dont_write_bytecode=True
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin")
from engine import read_pdf as reader
aud="/home/kema/projects/sheet-music-plugin/spike/omr/speed/launchers/marks1/bin/Audiveris"
src,work=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]);work.mkdir(parents=True,exist_ok=True)
shutil.copy(src,work/"score.pdf")
env={k:v for k,v in os.environ.items() if k!="FONTCONFIG_FILE"}
env.setdefault("TESSDATA_PREFIX",str(pathlib.Path(aud).parent.parent/"tessdata"))
env.update(HOME=str(work),_JAVA_OPTIONS="-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1")
opts=reader.audiveris_options(0,False)
cmd=[aud,"-batch",*opts,"-export","-output",str(work),str(work/"score.pdf")]
print(" ".join(cmd)[:300])
with open(work/"log.txt","wb") as f:
    r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env)
print("exit",r.returncode,sorted(p.name for p in work.iterdir()))
