import collections,copy,json,math,pathlib,sys,warnings,xml.etree.ElementTree as ET
warnings.filterwarnings("ignore")
sys.path.insert(0,"/home/kema/projects/sheet-music-plugin/spike/omr/speed")
from fractions import Fraction as F
from barparse import OMR,parse,align_bars
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from clean2 import clean
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
        if (not same and fh and not (fa and not fh)) or (same and not fa and fh):out[x]=y
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
SIGN={-2:"flat-flat",-1:"flat",0:"natural",1:"sharp",2:"double-sharp"}
FIFTHS=["F","C","G","D","A","E","B"]
SEMI={"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}
def key_alter(f,step):
    if f>0 and step in FIFTHS[:f]:return 1
    if f<0 and step in FIFTHS[::-1][:-f]:return -1
    return 0
def midi(el):
    p=el.find("pitch")
    if p is None:return None
    return (int(p.findtext("octave"))+1)*12+SEMI[p.findtext("step")]+int(round(float(p.findtext("alter") or 0)))
def add_signs(notes,fifths):
    state={}
    for on,d,el in sorted(notes,key=lambda t:t[0]):
        p=el.find("pitch")
        if p is None:continue
        step,oc=p.findtext("step"),p.findtext("octave");al=int(round(float(p.findtext("alter") or 0)))
        cur=state.get((step,oc),key_alter(fifths,step))
        if el.find("accidental") is None and al!=cur and al in SIGN:
            kids=list(el);at=max((i for i,k in enumerate(kids) if k.tag in("type","dot","voice")),default=len(kids)-1)+1
            a=ET.Element("accidental");a.text=SIGN[al];el.insert(at,a)
        state[(step,oc)]=al
def copy_ties(hnotes,anotes):
    found=collections.defaultdict(list)
    for on,d,el in anotes:
        if el.find("tie") is not None:found[(midi(el),on)].append(el)
    for on,d,el in hnotes:
        src=found.get((midi(el),on))
        if not src or el.find("tie") is not None:continue
        at=[i for i,k in enumerate(list(el)) if k.tag=="duration"][0]+1
        for t in reversed(src[0].findall("tie")):el.insert(at,copy.deepcopy(t))
        nt=el.find("notations")
        if nt is None:nt=ET.SubElement(el,"notations")
        for t in src[0].findall("notations/tied"):nt.append(copy.deepcopy(t))
def merge(pa,ph):
    da=pa.read_bytes() if pa.exists() and pa.stat().st_size else None
    dh=clean(ph.read_bytes())
    if da is None:
        r=ET.fromstring(dh)
        for part in r.findall("part"):
            div=1;f=0
            for ms in part.findall("measure"):
                notes,_,_,div=walk(ms,div)
                for k in ms.findall("attributes/key"):
                    if k.findtext("fifths") is not None:f=int(k.findtext("fifths"))
                for st in {t[2].findtext("staff","1") for t in notes}:
                    add_signs([t for t in notes if t[2].findtext("staff","1")==st],f)
        return ET.tostring(r,encoding="utf-8",xml_declaration=True),0,0
    if len(ET.fromstring(da).findall("part"))>1:return da,0,0
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
        adiv=1;keyof={}
        for j,m in enumerate(part.findall("measure")):
            notes,clefs,other,adiv=walk(m,adiv)
            for k in m.findall("attributes/key"):
                if k.findtext("fifths") is not None:
                    if k.get("number") is None:keyof.clear()
                    keyof[k.get("number","*")]=int(k.findtext("fifths"))
            sel={x:y for x,y in (choose(a[j],h[ah[j]],mode) if j in ah and j<len(a) else {}).items() if x[0]==pi}
            if not sel:
                for st in {t[2].findtext("staff","1") for t in notes}:
                    add_signs([t for t in notes if t[2].findtext("staff","1")==st],keyof.get(st,keyof.get("*",0)))
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
            dirs=[]
            for cur,el in other:
                if el.tag in("print","barline"):continue
                if el.tag=="direction" and cur>0 and el.find("offset") is None:
                    o=ET.Element("offset");o.text=str(int(cur*L))
                    el.insert(max(i for i,k in enumerate(list(el)) if k.tag=="direction-type")+1,o)
                dirs.append(el)
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
                    src=[(a,b,copy.deepcopy(c)) for a,b,c in hn if c.findtext("staff","1")==y[1]]
                    copy_ties(src,byst.get(st,[]))
                    add_signs(src,keyof.get(st,keyof.get("*",0)))
                    changed+=1
                else:
                    src=byst.get(st,[])
                    add_signs(src,keyof.get(st,keyof.get("*",0)))
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
        (out/ph.name).write_bytes(clean(data,rest=False,voices=False));tot+=c
    print("written",V,"staves replaced",tot)
