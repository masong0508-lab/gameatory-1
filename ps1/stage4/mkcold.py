#!/usr/bin/env python3
"""Cold (overlay) set selection.  usage: mkcold.py PROG.pkl RESIDENT.pkl OUT.pkl BUDGET_INSNS COV.pkl...
Order: (1) functions touched by the coverage runs but not hot, (2) call-graph neighbours (BFS from hot+touched, direct bl/b), until the instruction budget is used."""
import sys,pickle,collections,bisect
import disc,prune
P=pickle.load(open(sys.argv[1],'rb')); res,funcs=pickle.load(open(sys.argv[2],'rb')); BUD=int(sys.argv[4])
def fo(a): j=bisect.bisect_right(funcs,a)-1; return funcs[j]
fsz=collections.Counter(fo(a) for a in P.ins)
stubs={a for a,n in prune.STUBS.values()}
touched=collections.Counter()
for c in sys.argv[5:]:
    for a,sz in pickle.load(open(c,'rb')):
        a&=~1
        if a in P.ins: touched[fo(a)]+=1
calls=collections.defaultdict(set)
for a,i in P.ins.items():
    f=fo(a)
    if i.op in('bl','b') and i.target in P.ins and fo(i.target)!=f: calls[f].add(fo(i.target))
cold=[]; used=0; seen=set(res)|stubs
def add(f):
    global used
    if f in seen or f in stubs: return False
    if used+fsz[f]>BUD: return False
    seen.add(f); cold.append(f); used+=fsz[f]; return True
t=[f for f in touched if f not in res]
for f in sorted(t,key=lambda f:-touched[f]): add(f)
nt=len(cold)
front=list(res)+list(cold); 
while front and used<BUD:
    nxt=[]
    for f in front:
        for g in sorted(calls[f]):
            if add(g): nxt.append(g)
    front=nxt
print('touched-not-hot %d, cold %d functions %d insns (budget %d)'%(len(t),len(cold),used,BUD))
pickle.dump((set(cold),funcs),open(sys.argv[3],'wb'))
