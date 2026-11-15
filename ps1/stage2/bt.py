import sys,collections
sys.path.insert(0,'.')
from gbaenv import *
import cg
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
rom=open(SP+'/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
NS=int(sys.argv[1]); targets=[int(x,16) for x in sys.argv[2:]]
class SIo(Io):
    def __init__(s,h): super().__init__(); s.h=h; s.nd=0
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2:
            s.nd+=1
            if s.nd>=NS: s.h[0].emu_stop()
h=[None]; io=SIo(h); A=ArmSide(rom,io); h[0]=A.u
def isret(v):
    if v>>24!=8 or not v&1: return False
    a=v-1-4
    return (v-5) in cg.P.ins and cg.P.ins[v-5].op=='bl' or (v-3) in cg.P.ins and cg.P.ins[v-3].op=='bl'
seen=collections.Counter()
def hk(uc,a,sz,ud):
    seen[a]+=1
    if seen[a]>2: return
    sp=uc.reg_read(UC_ARM_REG_SP); lr=uc.reg_read(UC_ARM_REG_LR)
    st=[]
    for k in range(0,min(160,(0x03008000-sp)//4)):
        v=int.from_bytes(uc.mem_read(sp+4*k,4),'little')
        if isret(v): st.append(hex(cg.fo(v-1)))
    print('at %x (call %d) lr=%x r0=%x r1=%x frames:'%(a,seen[a],lr,uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)),st[:8])
for t in targets: A.u.hook_add(UC_HOOK_CODE,hk,None,t,t)
A.u.emu_start(0x08000000,0,count=4000000000)
