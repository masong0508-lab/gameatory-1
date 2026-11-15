import sys,os,collections
sys.path.insert(0,'.')
from gbaenv import *
import prune,cg
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
rom=open(SP+'/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
PAD=eval(os.environ.get('PAD','[0x3ff]')); N=int(sys.argv[1])
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=PAD[(s.nd//30)%len(PAD)]
        return super().read(off,size)
    def vblank(s): super().vblank(); s.nd+=1
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.nd+=1
io=SIo(); A=ArmSide(rom,io,stubs=prune.stub_by_addr())
A.u.emu_start(0x08000000,0,count=N)
print('nd',io.nd,'swis',A.nswi,'dl',len(A.dl),'pc',hex(A.u.reg_read(UC_ARM_REG_PC)),[hex(A.r(k)) for k in range(15)])
cnt=collections.Counter()
def h(uc,a,sz,ud): cnt[a]+=1
A.u.hook_add(UC_HOOK_CODE,h)
pc=A.u.reg_read(UC_ARM_REG_PC)|(1 if A.u.reg_read(UC_ARM_REG_CPSR)&0x20 else 0)
A.u.emu_start(pc,0,count=3000)
print([(hex(a),c) for a,c in cnt.most_common(12)])
print('funcs',collections.Counter(hex(cg.fo(a)) if a in cg.P.ins else hex(a) for a in cnt).most_common(5))
print('reads',io.nread,'ewram[0x2000000..]',[hex(int.from_bytes(A.u.mem_read(0x03007ff8,4),'little'))])
