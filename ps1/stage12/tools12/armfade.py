#!/usr/bin/env python3
"""ANALYSIS: ARM unicorn with blits modelled, stubs 2,4,5 only; gfx_fade_flip (id1) and gfx_effect (id3) run for real; records PAL/DISPCNT around each call.
usage: armfade.py ROM NTICKS OUT.pkl"""
import sys,os,struct,pickle,json,time
sys.path.insert(0,'.'); sys.path.insert(0,'tools12')
from gbaenv import *
import prune, ppu_model
rom=open(sys.argv[1],'rb').read(); NT=int(sys.argv[2])
plan=json.load(open('../s10_boot/out/pad_boot.json'))['plan']
def padat(f):
    for a,b,m in plan:
        if a<=f<b: return 0x3ff&~m
    return 0x3ff
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0; s.logon=False
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=padat(s.nd)
        return super().read(off,size)
    def tick(s):
        s.nd+=1
        if s.nd%SNEV==0: snaps[s.nd]=dict(vr=bytes(A.u.mem_read(0x06000000,0x18000)),pal=bytes(A.u.mem_read(0x05000000,0x400)),oam=bytes(A.u.mem_read(0x07000000,0x400)),io=bytes(io.regs))
        if s.nd>=NT: A.u.emu_stop()
    def vblank(s): super().vblank(); s.tick()
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.tick()
calls=[]; snaps={}
SNEV=int(os.environ.get('SNEV','25'))
class Arm(ArmSide):
    def _stub(s,uc,addr,sz,sid):
        if sid in (2,4):
            r=[uc.reg_read(UC_ARM_REG_R0+k) for k in range(3)]
            vr=bytearray(uc.mem_read(0x06000000,0xa000*2)); b=ppu_model.Blit(rom,vr)
            disp=struct.unpack_from('<H',s.io.regs,0)[0]
            if sid==2: b.blit2(r[0],r[1],r[2],disp)
            else:
                ew=lambda o:struct.unpack('<h',bytes(uc.mem_read(0x02000000+o,2)))[0]
                b.blit4(r[0],r[1],r[2],disp,ew(0x1cea),ew(0x1cec),ew(0x1d00))
            uc.mem_write(0x06000000,bytes(vr))
        super()._stub(uc,addr,sz,sid)
real={0x0806c82c:1,0x080234be:3}
def entry(uc,addr,sz,ud):
    r=[uc.reg_read(UC_ARM_REG_R0+k) for k in range(4)]; lr=uc.reg_read(UC_ARM_REG_LR)
    rec=dict(id=real[addr],tick=io.nd,r=r,pal=bytes(uc.mem_read(0x05000000,0x400)),disp=struct.unpack_from('<H',io.regs,0)[0],
             lr=lr)
    calls.append(rec)
    h=[None]
    def ret(u,a,s,d):
        if 'pal2' in rec: return
        rec['pal2']=bytes(u.mem_read(0x05000000,0x400)); rec['disp2']=struct.unpack_from('<H',io.regs,0)[0]; rec['tick2']=io.nd
    A.u.hook_add(UC_HOOK_CODE,ret,None,lr&~1,lr&~1)
REAL=[int(x) for x in os.environ.get('REAL','1,3').split(',')]
stubs={a:i for i,(a,n) in prune.STUBS.items() if i in (1,2,3,4,5) and i not in REAL}
A=Arm.__new__(Arm); io=SIo(); Arm.__init__(A,rom,io,stubs=stubs)
for a in real: A.u.hook_add(UC_HOOK_CODE,entry,None,a,a)
t0=time.time()
try: A.u.emu_start(0x08000000,0,count=int(os.environ.get('MAXINS','4000000000')))
except Exception as e: print('exc',e)
print('ticks',io.nd,'calls',len(calls),round(time.time()-t0,1),'s')
pickle.dump(dict(calls=calls,snaps=snaps),open(sys.argv[3],'wb'))
