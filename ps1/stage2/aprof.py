import sys,pickle,collections,bisect,struct
sys.path.insert(0,'.')
from gbaenv import *
import cg
rom=open(sys.argv[1],'rb').read(); NS=int(sys.argv[2]); KEYS=int(sys.argv[3]) if len(sys.argv)>3 else 0
class SIo(Io):
    def __init__(s,h): super().__init__(); s.h=h; s.nd=0; s.wl=[]
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2:
            s.nd+=1
            s.wl.append(s.h[0].reg_read(UC_ARM_REG_LR))
            if s.nd>=NS: s.h[0].emu_stop()
h=[None]; io=SIo(h); A=ArmSide(rom,io); h[0]=A.u
cnt=collections.Counter()
def blk(uc,a,sz,ud):
    th=uc.reg_read(UC_ARM_REG_CPSR)&0x20
    cnt[a&~1]+=sz//(2 if th else 4)
A.u.hook_add(UC_HOOK_BLOCK,blk)
A.u.emu_start(0x08000000,0,count=4000000000)
fc=collections.Counter()
for a,c in cnt.items(): fc[cg.fo(a) if a in cg.P.ins else 0]+=c
tot=sum(fc.values()); print('total',tot,'per step',tot/NS)
for f,c in fc.most_common(40):
    print('%08x %9.0f/step %5.1f%%  callers %s'%(f,c/NS,100*c/tot,[hex(x) for x in sorted(cg.callers[f])][:6]))
print('dispcnt-writer LRs',collections.Counter(hex(x) for x in io.wl).most_common(5))
