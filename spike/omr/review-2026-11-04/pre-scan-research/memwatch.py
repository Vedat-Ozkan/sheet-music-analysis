import collections,json,os,re,subprocess,sys,time
def children():
    kids=collections.defaultdict(list)
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                s=open(f"/proc/{p}/stat").read()
                kids[int(s.rsplit(")",1)[1].split()[1])].append(int(p))
            except OSError:
                pass
    return kids
def tree(root,kids):
    out=[];st=[root]
    while st:
        x=st.pop();out.append(x);st+=kids.get(x,[])
    return out
def mem(pid):
    try:
        t=open(f"/proc/{pid}/smaps_rollup").read()
        return int(re.search(r"^Pss:\s+(\d+)",t,re.M).group(1)),int(re.search(r"^Rss:\s+(\d+)",t,re.M).group(1)),open(f"/proc/{pid}/comm").read().strip()
    except (OSError,AttributeError):
        return None
out,cmd=sys.argv[1],sys.argv[2:]
p=subprocess.Popen(cmd)
samples=[]
while p.poll() is None:
    now=time.time();kids=children();tot=rtot=0;by=collections.Counter()
    for pid in tree(p.pid,kids):
        m=mem(pid)
        if m:
            tot+=m[0];rtot+=m[1];by[m[2]]+=m[0]
    samples.append((round(now,2),tot//1024,rtot//1024,{k:v//1024 for k,v in by.items()}))
    time.sleep(0.4)
peak=max(samples,key=lambda s:s[1]) if samples else None
json.dump({"cmd":cmd,"exit":p.returncode,"peak_pss_mb":peak[1] if peak else None,"peak_rss_sum_mb":max(s[2] for s in samples) if samples else None,"at_peak":peak[3] if peak else None,"samples":samples},open(out,"w"))
print("exit",p.returncode,"peak PSS MB",peak[1] if peak else None,"RSS-sum MB",max(s[2] for s in samples) if samples else None,"at peak",peak[3] if peak else None,flush=True)
