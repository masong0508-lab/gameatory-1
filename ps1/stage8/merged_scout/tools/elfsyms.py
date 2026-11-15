import subprocess,re,collections
def load(elf):
    """-> (funcs [(addr,size,name,mode 'T'|'A',section)], secs {name:(addr,size)}, mapsyms)"""
    secs={}; names={}
    for l in subprocess.run(['llvm-readelf','-S','-W',elf],capture_output=True,text=True).stdout.splitlines():
        m=re.match(r'\s*\[\s*(\d+)\]\s+(\S+)\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)',l)
        if m: names[int(m.group(1))]=m.group(2); secs[m.group(2)]=(int(m.group(4),16),int(m.group(6),16))
    ms=collections.defaultdict(list); fs=[]
    for l in subprocess.run(['llvm-readelf','-s','-W',elf],capture_output=True,text=True).stdout.splitlines():
        p=l.split()
        if len(p)<8 or not p[0].endswith(':'): continue
        try: nd=int(p[6])
        except: continue
        a=int(p[1],16); nm=p[7]
        if re.match(r'\$[atd](\.|$)',nm): ms[nd].append((a,nm[1]))
        elif p[3]=='FUNC': fs.append((a&~1,int(p[2]),nm,nd))
    for v in ms.values(): v.sort()
    out=[]
    for a,sz,nm,nd in fs:
        mode='A'
        for x,m in ms[nd]:
            if x<=a: mode='T' if m=='t' else 'A' if m=='a' else '?'
            else: break
        out.append((a,sz,nm,mode,names.get(nd)))
    return out,secs,{names.get(k):v for k,v in ms.items()}
def owners(objdir):
    import os
    o={}
    for f in sorted(os.listdir(objdir)):
        if not f.endswith('.o'): continue
        for l in subprocess.run(['llvm-nm','--defined-only',os.path.join(objdir,f)],capture_output=True,text=True).stdout.splitlines():
            p=l.split()
            if len(p)==3 and p[1] in 'tTwW': o.setdefault(p[2],re.sub(r'\.(c|s)\.o$','',f))
    return o
