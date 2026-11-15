#!/usr/bin/env python3
"""Store-trace bisect: compare the sequence of stores to RAM regions (EWRAM/IWRAM/PAL/VRAM/OAM) on both sides, report first divergence with guest pc.
usage: wtrace.py ROM OUTDIR NSYNC REGION"""
import sys,pickle,bisect
sys.path.insert(0,'.')
from gbaenv import *
import t2m
rom=open(sys.argv[1],'rb').read(); OUT=sys.argv[2]; NS=int(sys.argv[3]); REG=sys.argv[4]
cfg=t2m.Cfg('B'); blob=open(OUT+'/payback_B.bin','rb').read(); meta=pickle.load(open(OUT+'/meta_B.pkl','rb'))
gmap={}
for l in open(OUT+'/payback_B.map'):
    a,h=l.split(); gmap[int(a,16)]=int(h,16)
inv={h:g for g,h in gmap.items()}; hs=sorted(inv)
entries=set(meta['entries'])
gb={n:(b,sz) for n,b,sz in REGIONS}[REG]
class SIo(Io):
    def __init__(s,u): super().__init__(); s.u=u; s.nd=0
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2:
            s.nd+=1
            if s.nd>=NS: s.u[0].emu_stop()
ua=[None]; um=[None]
ioa=SIo(ua); iom=SIo(um)
A=ArmSide(rom,ioa); ua[0]=A.u
M=MipsSide(rom,iom,cfg,blob,meta['rt'],entries); um[0]=M.u
ta=[]; tm=[]
def wa(uc,acc,addr,sz,val,ud): ta.append((addr-gb[0],sz,val&((1<<8*sz)-1),uc.reg_read(UC_ARM_REG_PC)))
A.u.hook_add(UC_HOOK_MEM_WRITE,wa,None,gb[0],gb[0]+gb[1]-1)
h0=cfg.host(gb[0])&0x1fffffff
def wm(uc,acc,addr,sz,val,ud):
    pc=uc.reg_read(UC_MIPS_REG_PC); j=bisect.bisect_right(hs,pc)-1
    tm.append((addr-h0,sz,val&((1<<8*sz)-1),inv[hs[j]]))
M.u.hook_add(UC_HOOK_MEM_WRITE,wm,None,h0,h0+gb[1]-1)
A.u.emu_start(0x08000000,0,count=50000000)
M.u.emu_start(gmap[0x08000000],0,count=200000000)
print('stores arm %d mips %d'%(len(ta),len(tm)))
def key(t): return t[:2]
# the MIPS side may write host pointers as values; compare address/size only first, then value
n=min(len(ta),len(tm))
for i in range(n):
    if ta[i][:2]!=tm[i][:2] or (ta[i][2]!=tm[i][2] and not (tm[i][2]>>24>=0x80)):
        print('first divergence at store',i,'arm',[hex(x) for x in ta[i]],'mips',[hex(x) for x in tm[i]])
        for k in range(max(0,i-3),min(n,i+4)): print('  ',k,[hex(x) for x in ta[k]],[hex(x) for x in tm[k]])
        break
else: print('no divergence in first',n)
