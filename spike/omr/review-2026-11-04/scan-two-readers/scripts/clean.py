import sys,copy,pathlib,xml.etree.ElementTree as ET,collections
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from fractions import Fraction as F
def fix_rest_chords(m):
    kids=list(m)
    for i,el in enumerate(kids):
        if el.tag=="note" and el.find("rest") is not None and i+1<len(kids) and kids[i+1].tag=="note" and kids[i+1].find("chord") is not None:
            nx=kids[i+1]
            nx.remove(nx.find("chord"))
            m.remove(el)
    return m
def split_voices(m):
    seen={}
    for el in m:
        if el.tag=="note" and el.find("voice") is not None:
            k=(el.findtext("staff","1"),el.findtext("voice"))
            seen.setdefault(k,str(len(seen)+1))
            el.find("voice").text=seen[k]
    return m
def sig(e):
    return ET.tostring(e)
def drop_repeats(part):
    cur={}
    for m in part.findall("measure"):
        for at in m.findall("attributes"):
            for e in list(at):
                if e.tag in("key","time","clef"):
                    k=(e.tag,e.get("number"))
                    if cur.get(k)==sig(e):at.remove(e)
                    else:cur[k]=sig(e)
            if not len(at):m.remove(at)
def declare_staves(part):
    n=len({e.text for e in part.iter("staff")})
    if n<2:return
    first=part.find("measure")
    at=first.find("attributes")
    if at is None:
        at=ET.Element("attributes");first.insert(0,at)
    if at.find("staves") is None:
        s=ET.Element("staves");s.text=str(n)
        order=[i for i,e in enumerate(at) if e.tag in("divisions","key","time")]
        at.insert(order[-1]+1 if order else 0,s)
def clean(data,rest=True,voices=True,repeats=True):
    r=ET.fromstring(data)
    for part in r.findall("part"):
        declare_staves(part)
    if repeats:
        for part in r.findall("part"):drop_repeats(part)
    for m in r.iter("measure"):
        if rest:fix_rest_chords(m)
        if voices:split_voices(m)
    return ET.tostring(r,encoding="utf-8",xml_declaration=True)
if __name__=="__main__":
    import subprocess,tempfile,os
    S=pathlib.Path(__file__).parent;P="/home/kema/projects/sheet-music-plugin/.venv/bin/python"
    R=pathlib.Path("/home/kema/projects/sheet-music-plugin/spike/omr/speed/cache/runs")
    def ok(d):
        with tempfile.NamedTemporaryFile(suffix=".musicxml",delete=False,dir=S) as f:
            f.write(d);n=f.name
        r=subprocess.run([P,str(S/"vt.py"),n],capture_output=True);os.unlink(n);return r.returncode==0
    for v in sys.argv[1:]:
        c=collections.Counter()
        for p in sorted((R/v).glob("*.musicxml")):
            d=p.read_bytes()
            c["n"]+=1;c["raw"]+=ok(d);a=ok(clean(d));c["all"]+=a
            if not a:print(" still crash",v,p.name)
        print(v,dict(c),flush=True)
