import re, sys, zipfile, collections, math
from pathlib import Path
import xml.etree.ElementTree as ET
for omr in sys.argv[1:]:
    z = zipfile.ZipFile(omr)
    for n in sorted(z.namelist()):
        if not re.search(r"sheet#\d+\.xml$", n): continue
        root = ET.fromstring(z.read(n))
        skew = root.find(".//skew")
        tops = []
        for sg in root.iter("sig"):
            pass
        c = [e for e in root.iter("clef") if e.get("shape")]
        kinds = collections.Counter(e.get("shape") for e in c)
        staves = sum(1 for s in root.iter("staff") if s.get("id"))
        print(Path(omr).parent.name[:28], n.split("/")[-1], "skewdeg", round(math.degrees(math.atan(float(skew.get("slope")))),2), "staves", staves, dict(kinds), [(e.get("shape")[:1], e.get("staff"), round(float(e.get("grade",0)),2), e.find("bounds").attrib if False else "") for e in c][:0])
