import collections
def same_classes(a,h,j,k,x,y):
    pc=lambda ev:collections.Counter(m%12 for e in ev for m in e.midis)
    return pc([e for e in a[j].events if (e.part,e.staff)==x])==pc([e for e in h[k].events if (e.part,e.staff)==y])
