#!/usr/bin/env python3
"""trsize.py ROM IW PKL TAG : run t2m's Tr (analysis + emission) on the discovered program and report MIPS words by region (no link: a monolithic link
overflows the +-128 KiB branch range, the production pipeline partitions into hot blob + cold overlay groups), plus the translator's own counters."""
import sys,os,pickle,collections,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import t2m,disc,prune,mips as M
rom=open(sys.argv[1],'rb').read(); iw=open(sys.argv[2],'rb').read()
P=pickle.load(open(sys.argv[3],'rb')); P.img=disc.Img(rom,iw,[(0x100,prune.SWI_STUB)])
tag=sys.argv[4]
sf_lo,sf_hi=0x081b0000,0x081b0000+0x94e8c
t0=time.time(); T=t2m.Tr(P,t2m.Cfg('P'),False); T.run(); print('translate %.1fs'%(time.time()-t0))
it,nh=M.hazard_pass(T.A.it)
cur=None; w=collections.Counter(); n_in=collections.Counter()
def reg(a):
    if a is None: return 'prelude/runtime'
    if a>>24==3: return 'IWRAM ARM (Payback image)'
    if sf_lo<=a<sf_hi: return 'SF rom (Thumb)'
    if a>>24==8: return 'Payback rom (Thumb)'
    return 'other'
for x in it:
    if isinstance(x,tuple) and x[0]=='L':
        l=x[1]
        if isinstance(l,tuple) and l[0]=='g' and l[1] in P.ins: cur=l[1]
        continue
    w[reg(cur)]+=1
for a,i in P.ins.items(): n_in[reg(a)]+=1
tot=0
for k in sorted(w): print('%-28s guest insns %7d  MIPS words %8d  (%.2fx)  %7.1f KiB'%(k,n_in[k],w[k],w[k]/max(1,n_in[k]),w[k]*4/1024))
print('total words',sum(w.values()),'KiB',sum(w.values())*4/1024,'hazard nops added',nh)
print('stats',dict(T.st)); print('unsafe',dict(T.unsafe))
ops=collections.Counter()
for a,i in P.ins.items(): ops[(reg(a),i.op)]+=1
print('unsupported/undef/stub ops',{k:v for k,v in ops.items() if k[1] in('undef','stub','swi','msr','mrs','swp','mull')})
