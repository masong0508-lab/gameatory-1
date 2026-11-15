#!/usr/bin/env python3
"""TEST/ANALYSIS: run the real ROM (no stubs) in unicorn ARM; at entry of the 5 stub functions record args and the VRAM/PAL/OAM effect.
usage: armtrace.py ROM NTICKS OUT.pkl"""
import sys,os,struct,pickle,collections
sys.path.insert(0,'.')
import numpy as np
from gbaenv import *
import prune
rom=open(sys.argv[1],'rb').read(); NT=int(sys.argv[2])
PAD=[0x3ff]
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0; s.logon=False; s.pad=eval(os.environ.get('PADF','lambda n:0x3ff'))
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=s.pad(s.nd)
        return super().read(off,size)
    def tick(s):
        s.nd+=1
        if s.nd>=NT: A.u.emu_stop()
        if A.hook_tick: A.hook_tick(s.nd)
    def vblank(s): super().vblank(); s.tick()
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.tick()
A=ArmSide.__new__(ArmSide); io=SIo(); ArmSide.__init__(A,rom,io,stubs={})
A.hook_tick=None
calls=[]; pend=[]
names={a:(n,i) for i,(a,n) in prune.STUBS.items()}
def mem(a,n): return bytes(A.u.mem_read(a,n))
def hook(uc,addr,sz,ud):
    n,i=names[addr]
    r=[uc.reg_read(UC_ARM_REG_R0+k) for k in range(4)]
    lr=uc.reg_read(UC_ARM_REG_LR); sp=uc.reg_read(UC_ARM_REG_SP)
    rec=dict(tick=io.nd,id=i,name=n,r=r,lr=lr,sp=sp,stack=struct.unpack('<4I',mem(sp,16)),
      vr=mem(0x06000000,0x18000),pal=mem(0x05000000,0x400),oam=mem(0x07000000,0x400),disp=struct.unpack_from('<H',io.regs,0)[0],
      hdr=mem(r[0],32) if 0x02000000<=r[0]<0x08800000 or 0x03000000<=r[0]<0x03008000 else b'')
    calls.append(rec)
    if lr&~1 not in (0,): 
        h=uc.hook_add(UC_HOOK_CODE,lambda u,a,s,d:ret(u,rec,h_),None,lr&~1,lr&~1); h_=h
def ret(uc,rec,h):
    if rec.get('done'): return
    rec['done']=1
    rec['vr2']=mem(0x06000000,0x18000); rec['pal2']=mem(0x05000000,0x400); rec['oam2']=mem(0x07000000,0x400); rec['r0out']=uc.reg_read(UC_ARM_REG_R0)
    rec['disp2']=struct.unpack_from('<H',io.regs,0)[0]
    uc.hook_del(h)
for a in names: A.u.hook_add(UC_HOOK_CODE,hook,None,a,a)
try: A.u.emu_start(0x08000000,0,count=int(os.environ.get('MAXINS','4000000000')))
except Exception as e: print('exc',e)
print('pc',hex(A.u.reg_read(UC_ARM_REG_PC)),'lr',hex(A.u.reg_read(UC_ARM_REG_LR)),'cpsr',hex(A.u.reg_read(UC_ARM_REG_CPSR)),'nins?');print('ticks',io.nd,'calls',len(calls),collections.Counter(c['id'] for c in calls))
pickle.dump(calls,open(sys.argv[3],'wb'))
