import random,statistics as S
from truth_shapes import truth_path,split
from lib import parse
bars=[len(parse(truth_path(i).read_bytes())) for i in split["tuning"]]
rates=[.125,.039,.113,.154,.247]
rng=random.Random(20261104)
for n in (10,15,20,30):
    for delta in (.08,.13):
        over25=over33=over50=loo=0;N=4000
        for _ in range(N):
            b=rng.sample(bars,n);g=[max(0,(rng.choice(rates)-S.mean(rates)+delta))*x for x in b]
            s=max(g)/sum(g);over25+=s>.25;over33+=s>1/3;over50+=s>.5
            tot=sum(g);mn=min(100*(tot-x)/(sum(b)-y) for x,y in zip(g,b));loo+=mn<2
        print(f"pieces {n} true gain {int(delta*100)}: largest share over 1/4 {100*over25/N:.0f}%, over 1/3 {100*over33/N:.0f}%, over 1/2 {100*over50/N:.0f}%, leave-one-out under 2 points {100*loo/N:.0f}%")
print("bars tuning half: max",max(bars),"median",S.median(bars),"pieces under 15 bars",sum(x<15 for x in bars))
