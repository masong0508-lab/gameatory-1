#!/usr/bin/env python3
"""ARM-side exploration with pruned stubs: scripted pad, screenshots, block coverage, per-tick instruction counts.
usage: explore.py TAG NTICKS 'PAD list' shots(comma) [maxins]"""
import sys,os,struct,pickle,collections,time
sys.path.insert(0,'.')
from gbaenv import *
import prune
from PIL import Image
SP=None
rom=open(os.environ['ROM'],'rb').read()
TAG=sys.argv[1]; NT=int(sys.argv[2]); PAD=eval(sys.argv[3]); at=[int(x) for x in sys.argv[4].split(',') if x]
MAXI=int(sys.argv[5]) if len(sys.argv)>5 else 3000000000
PADSTEP=int(os.environ.get('PADSTEP','30'))
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0; s.nvb=0; s.hist=[]
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=PAD[(s.nd//PADSTEP)%len(PAD)]
        return super().read(off,size)
    def tick(s):
        s.nd+=1
        if s.nd in at: shot(s.nd)
        if s.nd>=NT: A.u.emu_stop()
    def vblank(s): super().vblank(); s.tick()
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.tick()
io=SIo(); A=ArmSide(rom,io,stubs=prune.stub_by_addr())
def shot(n):
    dc=struct.unpack_from('<H',io.regs,0)[0]; mode=dc&7
    pal=A.ram('PAL'); vram=A.ram('VRAM')
    def c(v): return ((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31)
    img=Image.new('RGB',(240,160))
    if mode==4:
        base=0xa000 if dc&0x10 else 0
        for y in range(160):
            for x in range(240): img.putpixel((x,y),c(struct.unpack_from('<H',pal,vram[base+y*240+x]*2)[0]))
    elif mode==3:
        for y in range(160):
            for x in range(240): img.putpixel((x,y),c(struct.unpack_from('<H',vram,(y*240+x)*2)[0]))
    img.save('out/ex_%s_%05d_m%d.png'%(TAG,n,mode)); print('shot',n,'mode',mode,hex(dc),'dl',len(A.dl),flush=True)
cov=set()
def blk(uc,a,sz,ud): cov.add((a,sz))
A.u.hook_add(UC_HOOK_BLOCK,blk)
t0=time.time()
try: A.u.emu_start(0x08000000,0,count=MAXI)
except Exception as e: print('exc',e,hex(A.u.reg_read(UC_ARM_REG_PC)),'lr',hex(A.u.reg_read(UC_ARM_REG_LR)))
print('end tick',io.nd,'swis',A.nswi,'dl',len(A.dl),'demand',len(A.demand),'time',round(time.time()-t0,1))
print('dl hist',collections.Counter(d[0] for d in A.dl))
pickle.dump(cov,open('out/cov_%s.pkl'%TAG,'wb'))
print('demand addrs',[hex(x) for x in A.demand[:10]])
