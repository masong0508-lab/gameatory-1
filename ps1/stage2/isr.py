import sys,collections,struct
sys.path.insert(0,'.')
from gbaenv import *
import cg
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
rom=open(SP+'/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
PAD=[0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81]
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=PAD[(s.nd//30)%6]
        return super().read(off,size)
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.nd+=1
io=SIo(); A=ArmSide(rom,io)
calls=[]
def h(uc,a,sz,ud):
    calls.append((a,uc.reg_read(UC_ARM_REG_LR)))
    if len(calls)>6: uc.emu_stop()
A.u.hook_add(UC_HOOK_CODE,h,None,0x100,0x100)
A.u.emu_start(0x08000000,0,count=300000000)
print('isr ptr',hex(struct.unpack('<I',bytes(A.u.mem_read(0x03007ffc,4)))[0]),'calls',[hex(x) for x,_ in calls])
