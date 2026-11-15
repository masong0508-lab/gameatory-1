import sys,struct
sys.path.insert(0,'.')
from gbaenv import *
from PIL import Image
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
rom=open(SP+'/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
at=[int(x) for x in sys.argv[2].split(',')]; KEYS=int(sys.argv[1])
import os
PAD=eval(os.environ.get('PAD','[0x3ff]'))
class SIo(Io):
    def __init__(s,h): super().__init__(); s.h=h; s.nd=0; s.A=None
    def read(s,off,size):
        if off in(0x130,0x131) and KEYS:
            ph=(s.nd//30)%len(PAD)
            s.keys=PAD[ph]
        return super().read(off,size)
    def tick(s):
        s.nd+=1
        if s.nd in at: shot(s.nd)
        if s.nd>=max(at): s.h[0].emu_stop()
    def vblank(s):
        super().vblank(); s.tick()
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.tick()
h=[None]; io=SIo(h); A=ArmSide(rom,io); h[0]=A.u
def shot(n):
    dc=struct.unpack_from('<H',io.regs,0)[0]; mode=dc&7
    pal=A.ram('PAL'); vram=A.ram('VRAM')
    def c(v): return ((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31)
    img=Image.new('RGB',(240,160))
    if mode==3:
        for y in range(160):
            for x in range(240): img.putpixel((x,y),c(struct.unpack_from('<H',vram,(y*240+x)*2)[0]))
    elif mode==4:
        base=0xa000 if dc&0x10 else 0
        for y in range(160):
            for x in range(240): img.putpixel((x,y),c(struct.unpack_from('<H',pal,vram[base+y*240+x]*2)[0]))
    elif mode==5:
        base=0xa000 if dc&0x10 else 0
        for y in range(128):
            for x in range(160): img.putpixel((x,y),c(struct.unpack_from('<H',vram,base+(y*160+x)*2)[0]))
    img.save('out/shot_%s_%04d_m%d.png'%(sys.argv[3],n,mode)); print(n,'mode',mode,hex(dc))
def um(uc,acc,addr,sz,val,ud): print('unmapped',acc,hex(addr),sz,hex(val),'pc',hex(uc.reg_read(UC_ARM_REG_PC))); return False
try: A.u.emu_start(0x08000000,0,count=4000000000)
finally: print('end pc',hex(A.u.reg_read(UC_ARM_REG_PC)),'swis',A.nswi,'nd',io.nd)
try: pass
except Exception as e:
    pc=A.u.reg_read(UC_ARM_REG_PC); print('exc',e,hex(pc),'cpsr',hex(A.u.reg_read(UC_ARM_REG_CPSR)),'lr',hex(A.u.reg_read(UC_ARM_REG_LR)))
    print(getattr(io,'eelog',None))
