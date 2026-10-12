import sys,hashlib,json
sys.path.insert(0,'analysis')
from attribute import *
pdf,bar=sys.argv[1],int(sys.argv[2]); j0=int(sys.argv[3]) if len(sys.argv)>3 else bar
base=json.load(open(HERE/'results-baseline.json'));sig=base['audiveris_install']
man=json.load(open(HERE/'manifest.json'));p=next(x for x in man['pdfs'] if pdf in x['pdf'])
key=hashlib.sha256((HERE/p['pdf']).read_bytes()+sig.encode()).hexdigest()[:32]
T,_=events((HERE/man['pieces'][p['piece']]['truth']).read_bytes());O,_=events((HERE/'cache'/f'{key}.musicxml').read_bytes())
f=lambda b:sorted((str(o),m,'g' if x['grace'] else '','t' if x['tup'] else '','.' if x['dot'] else '') for m,o,x in b)
print('T',bar,f(T[bar]));print('O',j0,f(O[j0]))
print(key)
