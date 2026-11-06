import argparse,collections,copy,json,os,pathlib,subprocess,sys,threading,time,xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
A=argparse.ArgumentParser();A.add_argument("pdf");A.add_argument("--out");A.add_argument("--truth");A.add_argument("--threads",default="4");A.add_argument("--homr",default="after",choices=["after","parallel","skip"]);A.add_argument("--audiveris",default="/home/kema/projects/sheet-music-plugin/spike/omr/speed/launchers/marks1/bin/Audiveris");A.add_argument("--server-import",action="store_true");A.add_argument("--render",action="store_true");A.add_argument("--reuse-current",default=None)
a=A.parse_args()
ROOT=pathlib.Path("/home/kema/projects/sheet-music-plugin");OMRD=ROOT/"spike/omr";HERE=pathlib.Path(__file__).parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE))
out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
phases=[]
def mark(name):
    phases.append((name,round(time.time(),2)));print(name,time.strftime("%H:%M:%S"),flush=True)
mark("start")
if a.server_import:
    import server.app
from engine import read_pdf as reader
mark("imported")
data=pathlib.Path(a.pdf).read_bytes()
def homr_pages():
    d=out/"homr";d.mkdir(exist_ok=True)
    subprocess.run([str(OMRD/"homr-venv/bin/python"),str(OMRD/"rasterize.py"),a.pdf,str(d),"300"],check=True)
    env={"OMP_NUM_THREADS":a.threads,"PATH":"/usr/bin:/bin","HOME":str(pathlib.Path.home())}
    trees=[];times=[];pages=[]
    for png in sorted(d.glob("*-p*.png"),key=lambda p:int(p.stem.rsplit("-p",1)[1])):
        xml=png.with_suffix(".musicxml");t=time.time()
        if not xml.exists():
            subprocess.run([str(OMRD/"homr-venv/bin/python"),str(OMRD/"review-2026-11-04/scan-two-readers/scripts/homr_safe.py"),str(png)],capture_output=True,text=True,env=env)
        times.append(round(time.time()-t,1))
        if xml.exists():
            tr=ET.parse(xml);trees.append(tr)
            pages.append([len({n.findtext("staff","1") for n in p.iter("note")}) for p in tr.getroot().findall("part")])
        else:pages.append(None)
    if trees:
        parts=trees[0].getroot().findall("part")
        for t in trees[1:]:
            for x,y in zip(parts,t.getroot().findall("part")):
                for ms in y.findall("measure"):x.append(copy.deepcopy(ms))
        for p in parts:
            for i,ms in enumerate(p.findall("measure"),1):ms.set("number",str(i))
        trees[0].write(out/"homr.musicxml",encoding="utf-8",xml_declaration=True)
    json.dump({"seconds_per_page":times,"page_shapes":pages},open(out/"homr_times.json","w"))
th=None
if a.homr=="parallel":
    th=threading.Thread(target=homr_pages);mark("homr_start_parallel");th.start()
facts={}
if a.reuse_current is None:
    mark("read_pdf")
    t=time.time();r=reader.read_pdf(data,audiveris=a.audiveris)
    facts=dict(seconds=round(time.time()-t,1),pages=r.pages,scan=r.scan,skipped=r.skipped,passes=[{k:p.get(k) for k in("setting","outcome","seconds")} for p in r.passes])
    (out/"current.musicxml").write_bytes(r.musicxml)
    mark("read_pdf_done")
if a.homr=="after":
    mark("homr");homr_pages();mark("homr_done")
elif a.homr=="parallel":
    th.join();mark("homr_done")
if a.render and (out/"homr.musicxml").exists():
    import merge3
    mark("merge_render")
    src=pathlib.Path(a.reuse_current) if a.reuse_current else out/"current.musicxml"
    d,info=merge3.merge(src,out/"homr.musicxml")
    (out/"merged3.musicxml").write_bytes(d)
    spots=reader.problem_spots(d)
    tall=reader.preview(d,tall=True,spots=spots);shaded=reader.preview(d,spots=spots)
    png=tall.png(1,width=1400,colors=256)
    facts["merge"]={k:str(v) for k,v in info.items()};mark("render_done")
json.dump({"facts":facts,"phases":phases},open(out/"run.json","w"),indent=1)
print(json.dumps(facts)[:600],flush=True)
