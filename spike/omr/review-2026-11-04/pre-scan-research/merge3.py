import collections,copy,math,sys,xml.etree.ElementTree as ET
from lib import *
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
from clean2 import clean
import merge2 as M2
from merge2 import walk,emit,add_signs,copy_ties,fill,sound,divisions
from fractions import Fraction as F
RULES={
 "as_written":lambda same,fa,fh:(not same and fh) or (same and not fa and fh),
 "only_if_current_short":lambda same,fa,fh:fh and not fa,
}
def copy_lyrics(hnotes,anotes):
    found=collections.defaultdict(list)
    for on,d,el in anotes:
        found[on]+=el.findall("lyric")
    used=set()
    for on,d,el in hnotes:
        if on in used or el.find("chord") is not None or el.find("lyric") is not None or el.find("rest") is not None:continue
        words=found.get(on)
        if not words:continue
        used.add(on)
        kids=list(el);at=max((i for i,k in enumerate(kids) if k.tag in("pitch","duration","tie","voice","type","dot","accidental","stem","staff","beam","notations")),default=len(kids)-1)+1
        for i,w in enumerate(words):el.insert(at+i,copy.deepcopy(w))
def sub_bars(bars,keys):
    out=[]
    for b in bars:
        n=type(b)();n.events=[e for e in b.events if (e.part,e.staff) in keys];n.full=b.full
        out.append(n)
    return out
def staves(bar,keys):
    d=collections.defaultdict(list)
    for e in bar.events:
        if (e.part,e.staff) in keys:d[(e.part,e.staff)].append(e)
    return d
def plan(da,dh,rule,veto=None):
    oa,oh=staff_order(da),staff_order(dh)
    a,h=parse(da),parse(dh)
    ends=[max(e.onset+e.dur for e in b.events) for b in a+h if b.events]
    mode=collections.Counter(ends).most_common(1)[0][0] if ends else None
    groups=collections.defaultdict(list)
    for x,y in zip(oa,oh):groups[y[0]].append((x,y))
    sel=collections.defaultdict(dict);st=collections.Counter()
    for hp,pairs in groups.items():
        ka={x for x,_ in pairs};kh={y for _,y in pairs}
        sa,sh=sub_bars(a,ka),sub_bars(h,kh)
        ah=dict(align_bars(sa,sh))
        for j,k in ah.items():
            if j>=len(a) or k>=len(h):continue
            da_,dh_=staves(a[j],ka),staves(h[k],kh)
            if len(da_)!=len(dh_):
                st["bar_staff_count_differs"]+=1
                continue
            full=a[j].full or h[k].full or mode
            for x,y in pairs:
                ea,eh=da_.get(x,[]),dh_.get(y,[])
                if not ea and not eh:continue
                same=sound(ea)==sound(eh);fa,fh=fill(ea,full),fill(eh,full)
                st[("same" if same else "differ",fa,fh)]+=1
                if RULES[rule](same,fa,fh) and not (veto and not same and fa and fh and veto(a,h,j,k,x,y)):sel[j][x]=(y,k)
    return sel,st,len(oa),len(oh)
NO_READING=OMR/"review-2026-11-04/pre-scan-research/no-such-file"
def merge(pa,ph,rule="as_written",veto=None):
    da=pa.read_bytes() if pa.exists() and pa.stat().st_size else None
    if da is None:
        data,_,_=M2.merge(pa,ph)
        return data,{"reason":"no current reading"}
    dh=clean(ph.read_bytes())
    if len(parse(da))<0.5*len(parse(dh)):
        data,_,_=M2.merge(NO_READING,ph)
        return data,{"reason":"current has under half of homr's bars"}
    sel,st,na,nh=plan(da,dh,rule,veto)
    if na!=nh:
        return da,{"reason":"staff count differs","current":na,"homr":nh}
    ra,rh=ET.fromstring(da),ET.fromstring(dh)
    L=math.lcm(*divisions(ra),*divisions(rh))
    hm=[]
    hdivs=[]
    for part in rh.findall("part"):
        ms=part.findall("measure");d=1;ds=[]
        for m in ms:
            x=m.find("attributes/divisions")
            if x is not None:d=int(x.text)
            ds.append(d)
        hm.append(ms);hdivs.append(ds)
    changed=0
    for pi,part in enumerate(ra.findall("part")):
        adiv=1;keyof={}
        for j,m in enumerate(part.findall("measure")):
            notes,clefs,other,adiv=walk(m,adiv)
            for k in m.findall("attributes/key"):
                if k.findtext("fifths") is not None:
                    if k.get("number") is None:keyof.clear()
                    keyof[k.get("number","*")]=int(k.findtext("fifths"))
            mine={x:v for x,v in sel.get(j,{}).items() if x[0]==pi}
            if not mine:
                for s in {t[2].findtext("staff","1") for t in notes}:
                    add_signs([t for t in notes if t[2].findtext("staff","1")==s],keyof.get(s,keyof.get("*",0)))
                for at in m.findall("attributes"):
                    for dv in at.findall("divisions"):at.remove(dv)
                for el in m:
                    if el.tag in("note","backup","forward") and el.find("duration") is not None:
                        el.find("duration").text=str(int(F(el.findtext("duration"))*F(L,adiv)))
                continue
            for at in m.findall("attributes"):
                for dv in at.findall("divisions"):at.remove(dv)
            attrs=[el for el in m if el.tag=="attributes"]
            pre=[el for el in m if el.tag=="print"]
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
            base=0
            for s in sorted(set(byst)|{x[1] for x in mine},key=str):
                if (pi,s) in mine:
                    (hp,hs),k=mine[(pi,s)]
                    hn,_,_,_=walk(hm[hp][k],hdivs[hp][k])
                    src=[(a,b,copy.deepcopy(c)) for a,b,c in hn if c.findtext("staff","1")==hs]
                    copy_ties(src,byst.get(s,[]))
                    copy_lyrics(src,byst.get(s,[]))
                    add_signs(src,keyof.get(s,keyof.get("*",0)))
                    changed+=1
                else:
                    src=byst.get(s,[])
                    add_signs(src,keyof.get(s,keyof.get("*",0)))
                base=emit(m,src,L,s,base)
            for el in bars:m.append(el)
        first=part.find("measure")
        at=first.find("attributes")
        if at is None:
            at=ET.Element("attributes");first.insert(0,at)
        d=ET.Element("divisions");d.text=str(L);at.insert(0,d)
    return clean(ET.tostring(ra,encoding="utf-8",xml_declaration=True),rest=False,voices=False),{"reason":"merged","staves":changed,"decisions":st}
