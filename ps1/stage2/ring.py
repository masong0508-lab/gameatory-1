import sys,os,collections
sys.path.insert(0,'.')
exec(open('bt2.py').read().split("targets=")[0])
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
LO,HI=int(sys.argv[1],16),int(sys.argv[2],16); ND=int(sys.argv[3])
ring=[]; found=[False]
def blk(uc,a,sz,ud):
    if found[0]: return
    ring.append((a,A.r(14)))
    if len(ring)>25: ring.pop(0)
    if io.nd>=ND and LO<=a<HI:
        found[0]=True
        print([(hex(x),hex(l),hex(cg.fo(x&~1)) if (x&~1) in cg.P.ins else '') for x,l in ring]); uc.emu_stop()
A.u.hook_add(UC_HOOK_BLOCK,blk)
A.u.emu_start(0x08000000,0,count=2000000000)
