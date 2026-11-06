import random,json,sys,statistics as S
from truth_shapes import truth_path,split
from lib import parse
bars=[len(parse(truth_path(i).read_bytes())) for i in split["tuning"]]
five=[(24,0,3),(77,61,64),(53,41,47),(26,11,15),(73,26,44)]
rates=[(m-c)/b for b,c,m in five]
print("five gain points by piece",[round(100*r,1) for r in rates],"sd",round(100*S.pstdev(rates),1),"mean bars tuning half",round(S.mean(bars),1))
rng=random.Random(20261104)
def obs(n,delta):
    cs=[rng.choice(rates)-S.mean(rates)+delta for _ in range(n)];bs=[rng.choice(bars) for _ in range(n)]
    return cs,bs
def boot(cs,bs,it=400):
    v=[]
    for _ in range(it):
        idx=[rng.randrange(len(cs)) for _ in cs];v.append(100*sum(cs[i]*bs[i] for i in idx)/sum(bs[i] for i in idx))
    v.sort();return v[int(.05*it)],v[int(.95*it)]
for n in (8,12,15,20,30):
    row=[]
    for delta in (0,.03,.05,.08,.10,.13):
        ok=0;wid=[]
        for _ in range(500):
            c,b=obs(n,delta);g=100*sum(x*y for x,y in zip(c,b))/sum(b);lo,hi=boot(c,b);wid.append(hi-lo)
            ok+=g>=5 and lo>=2
        row.append(f"gain{int(delta*100)}:{ok/5:.0f}%")
    print("pieces",n,"90% interval width",round(S.mean(wid),1),"pass chance",*row)
c=[r for r in rates];b=[x[0] for x in five]
print("five gain and bootstrap",round(100*sum(x*y for x,y in zip(c,b))/sum(b),1),boot(c,b,4000))
