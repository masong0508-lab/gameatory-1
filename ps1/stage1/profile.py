#!/usr/bin/env python3
"""Profile: ARM instructions executed per presentation step (DISPCNT write) on the original, translated MIPS instructions per step (from
lockstep's blockcnt.pkl), split by code category / function, and R3000 load estimate.   usage: profile.py ROM OUTDIR NSYNC PROGPKL"""
import sys,pickle,collections,bisect,struct
sys.path.insert(0,'.')
from gbaenv import *
rom=open(sys.argv[1],'rb').read(); OUT=sys.argv[2]; NS=int(sys.argv[3]); P=pickle.load(open(sys.argv[4],'rb'))
class SIo(Io):
    def __init__(s,h): super().__init__(); s.h=h; s.nd=0
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2:
            s.nd+=1
            if s.nd>=NS: s.h[0].emu_stop()
h=[None]; io=SIo(h); A=ArmSide(rom,io); h[0]=A.u
acnt=collections.Counter(); 
def blk(uc,a,sz,ud):
    th=uc.reg_read(UC_ARM_REG_CPSR)&0x20
    acnt[a]+=sz//(2 if th else 4)
A.u.hook_add(UC_HOOK_BLOCK,blk)
A.u.emu_start(0x08000000,0,count=4000000000)
ainsn=sum(acnt.values())
mc=pickle.load(open(OUT+'/blockcnt.pkl','rb'))
gmap={}
for l in open(OUT+'/payback_B.map'):
    a,hh=l.split(); gmap[int(a,16)]=int(hh,16)
hs=sorted(set(gmap.values())); inv={}
for g,hh in gmap.items(): inv.setdefault(hh,g)
funcs=sorted(a for a in (P.entries|P.callt|set(getattr(P,'orph',[]))) if a in P.ins)
def func_of(g): j=bisect.bisect_right(funcs,g)-1; return funcs[j] if j>=0 else 0
def cat(g):
    if 0x0806c294<=g<0x0806c660: return 'renderer: RAM-code template (mode-3 span loop)'
    if 0x0806c82c<=g<0x0806ca40: return 'renderer: driver F'
    if g>>24==3: return 'IWRAM routines'
    if g>=0x0807c000: return 'runtime lib (memcpy/div/call_via)'
    if g>>24==8: return 'ROM game/engine code'
    return 'other'
mi=collections.Counter(); mf=collections.Counter()
for hb,c in mc.items():
    j=bisect.bisect_right(hs,hb)-1
    g=inv.get(hs[j],0) if j>=0 else 0
    mi[cat(g)]+=c; mf[func_of(g)]+=c
tm=sum(mi.values())
ac=collections.Counter(); af=collections.Counter()
for a,c in acnt.items(): ac[cat(a&~1)]+=c; af[func_of(a&~1)]+=c
print('steps (DISPCNT writes)',NS,'ARM insns',ainsn,'per step %.0f'%(ainsn/NS),'| MIPS insns',tm,'per step %.0f'%(tm/NS),'| expansion %.2fx'%(tm/ainsn))
print('category            ARM/step   MIPS/step  share')
for k,v in mi.most_common(): print('%-52s %9.0f %9.0f %5.1f%%'%(k,ac[k]/NS,v/NS,100*v/tm))
print('top functions (MIPS insns/step, share, ARM/step):')
for f,v in mf.most_common(12): print(' %08x  %9.0f  %5.1f%%  %9.0f'%(f,v/NS,100*v/tm,af[f]/NS))
# R3000 estimate: CPI 1.0 ideal; 33.8688 MHz; GBA frame = 280896 cycles
mps=tm/NS
print('R3000 @33.8688MHz, CPI=1.0: %.2f ms per step (%.0f%% of a 60 Hz frame); CPI=1.5: %.2f ms'%(mps/33868.8,100*mps/33868.8/16.667,1.5*mps/33868.8))
