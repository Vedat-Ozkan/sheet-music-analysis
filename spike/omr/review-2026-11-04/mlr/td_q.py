import re,sys
f,xa,xb,ya,yb,sheet=sys.argv[1],*map(int,sys.argv[2:6]),sys.argv[6]
pt=re.compile(r"x=(\d+),y=(\d+)")
for l in open(f,errors="replace"):
    if "TD " not in l or f"#{sheet}]" not in l: continue
    m=pt.findall(l)
    if not m: continue
    x,y=int(m[0][0]),int(m[0][1])
    if xa<=x<=xb and ya<=y<=yb:
        print(re.sub(r"java.awt.(Point|Rectangle)","",l[l.index("TD "):]).strip()[:230])
