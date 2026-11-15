#!/usr/bin/env python3
"""Resident-set selection: functions touched in the traced runs (block coverage from explore.py) + their direct-call closure; everything else is
not translated (calls land in RT_MISS).  usage: mkresident.py PROG.pkl OUT.pkl COV.pkl..."""
import sys,pickle,collections,bisect
import disc
P=pickle.load(open(sys.argv[1],'rb'))
funcs=sorted(a for a in (P.entries|P.callt|set(getattr(P,'orph',[]))|set(getattr(P,'dptr',[]))) if a in P.ins)
def fo(a): j=bisect.bisect_right(funcs,a)-1; return funcs[j]
touched=set()
for c in sys.argv[3:]:
    for a,sz in pickle.load(open(c,'rb')):
        a&=~1
        if a in P.ins: touched.add(fo(a))
import prune
touched|={0x08000000,0x100}|{a for a,n in prune.STUBS.values()}
calls=collections.defaultdict(set)
for a,i in P.ins.items():
    f=fo(a)
    if i.op in('bl','b') and i.target in P.ins and fo(i.target)!=f: calls[f].add(fo(i.target))
DEPTH=int(__import__('os').environ.get('DEPTH','1'))
res=set(touched); front=[(f,0) for f in touched]
stubs={a for a,n in prune.STUBS.values()}
while front:
    f,d=front.pop()
    if f in stubs or d>=DEPTH: continue
    for g in calls[f]:
        if g not in res: res.add(g); front.append((g,d+1))
fsz=collections.Counter(fo(a) for a in P.ins)
print('touched',len(touched),'resident',len(res),'insns',sum(fsz[f] for f in res),'of',len(P.ins))
pickle.dump((res,funcs),open(sys.argv[2],'wb'))
