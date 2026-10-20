import sys, json, zipfile, io
from pathlib import Path
import xml.etree.ElementTree as ET
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'bench'))
import build as B
lieder = Path(sys.argv[1]) / 'scores'
old = set()
for d in ('bench', 'bench-heldout', 'bench-heldout2'):
    for p in json.loads((HERE.parent / d / 'manifest.json').read_text())['pieces'].values():
        old.add(p['source_url'].rstrip('/'))
rows = []
for f in sorted(lieder.glob('*/*/*/*.mxl')):
    sub = '/'.join(f.relative_to(lieder).parts[:3])
    if 'https://github.com/OpenScore/Lieder/tree/main/scores/' + sub in old:
        continue
    try:
        root = ET.fromstring(B.excerpt(f.read_bytes(), 32))
    except Exception:
        continue
    n = hidden = 0
    for note in root.iter('note'):
        if note.find('time-modification') is None or note.find('grace') is not None:
            continue
        n += 1
        shown = any(t.get('type') == 'start' and t.get('show-number') != 'none' for t in note.iter('tuplet'))
    printed_starts = sum(1 for t in root.iter('tuplet') if t.get('type') == 'start' and t.get('show-number') != 'none')
    total_starts = sum(1 for t in root.iter('tuplet') if t.get('type') == 'start')
    rows.append((n, printed_starts, total_starts, sub))
rows.sort(reverse=True)
for r in rows[:60]:
    print(*r)
