#!/usr/bin/env python3
"""Unicorn environments: the original GBA ARM side and the translated MIPS side share one IO model (Io) so that their
I/O write sequences and DMA effects are comparable.  Minimal GBA stub: IO regs recorded, DMA3 immediate transfers, keypad, BIOS 5."""
import struct,bisect,collections
from unicorn import *
from unicorn.arm_const import *
from unicorn.mips_const import *
import numpy as np
REGIONS=[('EWRAM',0x02000000,0x40000),('IWRAM',0x03000000,0x8000),('PAL',0x05000000,0x400),('VRAM',0x06000000,0x18000),('OAM',0x07000000,0x400),('SRAM',0x0e000000,0x10000)]
def P(h): return h&0x1fffffff if h>=0x80000000 else h
class Io:
    def __init__(s):
        s.regs=bytearray(0x400); s.log=[]; s.nread=0; s.keys=0x3ff; s.dma=None; s.logon=True
        s.vc=0; s.tm=[0]*4
        s.mem=None   # object with guest-address r/w functions for DMA
        s.nwr=0
        s.last_ewram_ptr=None
    def read(s,off,size):
        s.nread+=1
        if off==0x130 or off==0x131:
            v=s.keys
            return (v if size==2 else (v>>(8*(off-0x130)))&0xff if size==1 else v)
        if off in (6,7):
            s.vc=(s.vc+1)%228
            v=s.vc
            return v if size!=1 else (v>>(8*(off-6)))&0xff
        if off in (4,5):
            s.vc=(s.vc+1)%228
            v=(1 if s.vc>=160 and s.vc<227 else 0)|(2 if (s.nread&3)==0 else 0)|(4 if s.vc==((struct.unpack_from('<H',s.regs,4)[0]>>8)&0xff) else 0)|(struct.unpack_from('<H',s.regs,4)[0]&0xff38)
            return v&0xffff if size==2 else (v>>(8*(off-4)))&0xff if size==1 else v
        if off in(0x100,0x104,0x108,0x10c):
            s.tm[(off-0x100)//4]+=37; return s.tm[(off-0x100)//4]&0xffff
        return int.from_bytes(s.regs[off:off+size],'little')
    def write(s,off,size,val):
        val&=(1<<(8*size))-1
        s.nwr+=1
        if s.logon: s.log.append((off,size,s.norm(off,size,val)))
        if off==0x202 and size==2: # IF write-1-to-clear
            old=struct.unpack_from('<H',s.regs,0x202)[0]; struct.pack_into('<H',s.regs,0x202,old&~val&0xffff); return
        s.regs[off:off+size]=val.to_bytes(size,'little')
        # DMA3 control high halfword (0xde), also covers 32-bit write at 0xdc
        for ch in range(4):
            cnt=0xb0+12*ch+8
            if off<=cnt+2 and off+size>=cnt+4:
                s.dma_check(ch)
    def norm(s,off,size,val):
        return val
    def dma_check(s,ch):
        base=0xb0+12*ch
        sad,dad,cntl,cnth=struct.unpack_from('<IIHH',s.regs,base)
        if not (cnth&0x8000): return
        timing=(cnth>>12)&3
        if timing!=0 or ch==1 or ch==2 and False: return   # only immediate transfers are emulated
        if s.mem is None: return
        n=cntl or (0x10000 if ch==3 else 0x4000)
        unit=4 if cnth&0x400 else 2
        dc=(cnth>>5)&3; sc=(cnth>>7)&3
        src=s.mem.unmap(sad); dst=s.mem.unmap(dad)
        for k in range(n):
            v=s.mem.rd(src,unit)
            s.mem.wr(dst,unit,v)
            if sc==0: src+=unit
            elif sc==1: src-=unit
            if dc in(0,3): dst+=unit
            elif dc==1: dst-=unit
        s.dmas=getattr(s,'dmas',0)+1
        if not (cnth&0x200):   # no repeat -> clear enable
            struct.pack_into('<H',s.regs,base+10,cnth&0x7fff)
class ArmSide:
    def __init__(s,rom,io,prog=None):
        s.rom=rom; s.io=io
        u=s.u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        u.mem_map(0x08000000,0x800000,UC_PROT_ALL); u.mem_write(0x08000000,rom[:0x800000])
        for n,b,sz in REGIONS: u.mem_map(b,sz)
        u.mmio_map(0x04000000,0x1000,s._rd,None,s._wr,None)
        u.mem_map(0x0d000000,0x10000); u.mem_write(0x0d000000,b'\x01'*0x10000)    # EEPROM stub: always ready / 1 bits
        u.reg_write(UC_ARM_REG_CPSR,0x1f)
        s.nins=0; s.cache={}
        s.prog=prog
        io.mem=s
    def _rd(s,uc,off,size,ud): return s.io.read(off,size) if off<0x400 else 0
    def _wr(s,uc,off,size,val,ud):
        if off<0x400:
            try: s.io.write(off,size,val)
            except Exception:
                import traceback; traceback.print_exc(); raise
    def unmap(s,a): return a
    def rd(s,a,n):
        if a>>24==4: return s.io.read(a&0x3ff,n)
        return int.from_bytes(s.u.mem_read(a,n),'little')
    def wr(s,a,n,v):
        if a>>24==4: s.io.write(a&0x3ff,n,v); return
        s.u.mem_write(a,(v&((1<<(8*n))-1)).to_bytes(n,'little'))
    def r(s,k): return s.u.reg_read(UC_ARM_REG_R0+k) if k<13 else s.u.reg_read([UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC][k-13])
    def regs(s): return [s.r(k) for k in range(15)]
    def setr(s,k,v):
        if k<13: s.u.reg_write(UC_ARM_REG_R0+k,v&0xffffffff)
        else: s.u.reg_write([UC_ARM_REG_SP,UC_ARM_REG_LR][k-13],v&0xffffffff)
    def ram(s,name):
        for n,b,sz in REGIONS:
            if n==name: return bytes(s.u.mem_read(b,sz))
    def run(s,pc,until,count=0):
        """run Thumb/ARM from pc until address `until`; returns reason"""
        s.u.emu_start(pc,until,count=count)
class MipsSide:
    def __init__(s,rom,io,cfg,blob,rt,entries_set,reloc=True):
        s.io=io; s.cfg=cfg; s.rom=rom
        u=s.u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
        s.base=cfg.BASE
        sz=(len(blob)+0xfff)&~0xfff
        u.mem_map(s.base&0x1fffffff,sz,UC_PROT_ALL); u.mem_write(s.base&0x1fffffff,blob)
        u.mem_map(0x08000000,0x800000,UC_PROT_READ|UC_PROT_WRITE); u.mem_write(0x08000000,rom[:0x800000])
        s.hostbase={}
        for n,b,sz2 in REGIONS:
            h=cfg.host(b); s.hostbase[n]=h
            u.mem_map(h&0x1fffffff if h>=0x80000000 else h,(sz2+0xfff)&~0xfff)
        u.mem_map(0x0d000000,0x10000); u.mem_write(0x0d000000,b'\x01'*0x10000)
        ioh=cfg.host(0x04000000)
        s.ioh=ioh
        u.mmio_map(ioh&0x1fffffff if ioh>=0x80000000 else ioh,0x1000,s._rd,None,s._wr,None)
        s.rt=rt; s.entries=entries_set
        s.nins=0; s.reloc_cnt=0; s.rom_reads=0; s.rom_bytes=0; s.seen=set()
        io.mem=s
        if reloc:
            u.hook_add(UC_HOOK_MEM_READ,s._romread,None,0x08000000,0x087fffff)
        s.stop_at={}
    def _rd(s,uc,off,size,ud): return s.io.read(off,size) if off<0x400 else 0
    def _wr(s,uc,off,size,val,ud):
        if off<0x400:
            if size==4 and 0xb0<=off<0xe0 and (off-0xb0)%12 in (0,4):
                val=s.unmap(val)
            s.io.write(off,size,val)
    def _romread(s,uc,access,addr,size,value,ud):
        s.rom_reads+=1; s.rom_bytes+=size
        if size==4 and (addr&3)==0 and addr not in s.seen:
            s.seen.add(addr)
            v=int.from_bytes(uc.mem_read(addr,4),'little')
            if (v in s.entries) or ((v&~1) in s.entries): return
            h=s.cfg.host(v)
            if h is not None and v>=0x02000000:
                uc.mem_write(addr,struct.pack('<I',h)); s.reloc_cnt+=1
    # guest <-> host address helpers
    def host(s,a):
        h=s.cfg.host(a); return a if h is None else h
    def unmap(s,h):
        h&=0xffffffff
        for g,n,hb in s.cfg.reg:
            if hb<=h<=hb+n: return g+h-hb
        return h
    def rd(s,a,n):
        if a>>24==4: return s.io.read(a&0x3ff,n)
        return int.from_bytes(s.u.mem_read(P(s.host(a)),n),'little')
    def wr(s,a,n,v):
        if a>>24==4: s.io.write(a&0x3ff,n,v); return
        s.u.mem_write(P(s.host(a)),(v&((1<<(8*n))-1)).to_bytes(n,'little'))
    def r(s,k): return s.u.reg_read(UC_MIPS_REG_0+k)
    def setr(s,k,v): s.u.reg_write(UC_MIPS_REG_0+k,v&0xffffffff)
    GM={0:16,1:17,2:18,3:19,4:20,5:21,6:22,7:23,8:11,9:12,10:13,11:14,12:15,13:30,14:31}
    def gregs(s): return [s.r(s.GM[k]) for k in range(15)]
    def ram(s,name):
        for n,b,sz in REGIONS:
            if n==name: return bytes(s.u.mem_read(P(s.hostbase[n]),sz))
def norm_words(cfg,host_bytes,base_guest,entries):
    """map host-pointer words in a RAM image back to guest values for comparison (vectorised)"""
    a=np.frombuffer(host_bytes,dtype='<u4').copy()
    for g,n,h in cfg.reg:
        m=(a>=h)&(a<=h+n)
        a[m]=a[m]-np.uint32(h)+np.uint32(g)
    return a
