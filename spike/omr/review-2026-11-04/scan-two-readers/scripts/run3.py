import copy,hashlib,json,pathlib,subprocess,sys,xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
OMR=pathlib.Path("/home/kema/projects/sheet-music-plugin/spike/omr");S=pathlib.Path(__file__).parent
kind,tag,jobs=sys.argv[1],sys.argv[2],int(sys.argv[3])
items=[]
if kind=="unseen":
    m=json.loads((OMR/"bench-olimpic/manifest.json").read_text());u=set(json.loads((OMR/"bench-olimpic/split.json").read_text())["unseen"])
    items=[("bench-olimpic",OMR/"bench-olimpic"/p["pdf"]) for p in m["pdfs"] if p["piece"] in u]
else:
    for s in ["bench","bench-heldout","bench-heldout2","bench-heldout3","bench-tune2","bench-oldly"]:
        m=json.loads((OMR/s/"manifest.json").read_text())
        for e in m["pdfs"]:
            st=e["pdf"].rsplit("/",1)[-1][:-4]
            if "scan" not in st and (OMR/"speed/cache/runs/marks1"/f"{s}--{st}.musicxml").exists():items.append((s,OMR/s/e["pdf"]))
    items=sorted(items,key=lambda i:hashlib.sha256(i[1].stem.encode()).hexdigest())[:60]
(S/f"{tag}.items.json").write_text(json.dumps([[s,p.stem] for s,p in items]))
runs=OMR/"speed/cache/runs"/tag;runs.mkdir(parents=True,exist_ok=True);work=S/f"work-{tag}"
env={"OMP_NUM_THREADS":"4","PATH":"/usr/bin:/bin","HOME":str(pathlib.Path.home())}
def one(it):
    name,pdf=it;d=work/name/pdf.stem;out=runs/f"{name}--{pdf.stem}.musicxml"
    if out.exists():return
    d.mkdir(parents=True,exist_ok=True)
    subprocess.run([str(OMR/"homr-venv/bin/python"),str(OMR/"rasterize.py"),str(pdf),str(d),"300"],check=True)
    trees=[]
    for png in sorted(d.glob("*-p*.png"),key=lambda p:int(p.stem.rsplit("-p",1)[1])):
        xml=png.with_suffix(".musicxml")
        r=subprocess.run([str(OMR/"homr-venv/bin/python"),str(S/"homr_safe.py"),str(png)],capture_output=True,text=True,env=env)
        if not xml.exists():print("FAILED",name,pdf.stem,png.name,flush=True);continue
        trees.append(ET.parse(xml))
    if not trees:return
    parts=trees[0].getroot().findall("part")
    for t in trees[1:]:
        for a,b in zip(parts,t.getroot().findall("part")):
            for ms in b.findall("measure"):a.append(copy.deepcopy(ms))
    for p in parts:
        for i,ms in enumerate(p.findall("measure"),1):ms.set("number",str(i))
    trees[0].write(out,encoding="utf-8",xml_declaration=True)
with ThreadPoolExecutor(jobs) as ex:list(ex.map(one,items))
print("done",tag,len(items),len(list(runs.glob("*.musicxml"))),flush=True)
