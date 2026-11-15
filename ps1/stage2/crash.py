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
    def vblank(s): super().vblank(); s.nd+=1
io=SIo(); A=ArmSide(rom,io)
ring=[]
def blk(uc,a,sz,ud):
    ring.append((a,uc.reg_read(UC_ARM_REG_LR)))
    if len(ring)>40: ring.pop(0)
A.u.hook_add(UC_HOOK_BLOCK,blk)
try: A.u.emu_start(0x08000000,0,count=900000000)
except Exception as e: print(e)
print([(hex(a),hex(l)) for a,l in ring]); print('pc',hex(A.u.reg_read(UC_ARM_REG_PC)),'regs',[hex(A.r(k)) for k in range(15)],'nd',io.nd)
sp=A.r(13); st=[]
for k in range(min(300,(0x03008000-sp)//4)):
    v=int.from_bytes(A.u.mem_read(sp+4*k,4),'little')
    if v>>24==8 and v&1 and ((v-5) in cg.P.ins and cg.P.ins[v-5].op=='bl' or (v-3) in cg.P.ins and cg.P.ins[v-3].op=='bl'): st.append((hex(v),hex(cg.fo(v-1))))
print(st)
