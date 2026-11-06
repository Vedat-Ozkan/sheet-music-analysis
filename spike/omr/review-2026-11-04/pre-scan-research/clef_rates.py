import collections,json,sys
from lib import *
sys.path.insert(0,str(HERE))
from truth_shapes import meta,truth_path,split
def changes(data):
    b=parse(data);seen=set();mid=0;bars=len(b);chbars=0
    for i,x in enumerate(b):
        new=[k for k in x.clef if k in seen];seen|=set(x.clef)
        if new:chbars+=1
    notes=sum(sum(pitches(x).values()) for x in b)
    return bars,chbars,notes
for s,st in FIVE:
    b,c,n=changes(truth(s,st));print(st[:26],"bars",b,"bars with clef change",c,f"{100*c/b:.1f}%","notes per bar",round(n/b,1))
T=collections.Counter();per=[]
for i in split["tuning"]:
    f=truth_path(i)
    b,c,n=changes(f.read_bytes());T["bars"]+=b;T["chg"]+=c;T["notes"]+=n;per.append(c/b)
print("lieder tuning references: bars",T["bars"],"bars with clef change",T["chg"],f"{100*T['chg']/T['bars']:.1f}%","notes per bar",round(T["notes"]/T["bars"],1),"pieces with any",sum(p>0 for p in per),"of",len(per))
