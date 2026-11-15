#!/usr/bin/env python3
"""TEST-ONLY unicorn-MIPS sim of the PS1 exe (code only; no ROM inside).  Library: Sim(exe, iso, elf) with run(), guest memory access, key injection."""
import sys,struct,os,subprocess,time
from unicorn import *
from unicorn.mips_const import *
class Sim:
    def __init__(s,exe,iso,elf):
        e=open(exe,'rb').read(); pc0,gp,ta,ts=struct.unpack_from('<IIII',e,0x10)
        u=s.u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN); u.mem_map(0,0x1000000)
        d=open(iso,'rb').read(); u.mem_map(0x10000000,(len(d)+0xfff)&~0xfff); u.mem_write(0x10000000,d)
        u.mem_write(ta&0x1fffffff,e[0x800:0x800+ts]); s.out=bytearray(); s.rc=0
        def r(uc,off,size,ud):
            a=0x1f801000+off
            if a==0x1f801814: return 0x1c000000
            if a==0x1f801070: return 1
            if a==0x1f801110: s.rc=(s.rc+7)&0xffff; return s.rc
            return 0
        u.mmio_map(0x1f801000,0x1000,r,None,lambda *a:None,None); u.mem_map(0x1f000000,0x10000)
        def a0(uc,addr,sz,ud):
            if uc.reg_read(UC_MIPS_REG_9)==0x3c: s.out.append(uc.reg_read(UC_MIPS_REG_4)&0xff)
            uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_31))
        u.hook_add(UC_HOOK_CODE,a0,None,0xa0,0xa0)
        nm=subprocess.run(['llvm-nm','-n',elf],capture_output=True,text=True).stdout
        s.sym={l.split()[2]:int(l.split()[0],16) for l in nm.splitlines() if len(l.split())==3}
        s.pc0=pc0; u.reg_write(UC_MIPS_REG_29,0x801fd000); s.vbl=0; s.cb=None
        u.hook_add(UC_HOOK_CODE,s._v,None,s.sym['present'],s.sym['present'])
    def _v(s,uc,a,sz,ud):
        s.vbl+=1
        if s.cb and s.cb(s): uc.emu_stop()
    def rd(s,a,n): return bytes(s.u.mem_read(a&0x1fffffff,n))
    def r32(s,a): return struct.unpack('<I',s.rd(a,4))[0]
    def r16(s,a): return struct.unpack('<H',s.rd(a,2))[0]
    def w32(s,a,v): s.u.mem_write(a&0x1fffffff,struct.pack('<I',v))
    def sv(s,n): return s.sym[n]
    def run(s,pc=None,count=4000000000):
        try: s.u.emu_start(pc if pc is not None else s.pc0,0,count=count)
        except UcError as e: print('exc',e,hex(s.u.reg_read(UC_MIPS_REG_PC)))
PAL,VRAM,EW,IW=0x80180000,0x80181000,0x801b0000,0x801f0000
def shot(s,path):
    from PIL import Image
    import numpy as np
    dc=s.r16(s.sv('io')); mode=dc&7; pal=np.frombuffer(s.rd(PAL,512),'<u2')
    rgb=lambda v:(((v&31)<<3),(((v>>5)&31)<<3),(((v>>10)&31)<<3))
    img=np.zeros((160,240,3),np.uint8)
    if mode==4:
        base=0xa000 if dc&0x10 else 0; px=np.frombuffer(s.rd(VRAM+base,240*160),np.uint8).reshape(160,240)
        P=np.array([rgb(int(v)) for v in pal[:256]],np.uint8); img=P[px]
    elif mode==3:
        px=np.frombuffer(s.rd(VRAM,240*160*2),'<u2').reshape(160,240); img=np.array([[rgb(int(v)) for v in row] for row in px],np.uint8)
    Image.fromarray(img).resize((480,320)).save(path); return dc
