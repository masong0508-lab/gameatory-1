import sys,os,pickle,bisect,collections,subprocess,re
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import elfsyms
elf=sys.argv[1]; P=pickle.load(open(sys.argv[2],'rb'))
fs,secs,ms=elfsyms.load(elf)
base,size=secs['.text']
cov=bytearray(size)
for a,i in P.ins.items():
    if base<=a<base+size:
        for k in range(i.size): cov[a-base+k]=1
# mapping symbols of .text
m=sorted(ms['.text']); m.append((base+size,'e'))
gap=[]; 
for (a,t),(b,_) in zip(m,m[1:]):
    if t in 'at':
        s=None
        for x in range(a,b):
            if not cov[x-base] and s is None: s=x
            if (cov[x-base] or x==b-1) and s is not None:
                e=x if cov[x-base] else x+1; gap.append((s,e-s,t)); s=None
print('code bytes (mapping) %d, uncovered %d in %d gaps'%(sum(b-a for (a,t),(b,_) in zip(m,m[1:]) if t in 'at'),sum(g[1] for g in gap),len(gap)))
fa=sorted((f[0],f[2],f[1]) for f in fs if f[4]=='.text'); fk=[f[0] for f in fa]
sizes=collections.Counter(g[1] for g in gap); print('gap size histogram',sizes.most_common(8))
big=sorted(gap,key=lambda g:-g[1])[:25]
for s,n,t in big:
    k=bisect.bisect_right(fk,s)-1; print('  %08x +%5d %s  after %s (+%d)'%(s,n,t,fa[k][1] if k>=0 else '?',s-fa[k][0] if k>=0 else 0))
