import sys,collections,struct
sys.path.insert(0,'.')
from gbaenv import *
import cg
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
rom=open(SP+'/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
import os
PAD=eval(os.environ.get('PAD','[0x3ff]'))
LO,HI=int(sys.argv[1],16),int(sys.argv[2],16); LIM=int(sys.argv[3])
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=PAD[(s.nd//30)%len(PAD)]
        return super().read(off,size)
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.nd+=1
    def vblank(s): super().vblank(); s.nd+=1
io=SIo(); A=ArmSide(rom,io)
seen=collections.Counter()
def hk(uc,a,sz,ud):
    seen[a]+=1
    if len(seen)<=3 and seen[a]==1 or (a in(0x3001cec,0x3005eb8) and seen[a]<=2):
        print('hit %x nd=%d lr=%x sp=%x r0-3=%s'%(a,io.nd,A.r(14),A.r(13),[hex(A.r(k)) for k in range(4)]))
A.u.hook_add(UC_HOOK_CODE,hk,None,LO,HI-1)
try: A.u.emu_start(0x08000000,0,count=LIM)
except Exception as e: print(e)
print('nd',io.nd,hex(A.u.reg_read(UC_ARM_REG_PC)),len(seen))
