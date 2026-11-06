import collections,copy,json,math,pathlib,sys,warnings,xml.etree.ElementTree as ET
warnings.filterwarnings("ignore")
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from fractions import Fraction as F
from barparse import OMR,parse,align_bars
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from clean import clean
RUNS=OMR/"speed/cache/runs"
def staves(b):
    d=collections.defaultdict(list)
    for e in b.events:d[(e.part,e.staff)].append(e)
    return d
def fill(ev,full):
    return bool(ev) and full is not None and max(e.onset+e.dur for e in ev)==full
def sound(ev):
    return collections.Counter(m for e in ev for m in e.midis)
def choose(ba,bh,mode):
    sa,sh=staves(ba),staves(bh)
    ka,kh=sorted(sa,key=str),sorted(sh,key=str)
    if len(ka)!=len(kh):return {}
    full=ba.full or bh.full or mode
    out={}
    for x,y in zip(ka,kh):
        same=sound(sa[x])==sound(sh[y]);fa,fh=fill(sa[x],full),fill(sh[y],full)
        if (not same and (fh or not fa)) or (same and not fa and fh):out[x]=y
    return out
def divisions(root):
    return {int(d.text) for d in root.iter("divisions")}|{1}
def walk(measure,div):
    cur=F(0);last=F(0);out=[];clefs={};other=[]
    for el in measure:
        if el.tag=="attributes":
            if el.find("divisions") is not None:div=int(el.find("divisions").text)
            for c in el.findall("clef"):clefs[c.get("number","1")]=c
        elif el.tag=="backup":cur-=F(el.findtext("duration"))/div
        elif el.tag=="forward":cur+=F(el.findtext("duration"))/div
        elif el.tag=="note":
            d=F(el.findtext("duration") or 0)/div
            if el.find("chord") is not None:on=last
            else:on=cur;last=cur
            out.append((on,d,el))
            if el.find("chord") is None and el.find("grace") is None:cur+=d
        else:other.append((cur,el))
    return out,clefs,other,div
def emit(new,notes,L,staff_out,voice_base):
    voices=collections.defaultdict(list)
    for on,d,el in notes:voices[el.findtext("voice","1")].append((on,d,el))
    cursor=F(0);n=voice_base
    for v in sorted(voices):
        n+=1
        prev=None
        for on,d,el in sorted(voices[v],key=lambda t:(t[0],t[2].find("chord") is not None)):
            if el.find("chord") is not None and prev!=on:
                el=copy.deepcopy(el);el.remove(el.find("chord"))
            prev=on
            if el.find("chord") is None and on>cursor:
                f=ET.SubElement(new,"forward");ET.SubElement(f,"duration").text=str(int((on-cursor)*L));cursor=on
            elif el.find("chord") is None and on<cursor:
                b=ET.SubElement(new,"backup");ET.SubElement(b,"duration").text=str(int((cursor-on)*L));cursor=on
            c=copy.deepcopy(el)
            if c.find("duration") is not None:c.find("duration").text=str(max(1,int(d*L)))
            if c.find("voice") is not None:c.find("voice").text=str(n)
            s=c.find("staff")
            if s is not None:s.text=staff_out
            new.append(c)
            if el.find("chord") is None and el.find("grace") is None:cursor=on+d
    if cursor>0:
        b=ET.SubElement(new,"backup");ET.SubElement(b,"duration").text=str(int(cursor*L))
    return n
def merge(pa,ph):
    da=pa.read_bytes() if pa.exists() and pa.stat().st_size else None
    dh=clean(ph.read_bytes())
    if da is None:return dh,0,0
    a,h=parse(da),parse(dh)
    ah=dict(align_bars(a,h))
    ends=[max(e.onset+e.dur for e in b.events) for b in a+h if b.events]
    mode=collections.Counter(ends).most_common(1)[0][0] if ends else None
    ra,rh=ET.fromstring(da),ET.fromstring(dh)
    pas,phs=ra.findall("part"),rh.findall("part")
    L=math.lcm(*divisions(ra),*divisions(rh))
    for sc in [2,3,4]:
        if L*sc<=100000 and L%sc: pass
    hm=phs[0].findall("measure")
    hdiv=1;hdivs=[]
    for m in hm:
        d=m.find("attributes/divisions")
        if d is not None:hdiv=int(d.text)
        hdivs.append(hdiv)
    changed=0
    for pi,part in enumerate(pas):
        adiv=1
        for j,m in enumerate(part.findall("measure")):
            notes,clefs,other,adiv=walk(m,adiv)
            sel={x:y for x,y in (choose(a[j],h[ah[j]],mode) if j in ah and j<len(a) else {}).items() if x[0]==pi}
            if not sel:
                for at in m.findall("attributes"):
                    for dv in at.findall("divisions"):at.remove(dv)
                for el in m:
                    if el.tag in("note","backup","forward") and el.find("duration") is not None:
                        el.find("duration").text=str(int(F(el.findtext("duration"))*F(L,adiv)))
                continue
            for at in m.findall("attributes"):
                for dv in at.findall("divisions"):at.remove(dv)
            attrs=[el for el in m if el.tag=="attributes"]
            pre=[el for el in m if el.tag in("print",)]
            bars=[el for el in m if el.tag=="barline"]
            dirs=[el for _,el in other if el.tag not in("print","barline")]
            for el in list(m):m.remove(el)
            for el in pre+attrs+dirs:m.append(el)
            byst=collections.defaultdict(list)
            for t in notes:byst[t[2].findtext("staff","1")].append(t)
            hn=None
            base=0
            for st in sorted(set(byst)|{x[1] for x in sel},key=str):
                if (pi,st) in sel:
                    y=sel[(pi,st)]
                    if hn is None:
                        hn,_,_,_=walk(hm[ah[j]],hdivs[ah[j]])
                    src=[t for t in hn if t[2].findtext("staff","1")==y[1]]
                    changed+=1
                else:src=byst.get(st,[])
                base=emit(m,src,L,st,base)
            for el in bars:m.append(el)
        first=part.find("measure")
        at=first.find("attributes")
        if at is None:
            at=ET.Element("attributes");first.insert(0,at)
        d=ET.Element("divisions");d.text=str(L);at.insert(0,d)
    return ET.tostring(ra,encoding="utf-8",xml_declaration=True),changed,len(a)
if __name__=="__main__":
    A,H,V=sys.argv[1:4]
    out=RUNS/V;out.mkdir(exist_ok=True)
    tot=0
    for ph in sorted((RUNS/H).glob("*.musicxml")):
        data,c,n=merge(RUNS/A/ph.name,ph)
        (out/ph.name).write_bytes(clean(data));tot+=c
    print("written",V,"staves replaced",tot)
