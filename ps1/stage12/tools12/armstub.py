#!/usr/bin/env python3
"""ANALYSIS: stubbed ARM unicorn (same stubs as the PS1 build) run with the stock pad plan; snapshots VRAM/PAL/OAM/IO/EWRAM + draw list at chosen ticks.
usage: armstub.py ROM NTICKS OUT.pkl [snap ticks comma list]"""
import sys,os,struct,pickle,json,time
sys.path.insert(0,'.')
import numpy as np
from gbaenv import *
import prune
rom=open(sys.argv[1],'rb').read(); NT=int(sys.argv[2]); SNAPS=set(int(x) for x in sys.argv[4].split(',')) if len(sys.argv)>4 else set()
plan=json.load(open('../s10_boot/out/pad_boot.json'))['plan']
def padat(f):
    for a,b,m in plan:
        if a<=f<b: return 0x3ff&~m
    return 0x3ff
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0; s.logon=False
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=padat(s.nd//1)   # plan is in GBA frames; ticks (vblanks) ~ frames
        return super().read(off,size)
    def tick(s):
        s.nd+=1
        if s.nd in SNAPS: snaps[s.nd]=dict(vr=bytes(A.u.mem_read(0x06000000,0x18000)),pal=bytes(A.u.mem_read(0x05000000,0x400)),oam=bytes(A.u.mem_read(0x07000000,0x400)),io=bytes(io.regs),dl=len(A.dl),ew=bytes(A.u.mem_read(0x02000000,0x40000)),iw=bytes(A.u.mem_read(0x03000000,0x8000)))
        if s.nd>=NT: A.u.emu_stop()
    def vblank(s): super().vblank(); s.tick()
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.tick()
snaps={}
A=ArmSide.__new__(ArmSide); io=SIo(); ArmSide.__init__(A,rom,io,stubs=prune.stub_by_addr())
t0=time.time()
try: A.u.emu_start(0x08000000,0,count=int(os.environ.get('MAXINS','4000000000')))
except Exception as e: print('exc',e)
print('ticks',io.nd,'dl',len(A.dl),round(time.time()-t0,1),'s')
pickle.dump(dict(dl=A.dl,snaps=snaps),open(sys.argv[3],'wb'))
