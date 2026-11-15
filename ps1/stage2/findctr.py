import sys,os,struct,collections
sys.path.insert(0,'.')
import numpy as np
from gbaenv import *
import prune
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
rom=open(SP+'/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
PAD=[0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81]
snaps={}
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=PAD[(s.nd//30)%6]
        return super().read(off,size)
    def tick(s):
        s.nd+=1
        if 40<=s.nd<=150: snaps[s.nd]=(np.frombuffer(A.ram('EWRAM'),dtype='<u2').copy(),np.frombuffer(A.ram('IWRAM'),dtype='<u2').copy())
        if s.nd>=150: A.u.emu_stop()
    def vblank(s): super().vblank(); s.tick()
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.tick()
io=SIo(); A=ArmSide(rom,io,stubs=prune.stub_by_addr())
A.u.emu_start(0x08000000,0,count=2000000000)
ks=sorted(snaps)
for nm,ix in (('EWRAM',0),('IWRAM',1)):
    arr=np.stack([snaps[k][ix].astype(np.int32) for k in ks])
    d=np.diff(arr,axis=0)&0xffff
    inc=(d==1).sum(axis=0)
    top=np.argsort(-inc)[:6]
    print(nm,[(hex(2*int(t)),int(inc[t])) for t in top],'of',len(ks)-1)
    ch=(d!=0).sum(axis=0); top=np.argsort(-ch)[:4]; print('  most-changing',[(hex(2*int(t)),int(ch[t])) for t in top])
