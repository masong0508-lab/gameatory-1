#!/usr/bin/env python3
"""scan_merged.py ROM IW OUT.pkl [--payback]: discovery run of disc.py/armdec on the merged Star-FlyBack ROM (or on plain Payback with --payback, same
heuristics, for a baseline).  Prints instruction counts by mode/span, undecodable, indirect sites, IWRAM calls out of SF code."""
import sys,os,pickle,collections,time
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if '--payback' not in sys.argv:
    os.environ.setdefault('SF_LEN','94e8c'); os.environ.setdefault('ROM_EXTRA','1b0000,244e8c')
import disc,prune
rom=open(sys.argv[1],'rb').read(); iw=open(sys.argv[2],'rb').read()
t0=time.time()
P=disc.discover(rom,iw,True,stubs=prune.stub_dict() if '--pruned' in sys.argv else {},templates=[],extra=[(0x100,prune.SWI_STUB)],seeds=[(0x100,'A')])
print('time %.1fs'%(time.time()-t0))
def span(a):
    if a>>24==3: return 'IWRAM(Payback img)'
    if disc.in_sf(a): return 'SF rom'
    if a>>24==8: return 'Payback rom'
    return 'other'
c=collections.Counter(); b=collections.Counter()
for a,i in P.ins.items():
    c[(span(a),i.mode)]+=1; b[(span(a),i.mode)]+=i.size
for k in sorted(c): print('%-20s %s insns %7d bytes %8d'%(k[0],k[1],c[k],b[k]))
print('total insns',len(P.ins),'bad',P.bad,'indirect sites',len(P.indirect),'entries',len(P.entries),'jt',len(P.jt))
ops=collections.Counter(i.op for i in P.ins.values()); print(dict(ops.most_common(30)))
print('SF->IWRAM calls',len(disc.HOTCALLS),'distinct targets',len({t for _,t,_ in disc.HOTCALLS}))
P.img=None; P.hotcalls=list(disc.HOTCALLS); pickle.dump(P,open(sys.argv[3],'wb'))
