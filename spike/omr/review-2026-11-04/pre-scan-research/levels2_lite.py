import collections,sys
from lib import *
sys.path.insert(0,str(OMR/"review-2026-11-04/scan-two-readers/scripts"))
import merge2 as MX
def barinfo(data):
    r=root_of(data);out=collections.defaultdict(lambda:{"stops":collections.Counter()})
    for pi,part in enumerate(r.findall("part")):
        div=1
        for bi,m in enumerate(part.findall("measure")):
            notes,_,_,div=MX.walk(m,div)
            for on,d,el in notes:
                p=el.find("pitch")
                if p is None:continue
                for t in el.findall("tie"):
                    if t.get("type")=="stop":out[bi]["stops"][(pi,el.findtext("staff","1"),p.findtext("step"),p.findtext("octave"),on)]+=1
    return out
