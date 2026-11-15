import sys,collections
sys.path.insert(0,'.')
from gbaenv import *
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
rom=open(SP+'/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0
    def read(s,off,size):
        if off in(0x130,0x131):
            ph=(s.nd//30)%6
            s.keys=[0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81][ph]
        return super().read(off,size)
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.nd+=1
io=SIo(); A=ArmSide(rom,io)
A.u.emu_start(0x08000000,0,count=int(sys.argv[1]))
print('nd',io.nd,'swis',A.nswi,hex(A.u.reg_read(UC_ARM_REG_PC)))
cnt=collections.Counter()
def h(uc,a,sz,ud): cnt[a]+=1
A.u.hook_add(UC_HOOK_CODE,h)
A.u.emu_start(A.u.reg_read(UC_ARM_REG_PC)|(1 if A.u.reg_read(UC_ARM_REG_CPSR)&0x20 else 0),0,count=20000)
print(sorted((hex(a),c) for a,c in cnt.most_common(30)))
print('regs',[hex(A.r(k)) for k in range(15)])
print('reads',io.nread)
