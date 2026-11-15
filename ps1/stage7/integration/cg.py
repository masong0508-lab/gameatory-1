import pickle,sys,bisect,collections
sys.path.insert(0,'.')
import disc
from armdec import *
P=pickle.load(open('out/prog.pkl','rb'))
funcs=sorted(a for a in (P.entries|P.callt|set(getattr(P,'orph',[]))|set(getattr(P,'dptr',[]))) if a in P.ins)
def fo(a): j=bisect.bisect_right(funcs,a)-1; return funcs[j]
callers=collections.defaultdict(set)   # func -> set of (callsite, callerfunc)
refs=collections.defaultdict(set)
for a,i in P.ins.items():
    if i.op in('bl','b') and i.target in P.ins:
        if i.op=='bl' or fo(i.target)!=fo(a) or i.target in funcs and i.cond==14: callers[i.target].add(fo(a))
if __name__=='__main__':
    for t in sys.argv[1:]:
        t=int(t,16); print(hex(t),'func',hex(fo(t)),'callers',[hex(x) for x in sorted(callers[fo(t)])])
