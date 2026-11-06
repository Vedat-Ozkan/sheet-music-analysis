import sys,glob,json,numpy as np,pypdfium2 as pdfium
f=glob.glob("/home/kema/projects/sheet-music-plugin/spike/omr/bench-scan/incoming/*.pdf")[0]
pdf=pdfium.PdfDocument(f);out=[]
for i in range(len(pdf)):
    im=np.array(pdf[i].render(scale=150/72).to_pil().convert("L"))
    dark=(im<140).mean(axis=1)
    rows=(dark>0.35).sum()
    out.append(int(rows))
nomusic=[i+1 for i,r in enumerate(out) if r<10]
print(nomusic)
seg=[];cur=[]
for i,r in enumerate(out,1):
    if r<10:
        if cur:seg.append(cur);cur=[]
    else:cur.append(i)
if cur:seg.append(cur)
print(len(seg),[(s[0],s[-1],len(s)) for s in seg])
json.dump(seg,open(sys.argv[1],"w"))
