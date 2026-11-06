import collections,json,re,sys,warnings,zipfile,io
warnings.filterwarnings("ignore")
sys.path.insert(0,'.')
import xml.etree.ElementTree as ET
from whole_bars import OMR,SETS,HERE
from engine.read_pdf import _lyrics_to_directions,_keep_meaningful_text
SF=re.compile(r'^(sf|sfz|sfp|fz|rf|rfz|s\s*f|f2|sƒ)\.?$',re.I)
def count(root):
    c=collections.Counter()
    for d in root.iter('dynamics'):
        for k in d:
            if k.tag in('sf','sfz','sfp','fz','rf','rfz'): c['dyn']+=1
    for w in root.iter('words'):
        if SF.match((w.text or '').strip()): c['words']+=1
    for l in root.iter('lyric'):
        if SF.match((l.findtext('text') or '').strip()): c['lyric']+=1
    return c
tot=collections.Counter();worst=[]
for name in SETS:
    man=json.loads((OMR/name/'manifest.json').read_text())
    for en in man['pdfs']:
        stem=en['pdf'].rsplit('/',1)[-1][:-4]
        r=HERE/'cache/runs/marks1'/f'{name}--{stem}.musicxml'
        if not r.exists() or not r.stat().st_size: continue
        root=ET.fromstring(r.read_bytes()); a=count(root)
        for k,v in a.items(): tot['read_'+k]+=v
        worst.append((a['words'],a['lyric'],a['dyn'],stem))
        t=OMR/name/man['pieces'][en['piece']]['truth']
        d=t.read_bytes()
        if d[:2]==b'PK':
            z=zipfile.ZipFile(io.BytesIO(d)); f=[x for x in z.namelist() if x.endswith(('.xml','.musicxml')) and 'META' not in x][0]; d=z.read(f)
        b=count(ET.fromstring(d))
        for k,v in b.items(): tot['truth_'+k]+=v
print(dict(tot)); print(sorted(worst,reverse=True)[:6]); print([w for w in worst if 'n04' in w[3] or 'quartet' in w[3].lower()][:8])
