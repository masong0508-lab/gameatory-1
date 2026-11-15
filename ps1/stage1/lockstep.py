#!/usr/bin/env python3
"""Whole-boot lockstep: original ARM code on unicorn-ARM vs translated MIPS on unicorn-MIPS, same GBA stub (gbaenv.Io).
Sync points = every DISPCNT write; compared: full I/O write sequence, EWRAM/IWRAM/PAL/VRAM/OAM images (host pointers normalised).
usage: lockstep.py ROM OUTDIR NSYNC [maxins]"""
import sys,struct,time,pickle,collections
sys.path.insert(0,'.')
import numpy as np
from gbaenv import *
import t2m
rom=open(sys.argv[1],'rb').read(); OUT=sys.argv[2]; NSYNC=int(sys.argv[3])
cfg=t2m.Cfg('B')
blob=open(OUT+'/payback_B.bin','rb').read(); meta=pickle.load(open(OUT+'/meta_B.pkl','rb'))
gmap={}
for l in open(OUT+'/payback_B.map'):
    a,h=l.split(); gmap[int(a,16)]=int(h,16)
entries=set(meta['entries'])
inv={h:g for g,h in gmap.items()}
invs=collections.defaultdict(set)
for g_,h_ in gmap.items(): invs[h_].add(g_)
KEYS=int(__import__('os').environ.get('KEYS','0'))
EVERY=int(sys.argv[4]) if len(sys.argv)>4 else 1
class SyncIo(Io):
    def __init__(s,side): super().__init__(); s.side=side; s.ndisp=0; s.snaps={}; s.ionum={}
    def read(s,off,size):
        if off in(0x130,0x131) and KEYS:
            ph=(s.ndisp//30)%6      # scripted pad: idle, START, idle, A, idle, DOWN+A
            s.keys=[0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81][ph]
        return super().read(off,size)
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2:
            s.ndisp+=1
            if s.ndisp%EVERY==0 or s.ndisp<=4:
                s.snaps[s.ndisp]=s.side.snap(); s.ionum[s.ndisp]=len(s.log)
            if s.ndisp>=NSYNC: s.side.u.emu_stop()
class Arm2(ArmSide):
    def snap(s): return {nm:np.frombuffer(s.ram(nm),dtype='<u4').copy() for nm in('EWRAM','IWRAM','PAL','VRAM','OAM')}
class Mips2(MipsSide):
    def snap(s):
        d={}
        for nm in('EWRAM','IWRAM'): b=s.ram(nm); d[nm]=norm_words(cfg,b,0,entries)
        for nm in('PAL','VRAM','OAM'): d[nm]=np.frombuffer(s.ram(nm),dtype='<u4').copy()
        return d
A=Arm2.__new__(Arm2); ioa=SyncIo(A); Arm2.__init__(A,rom,ioa)
M=Mips2.__new__(Mips2); iom=SyncIo(M); Mips2.__init__(M,rom,cfg,blob,meta['rt'],entries) if False else Mips2.__init__(M,rom,iom,cfg,blob,meta['rt'],entries)
cnt=collections.Counter()
def blk(uc,a,sz,ud): cnt[a]+=sz//4
M.u.hook_add(UC_HOOK_BLOCK,blk)
MAXA=int(sys.argv[5]) if len(sys.argv)>5 else 3000000000
t0=time.time()
try: A.u.emu_start(0x08000000,0,count=MAXA)
except Exception as e: print('ARM exc',e)
print('ARM done: dispcnt writes',ioa.ndisp,'io',len(ioa.log),round(time.time()-t0,1),'s')
M.u.reg_write(UC_MIPS_REG_PC,gmap[0x08000000])
try: M.u.emu_start(gmap[0x08000000],0,count=MAXA*3)
except Exception as e: print('MIPS exc',e,hex(M.u.reg_read(UC_MIPS_REG_PC)),'ra',hex(M.r(31)),'r25',hex(M.r(25)),[hex(x) for x in M.gregs()])
print('MIPS done: dispcnt writes',iom.ndisp,'io',len(iom.log),round(time.time()-t0,1),'s')
la,lm=ioa.log,iom.log
n=min(len(la),len(lm)); bad=next((i for i in range(n) if la[i]!=lm[i]),None)
print('io writes arm %d mips %d first mismatch %s'%(len(la),len(lm),None if bad is None else (bad,la[bad],lm[bad])))
tot=collections.Counter(); shown=0
for k in sorted(set(ioa.snaps)&set(iom.snaps)):
    sa,sm=ioa.snaps[k],iom.snaps[k]; msg=''
    for nm in sa:
        a,m=sa[nm],sm[nm]
        d=np.nonzero(a!=m)[0]
        d=[x for x in d if (int(a[x])&~1) not in invs.get(int(m[x]),())]
        tot[nm]+=len(d)
        if d: msg+='  %s:%d first@%x a=%08x m=%08x'%(nm,len(d),4*d[0],a[d[0]],m[d[0]])
    if msg and shown<12: print('sync',k,msg); shown+=1
print('snapshots compared',len(set(ioa.snaps)&set(iom.snaps)),'word diffs',dict(tot),'mips instrs',sum(cnt.values()))
pickle.dump(cnt,open(OUT+'/blockcnt.pkl','wb'))
print('mips pc',hex(M.u.reg_read(UC_MIPS_REG_PC)),'guest',hex(inv.get(M.u.reg_read(UC_MIPS_REG_PC),0)))
import bisect
gs=sorted(inv.items())
for a,c in cnt.most_common(8):
    j=bisect.bisect_right([h for h,g in gs],a)-1; print(hex(a),c,'guest~',hex(gs[j][1]) if j>=0 else None)
print('ARM log tail',la[len(lm)-3:len(lm)+3],'mips tail',lm[-3:])
