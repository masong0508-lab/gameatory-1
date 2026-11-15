#!/usr/bin/env python3
"""elfcount.py ELF OBJDIR : ground truth for the merged Star-FlyBack ELF. Code/data bytes by ARM/Thumb mapping symbols,
per source module (function symbols attributed through the .o files). Prints a table + json."""
import sys,subprocess,re,collections,json,os
elf,objdir=sys.argv[1],sys.argv[2]
rs=subprocess.run(['llvm-readelf','-s','-W',elf],capture_output=True,text=True).stdout.splitlines()
secs={}
for l in subprocess.run(['llvm-readelf','-S','-W',elf],capture_output=True,text=True).stdout.splitlines():
    m=re.match(r'\s*\[\s*(\d+)\]\s+(\S+)\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)',l)
    if m: secs[int(m.group(1))]=(m.group(2),m.group(3),int(m.group(4),16),int(m.group(6),16))
mapsym=collections.defaultdict(list); funcs=[]
for l in rs:
    p=l.split()
    if len(p)<8 or not p[0].endswith(':'): continue
    try: ndx=int(p[6])
    except: continue
    a=int(p[1],16); nm=p[7]
    if re.match(r'\$[atd](\.|$)',nm): mapsym[ndx].append((a,nm[1]))
    elif p[3]=='FUNC': funcs.append((a,int(p[2]),nm,ndx))
# defining object for each function
owner={}
for f in sorted(os.listdir(objdir)):
    if not f.endswith('.o'): continue
    for l in subprocess.run(['llvm-nm','--defined-only',os.path.join(objdir,f)],capture_output=True,text=True).stdout.splitlines():
        p=l.split()
        if len(p)==3 and p[1] in 'tTwW': owner.setdefault(p[2],f.replace('.c.o','').replace('.s.o',''))
res=collections.defaultdict(lambda:collections.Counter())
totals=collections.Counter()
def mode_at(ndx,a):
    ms=sorted(mapsym[ndx]); k=None
    for x,m in ms:
        if x<=a: k=m
        else: break
    return k
# per-section ARM/Thumb/data bytes
for ndx,(name,typ,addr,size) in secs.items():
    if ndx not in mapsym: continue
    ms=sorted(mapsym[ndx])+[(addr+size,'e')]
    for (a,m),(b,_) in zip(ms,ms[1:]):
        totals[(name,m)]+=b-a
for k,v in sorted(totals.items()): print('%-10s %s %8d'%(k[0],{'a':'ARM','t':'Thumb','d':'data'}[k[1]],v))
# per module code bytes by function symbols
mod=collections.defaultdict(lambda:collections.Counter())
for a,sz,nm,ndx in funcs:
    m=mode_at(ndx,a); mod[owner.get(nm,'?')][('T' if m=='t' else 'A' if m=='a' else '?')]+=sz
print('%-14s %8s %8s'%('module','thumbB','armB'))
for k,v in sorted(mod.items(),key=lambda kv:-(kv[1]['T']+kv[1]['A'])): print('%-14s %8d %8d'%(k,v['T'],v['A']))
json.dump({'totals':{'%s/%s'%k:v for k,v in totals.items()},'mod':{k:dict(v) for k,v in mod.items()}},open(sys.argv[3] if len(sys.argv)>3 else '/dev/null','w'),indent=1)
