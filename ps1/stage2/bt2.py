import sys,os,collections
sys.path.insert(0,'.')
from gbaenv import *
import prune,cg
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
rom=open(SP+'/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
PAD=[0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81]
targets=[int(x,16) for x in sys.argv[1:]]
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=PAD[(s.nd//30)%6]
        return super().read(off,size)
    def vblank(s): super().vblank(); s.nd+=1
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.nd+=1
io=SIo(); A=ArmSide(rom,io,stubs=prune.stub_by_addr())
def isret(v):
    return v>>24==8 and v&1 and ((v-5) in cg.P.ins and cg.P.ins[v-5].op=='bl' or (v-3) in cg.P.ins and cg.P.ins[v-3].op=='bl')
seen=collections.Counter()
def hk(uc,a,sz,ud):
    seen[a]+=1
    if seen[a]>2: return
    sp=A.r(13); lr=A.r(14); st=[]
    if 0x03000000<=sp<0x03008000:
        for k in range(min(200,(0x03008000-sp)//4)):
            v=int.from_bytes(uc.mem_read(sp+4*k,4),'little')
            if isret(v): st.append(hex(v-1)+':'+hex(cg.fo(v-1)))
    print('hit %x nd=%d lr=%x r0-3=%s frames=%s'%(a,io.nd,lr,[hex(A.r(k)) for k in range(4)],st[:6]))
    if seen[a]==2: uc.emu_stop()
for t in targets: A.u.hook_add(UC_HOOK_CODE,hk,None,t,t)
A.u.emu_start(0x08000000,0,count=2000000000)
