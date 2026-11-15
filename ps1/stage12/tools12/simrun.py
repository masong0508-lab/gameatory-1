#!/usr/bin/env python3
"""ANALYSIS (test-only): run a PS1 exe in the unicorn MIPS sim with the stock pad plan inside; dump guest shadow state at given GBA frames and record EWRAM pages written.
usage: simrun.py EXE ISO ELF OUTPREFIX frames_csv total_frames"""
import sys,os,pickle,struct,time
sys.path.insert(0,'t')
from sim4 import *
exe,iso,elf,out=sys.argv[1:5]; FR=sorted(int(x) for x in sys.argv[5].split(',')); TOTAL=int(sys.argv[6])
s=Sim(exe,iso,elf); sym=s.sym; CY=sym['io_cyc']
ewp=set(); ewr=set()
def hw(uc,acc,addr,sz,val,ud): ewp.add((addr-0x1b0000)>>12)
s.u.hook_add(UC_HOOK_MEM_WRITE,hw,None,0x1b0000,0x1effff)
snaps={}; T0=time.time(); nx=[0]
def cb(s):
    f=s.r32(CY)//280896
    while nx[0]<len(FR) and f>=FR[nx[0]]:
        snaps[FR[nx[0]]]=dict(f=f,l0=s.rd(sym['pp_l0'],2*20*14),nl0=s.rd(sym['pp_nl0'],2),pimg=s.rd(sym['pp_img'],40*24),nimg=s.r32(sym['pp_nimg']),pdisp=s.r32(sym['pp_disp']),vr=s.rd(VRAM,0x18000),pal=s.rd(PAL,0x400),oam=s.rd(PAL+0x400,0x400),io=s.rd(sym['io'],0x400),ew=s.rd(EW,0x40000),n=s.r32(DL0) if 0 else 0)
        print('snap',FR[nx[0]],'at',f,'t %.0f'%(time.time()-T0),flush=True); nx[0]+=1
    return f>=TOTAL
DL0=0x8017c000
s.cb=cb; s.run(count=30000000000)
pickle.dump(dict(snaps=snaps,ewpages=sorted(ewp)),open(out+'.pkl','wb')); print('done',len(ewp),'ewram pages written')
