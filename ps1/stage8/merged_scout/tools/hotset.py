#!/usr/bin/env python3
"""hotset.py : from the per-scene instruction histograms (gbaprof.py) estimate the size of the HOT resident set: the functions that carry 90 / 99 % of the guest
instructions executed in each scene, and their static size in guest instructions (functions: ELF symbols for Stunt Fox, discovered entries for Payback)."""
import sys,os,pickle,bisect,collections
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); sys.path.insert(0,os.path.join(HERE,'..'))
import elfsyms,numpy as np
elf,progp,binsp=sys.argv[1:4]
P=pickle.load(open(progp,'rb'))
fs,secs,_=elfsyms.load(elf); fs=sorted(fs); fa=[f[0] for f in fs]
pb=pickle.load(open(os.path.join(HERE,'..','out','prog_pb.pkl'),'rb')); pe=sorted(a for a in pb.entries if a>>24==8 and a<0x081b0000)
SB=pickle.load(open(binsp,'rb'))
def fn(pc):
    if pc>>24==3:
        for hn,(ha,hs) in secs.items():
            if hn.startswith('.hot') and ha<=pc<ha+hs:
                k=bisect.bisect_right(fa,pc)-1; return ('sfhot',fs[k][0])
        return ('pbiw',pc&~0xff)
    if 0x081b0000<=pc<0x08244e8c:
        k=bisect.bisect_right(fa,pc)-1; return ('sf',fs[k][0])
    k=bisect.bisect_right(pe,pc)-1; return ('pb',pe[k])
# static size per function (guest insns) from the clean program
size=collections.Counter()
for a,i in P.ins.items():
    if a>>24==3: size[('pbiw',a&~0xff)]+=1
    elif 0x081b0000<=a<0x08244e8c:
        k=bisect.bisect_right(fa,a)-1; size[('sf',fs[k][0])]+=1
    elif a>>24==8:
        k=bisect.bisect_right(pe,a)-1; size[('pb',pe[k])]+=1
# hot-section code (SF IW) from ARM sections: bytes/4
for hn,(ha,hs) in secs.items():
    if hn.startswith('.hot'):
        for f in fs:
            if f[4]==hn: size[('sfhot',f[0])]=max(size[('sfhot',f[0])],f[1]//4)
allhot=collections.Counter(); 
for sc,(nz,v,fr) in SB.items():
    c=collections.Counter()
    for i,n in zip(nz,v):
        i=int(i)
        pc=0x08000000+(i<<4) if i<0x200000 else 0x03000000+((i-0x200000)<<2) if i<0x202000 else 0
        if pc: c[fn(pc)]+=int(n)
    tot=sum(c.values()); acc=0; sel={}; 
    ranked=c.most_common()
    out=[]
    for thr in (0.90,0.99):
        acc=0; ins=0; nf=0
        for f,n in ranked:
            acc+=n; ins+=size[f]; nf+=1
            if acc>=thr*tot: break
        out.append((thr,nf,ins))
    print('%-14s funcs for 90%%: %4d (%6d static insns)   for 99%%: %4d (%6d insns)'%(sc,out[0][1],out[0][2],out[1][1],out[1][2]))
    for f,n in ranked: allhot[f]+=n
# union of the 99% functions over scenes
sel=set()
for sc,(nz,v,fr) in SB.items():
    c=collections.Counter()
    for i,n in zip(nz,v):
        i=int(i); pc=0x08000000+(i<<4) if i<0x200000 else 0x03000000+((i-0x200000)<<2) if i<0x202000 else 0
        if pc: c[fn(pc)]+=int(n)
    tot=sum(c.values()); acc=0
    for f,n in c.most_common():
        sel.add(f); acc+=n
        if acc>=0.99*tot: break
by=collections.Counter()
for f in sel: by[f[0]]+=size[f]
print('union of 99%% sets over the scenes: %d functions, static insns by kind %s, total %d'%(len(sel),dict(by),sum(by.values())))
