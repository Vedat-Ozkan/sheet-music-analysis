import sys,copy,pathlib,xml.etree.ElementTree as ET,collections
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from fractions import Fraction as F
def fix_rest_chords(m):
    kids=list(m)
    for i,el in enumerate(kids):
        if el.tag=="note" and el.find("rest") is not None and i+1<len(kids) and kids[i+1].tag=="note" and kids[i+1].find("chord") is not None:
            nx=kids[i+1]
            nx.remove(nx.find("chord"))
            b=ET.Element("backup");ET.SubElement(b,"duration").text=el.findtext("duration")
            m.insert(list(m).index(nx),b)
    return m
def split_voices(m):
    seen={}
    for el in m:
        if el.tag=="note" and el.find("voice") is not None:
            k=(el.findtext("staff","1"),el.findtext("voice"))
            seen.setdefault(k,str(len(seen)+1))
            el.find("voice").text=seen[k]
    return m
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
def clean(data,rest=True,voices=True):
    r=ET.fromstring(data)
    for part in r.findall("part"):
        declare_staves(part)
    for m in r.iter("measure"):
        if rest:fix_rest_chords(m)
        if voices:split_voices(m)
    return ET.tostring(r,encoding="utf-8",xml_declaration=True)
