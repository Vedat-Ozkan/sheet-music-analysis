import collections,json,pathlib,random,subprocess,sys,xml.etree.ElementTree as ET
from lib import *
from truth_shapes import truth_path,split
from merge3 import sub_bars
import homrjoin
import verovio,cairosvg
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
from clean2 import clean
from merge2 import key_alter
OUT=pathlib.Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True)
IDS=[int(x) for x in sys.argv[2:]]
assert all(i in split["tuning"] for i in IDS)
STEPS="CDEFGAB"
SEMI={"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}
def alter(root,rng):
    log=[]
    for pi,part in enumerate(root.findall("part")):
        fifths=0;div=1
        for bi,m in enumerate(part.findall("measure")):
            cur=0;last=0
            for el in list(m):
                if el.tag=="attributes":
                    for k in el.findall("key"):
                        if k.findtext("fifths") is not None:fifths=int(k.findtext("fifths"))
                    if el.findtext("divisions"):div=int(float(el.findtext("divisions")))
                elif el.tag=="backup":cur-=int(float(el.findtext("duration")))
                elif el.tag=="forward":cur+=int(float(el.findtext("duration")))
                elif el.tag=="note":
                    if el.find("grace") is not None or el.find("cue") is not None:continue
                    d=int(float(el.findtext("duration") or 0))
                    chord=el.find("chord") is not None
                    on=last if chord else cur
                    if not chord:last=cur;cur+=d
                    p=el.find("pitch")
                    if p is None or chord or el.find("tie") is not None or el.find("notations/tied") is not None:continue
                    if rng.random()>0.12:continue
                    s,o=p.findtext("step"),int(p.findtext("octave"));old=(o+1)*12+SEMI[s]+int(round(float(p.findtext("alter") or 0)))
                    i=STEPS.index(s)+rng.choice([-1,1]);o2=o+(i//7);s2=STEPS[i%7];a2=key_alter(fifths,s2)
                    p.find("step").text=s2;p.find("octave").text=str(o2)
                    al=p.find("alter")
                    if al is not None:p.remove(al)
                    if a2:
                        al=ET.Element("alter");al.text=str(a2);p.insert(1,al)
                    acc=el.find("accidental")
                    if acc is not None:el.remove(acc)
                    new=(o2+1)*12+SEMI[s2]+a2
                    log.append(dict(part=pi,staff=el.findtext("staff","1"),bar=bi,onset=str(F(on,div)),old=old,new=new))
    return log
from fractions import Fraction as F
def render(xml,dest):
    tk=verovio.toolkit();tk.setOptions({"pageWidth":2100,"pageHeight":2970,"scale":50,"adjustPageHeight":False,"breaks":"auto","footer":"none","header":"none"})
    tk.loadData(xml.decode());paths=[]
    for i in range(1,tk.getPageCount()+1):
        p=dest/f"page-p{i}.png";cairosvg.svg2png(bytestring=tk.renderToSVG(i).encode(),write_to=str(p),output_width=2480,background_color="white");paths.append(p)
    return paths
T=collections.Counter()
for i in IDS:
    d=OUT/str(i);d.mkdir(exist_ok=True)
    rng=random.Random(20261104+i)
    data=truth_path(i).read_bytes();root=root_of(data);log=alter(root,rng)
    alt=ET.tostring(root,encoding="utf-8",xml_declaration=True);(d/"altered.musicxml").write_bytes(alt)
    (d/"log.json").write_text(json.dumps(log))
    h=d/"homr";h.mkdir(exist_ok=True)
    pngs=render(alt,h)
    env={"OMP_NUM_THREADS":"4","PATH":"/usr/bin:/bin","HOME":str(pathlib.Path.home())}
    rows=[]
    for png in pngs:
        x=png.with_suffix(".musicxml")
        if not x.exists():subprocess.run([str(homrjoin.OMRD/"homr-venv/bin/python"),str(homrjoin.SAFE),str(png)],capture_output=True,text=True,env=env)
        rows.append(dict(page=png.stem,ok=x.exists(),xml=str(x),shape=homrjoin.page_shape(ET.parse(x).getroot()) if x.exists() else None))
    homrjoin.join(rows,d/"homr.musicxml")
    if not (d/"homr.musicxml").exists():continue
    tb=parse(alt);hb=parse(clean((d/"homr.musicxml").read_bytes()))
    ot,oh=staff_order(alt),staff_order(clean((d/"homr.musicxml").read_bytes()))
    T["pieces"]+=1;T["altered notes"]+=len(log)
    if len(ot)!=len(oh):T["shape mismatch"]+=1;continue
    groups=collections.defaultdict(list)
    for z,y in enumerate(oh):groups[y[0]].append(z)
    altered={(l["part"],l["staff"],l["bar"],F(l["onset"])):l for l in log}
    for hp,idx in groups.items():
        kt={ot[z] for z in idx};kh={oh[z] for z in idx}
        pairs=dict(align_bars(sub_bars(tb,kt),sub_bars(hb,kh)))
        for b,k in pairs.items():
            for z in idx:
                tk=ot[z]
                he=[e for e in hb[k].events if (e.part,e.staff)==oh[z]]
                hm=collections.defaultdict(list)
                for e in he:hm[e.onset]+=e.midis
                for e in tb[b].events:
                    if (e.part,e.staff)!=tk or e.rest or not e.midis:continue
                    key=(e.part,e.staff,b,e.onset)
                    got=hm.get(e.onset,[])
                    if key in altered:
                        l=altered[key]
                        T["a_read_new"]+=l["new"] in got;T["a_read_old"]+=(l["old"] in got and l["new"] not in got);T["a_other"]+=(l["new"] not in got and l["old"] not in got);T["a_n"]+=1
                    elif len(e.midis)==1:
                        m=e.midis[0];T["c_n"]+=1;T["c_right"]+=m in got
                        near={m+x for x in(-2,-1,1,2)}
                        T["c_step_off"]+=(m not in got and bool(near&set(got)))
print(dict(T))
if T["a_n"]:print("altered read as printed %.1f%%, read as the original %.1f%%, other %.1f%%"%(100*T["a_read_new"]/T["a_n"],100*T["a_read_old"]/T["a_n"],100*T["a_other"]/T["a_n"]))
if T["c_n"]:print("unaltered single notes read right %.1f%%, read a step off %.1f%%"%(100*T["c_right"]/T["c_n"],100*T["c_step_off"]/T["c_n"]))
