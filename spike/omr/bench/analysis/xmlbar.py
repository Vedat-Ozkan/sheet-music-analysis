import sys,io,zipfile
import xml.etree.ElementTree as ET
sys.path.insert(0,'analysis')
from attribute import rx
root=rx(open(sys.argv[1],'rb').read()); k=int(sys.argv[2])
for pi,p in enumerate(root.iter('part')):
    m=list(p.iter('measure'))[k]; print('part',pi,'measure',m.get('number'))
    s=[]
    for el in m:
        if el.tag=='note':
            pt=el.find('pitch'); nm=(pt.findtext('step')+(('%+d'%int(float(pt.findtext('alter') or 0))) if pt.findtext('alter') else '')+pt.findtext('octave')) if pt is not None else 'R'
            s.append(('+' if el.find('chord') is not None else '')+nm+'/'+el.findtext('duration')+('.' if el.find('dot') is not None else '')+(' t' if el.find('time-modification') is not None else '')+' v'+(el.findtext('voice') or '?')+' s'+(el.findtext('staff') or '?')+(' G' if el.find('grace') is not None else ''))
        elif el.tag in('backup','forward'): s.append(el.tag+el.findtext('duration'))
        elif el.tag=='attributes': s.append('ATTR div=%s'%el.findtext('divisions'))
    print(' | '.join(s))
