#!/usr/bin/env python3
"""ANALYSIS: stubbed ARM unicorn + the Python PPU model applied inside the stub hook; snapshots page/PAL/OAM at ticks.  usage: armppu.py ROM NTICKS OUT.pkl snapticks [padmode]"""
import sys,os,struct,pickle,json,time
sys.path.insert(0,'.'); sys.path.insert(0,'tools12')
import numpy as np
from gbaenv import *
import prune, ppu_model
rom=open(sys.argv[1],'rb').read(); NT=int(sys.argv[2]); SNAPS=set(int(x) for x in sys.argv[4].split(',')) if len(sys.argv)>4 and sys.argv[4] else set()
plan=json.load(open('../s10_boot/out/pad_boot.json'))['plan']
SEQ=[1,1,1,1,1,1,1,1,128,128,1,1,1,1]
ST=dict(i=0,last=None,stable=0,hold=0,cur=0)
STAB=int(os.environ.get('STAB','25'))
TP=[tuple(int(y) for y in x.split(':')) for x in os.environ.get('TPLAN','').split(',') if x]
def adapt(tick):
    if TP:
        for t,k in TP:
            if t<=tick<t+6: return 0x3ff&~k
        return 0x3ff

    disp=struct.unpack_from('<H',io.regs,0)[0]
    off=0 if disp&0x10 else 0xa000
    h=hash(bytes(A.u.mem_read(0x06000000,240*160)))+hash(bytes(A.u.mem_read(0x0600a000,240*160)))
    if ST['hold']>0: ST['hold']-=1; 
    if ST['hold']==0: ST['cur']=0
    hist=ST.setdefault('hist',[]); hist.append(h); del hist[:-12]
    ST['stable']=ST['stable']+1 if len(set(hist))<=4 else 0
    if ST['hold']==0 and ST['stable']>=STAB and ST['i']<len(SEQ):
        ST['cur']=SEQ[ST['i']]; ST['i']+=1; ST['hold']=6; ST['stable']=0
    return 0x3ff&~ST['cur']
def padat(f):
    for a,b,m in plan:
        if a<=f<b: return 0x3ff&~m
    return 0x3ff
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0; s.logon=False
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=ST_KEYS[0]
        return super().read(off,size)
    def tick(s):
        s.nd+=1
        ST_KEYS[0]=adapt(s.nd)
        if s.nd in SNAPS or (SNAPS==set() and 0): snap()
        if s.nd>=NT: A.u.emu_stop()
    def vblank(s): super().vblank(); s.tick()
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.tick()
snaps={}
ST_KEYS=[0x3ff]
KB=int(os.environ.get('KB','0')); FL=[0]
NOM=os.environ.get('NOMODEL')=='1'
def snap():
    snaps[io.nd]=dict(vr=bytes(A.u.mem_read(0x06000000,0x18000)),pal=bytes(A.u.mem_read(0x05000000,0x400)),oam=bytes(A.u.mem_read(0x07000000,0x400)),io=bytes(io.regs),ew=bytes(A.u.mem_read(0x02000000,0x40000)))
class Arm(ArmSide):
    def _stub(s,uc,addr,sz,sid):
        if sid==1: FL[0]+=1
        if sid in (2,4) and not NOM:
            r=[uc.reg_read(UC_ARM_REG_R0+k) for k in range(3)]
            vr=bytearray(uc.mem_read(0x06000000,0xa000*2)); b=ppu_model.Blit(rom,vr)
            disp=struct.unpack_from('<H',s.io.regs,0)[0]
            if sid==2: b.blit2(r[0],r[1],r[2],disp)
            else:
                ew=lambda o:struct.unpack('<h',bytes(uc.mem_read(0x02000000+o,2)))[0]
                b.blit4(r[0],r[1],r[2],disp,ew(0x1cea),ew(0x1cec),ew(0x1d00))
            uc.mem_write(0x06000000,bytes(vr))
        super()._stub(uc,addr,sz,sid)
A=Arm.__new__(Arm); io=SIo(); Arm.__init__(A,rom,io,stubs=prune.stub_by_addr())
t0=time.time()
try: A.u.emu_start(0x08000000,0,count=int(os.environ.get('MAXINS','4000000000')))
except Exception as e: print('exc',e)
print(ST);print('ticks',io.nd,'flips',FL[0],'clk',struct.unpack_from('<I',bytes(A.u.mem_read(0x02001e00,4)))[0],'map',struct.unpack_from('<H',bytes(A.u.mem_read(0x02001d40,2)))[0],'dl',len(A.dl),round(time.time()-t0,1),'s')
pickle.dump(dict(dl=A.dl,snaps=snaps),open(sys.argv[3],'wb'))
