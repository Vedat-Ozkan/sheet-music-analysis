import collections,copy,json,pathlib,subprocess,sys,time,xml.etree.ElementTree as ET
OMRD=pathlib.Path("/home/kema/projects/sheet-music-plugin/spike/omr")
SAFE=OMRD/"review-2026-11-04/scan-two-readers/scripts/homr_safe.py"
def page_shape(root):
    out=[]
    for p in root.findall("part"):
        ns=0
        for at in p.iter("staves"):ns=max(ns,int(at.text))
        st={n.findtext("staff","1") for n in p.iter("note")}
        out.append(max(ns,len(st),1))
    return tuple(out)
def read_pages(pdf,out,threads="4",prefix=()):
    d=pathlib.Path(out)/"homr";d.mkdir(parents=True,exist_ok=True)
    subprocess.run([*prefix,str(OMRD/"homr-venv/bin/python"),str(OMRD/"rasterize.py"),str(pdf),str(d),"300"],check=True)
    env={"OMP_NUM_THREADS":str(threads),"PATH":"/usr/bin:/bin","HOME":str(pathlib.Path.home())}
    rows=[]
    for png in sorted(d.glob("*-p*.png"),key=lambda p:int(p.stem.rsplit("-p",1)[1])):
        xml=png.with_suffix(".musicxml");t=time.time()
        if not xml.exists():
            subprocess.run([*prefix,str(OMRD/"homr-venv/bin/python"),str(SAFE),str(png)],capture_output=True,text=True,env=env)
        rows.append(dict(page=png.stem.rsplit("-p",1)[1],seconds=round(time.time()-t,1),ok=xml.exists(),shape=page_shape(ET.parse(xml).getroot()) if xml.exists() else None,xml=str(xml)))
    return rows
def join(rows,dest):
    good=[r for r in rows if r["ok"]]
    if not good:return dict(kept=0,dropped=[])
    common=collections.Counter(r["shape"] for r in good).most_common(1)[0][0]
    keep=[r for r in good if r["shape"]==common]
    trees=[ET.parse(r["xml"]) for r in keep]
    parts=trees[0].getroot().findall("part")
    for t in trees[1:]:
        for a,b in zip(parts,t.getroot().findall("part")):
            for ms in b.findall("measure"):a.append(copy.deepcopy(ms))
    for p in parts:
        for i,ms in enumerate(p.findall("measure"),1):ms.set("number",str(i))
    trees[0].write(dest,encoding="utf-8",xml_declaration=True)
    return dict(kept=len(keep),common=common,dropped=[(r["page"],r["shape"]) for r in rows if r not in keep])
def plain_join(rows,dest):
    good=[r for r in rows if r["ok"]]
    if not good:return
    trees=[ET.parse(r["xml"]) for r in good]
    parts=trees[0].getroot().findall("part")
    for t in trees[1:]:
        for a,b in zip(parts,t.getroot().findall("part")):
            for ms in b.findall("measure"):a.append(copy.deepcopy(ms))
    for p in parts:
        for i,ms in enumerate(p.findall("measure"),1):ms.set("number",str(i))
    trees[0].write(dest,encoding="utf-8",xml_declaration=True)
