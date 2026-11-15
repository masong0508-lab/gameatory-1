import sys,os
sys.path.insert(0,'.')
from gbaenv import *
import prune
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
rom=open(SP+'/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
PAD=[0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81]
USE=os.environ.get('STUBS','')
stubs={prune.STUBS[int(i)][0]:int(i) for i in USE.split(',') if i}
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=PAD[(s.nd//30)%6]
        return super().read(off,size)
    def vblank(s): super().vblank(); s.nd+=1
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.nd+=1
io=SIo(); A=ArmSide(rom,io,stubs=stubs)
n=[0]
def h(uc,a,sz,ud):
    n[0]+=1
    if n[0]<=int(sys.argv[1]):
        p=A.r(0); 
        try: s=bytes(uc.mem_read(p,24))
        except: s=b'?'
        print('str call',n[0],'nd',io.nd,'r0=%x r1=%x r2=%x r3=%x'%(A.r(0),A.r(1),A.r(2),A.r(3)),s[:24])
    if n[0]>int(sys.argv[1]): uc.emu_stop()
A.u.hook_add(UC_HOOK_CODE,h,None,0x8029198,0x8029198)
A.u.emu_start(0x08000000,0,count=300000000)
