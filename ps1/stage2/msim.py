import os
"""Unicorn-MIPS model of the PS1 runtime around the translated blob (cfg 'P' layout).  The C helper calls of RT_MEMRD/RT_MEMWR/RT_MISS are
hooked here (the blob's RT_CC trampoline is what calls the real C on the PS1).  ROM data is only reachable through RT_MEMRD (ROM page protected
after boot) and every page served is recorded."""
import struct,collections
from unicorn import *
from unicorn.mips_const import *
import numpy as np
from gbaenv import Io,norm_words
def P(h): return h&0x1fffffff if h>=0x80000000 else h
class MSim:
    def __init__(s,rom,io,cfg,blob,rt,gmap,stubs=None,rpages=(),cold=None):
        s.rdlog=[]; s.io=io; s.cfg=cfg; s.rom=rom; s.rt=rt; s.gmap=gmap
        u=s.u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
        pages=set()
        def mp(base,size,perm=UC_PROT_ALL):
            for pg in range(P(base)&~0xfff,(P(base)+size+0xfff)&~0xfff,0x1000):
                if pg not in pages: pages.add(pg); u.mem_map(pg,0x1000,perm)
        s.base=cfg.BASE
        mp(cfg.BASE,len(blob)); u.mem_write(P(cfg.BASE),blob)
        s.cold=cold; s.ovl_loaded=set(); s.ovl_loads=0; s.ovl_calls=0; s.coldrows={}
        if cold:
            cb,ctab,cstart=cold; s.cstart=cstart
            mp(cstart,len(cb)+16384)
            n=struct.unpack_from('<I',ctab,0)[0]
            for k in range(n): g,h,hs,he=struct.unpack_from('<IIII',ctab,4+16*k); s.coldrows[g]=(h,hs,he)
        s.reg={}
        for g,n,h in cfg.reg:
            if g==0x04000000: continue
            mp(h,n)
        mp(cfg.DL,0x2100)
        s.ioh=cfg.host(0x04000000)
        mp(0x08000000,0x800000)          # guest ROM window (page-protected after boot)
        u.mem_write(0x08000000,rom[:0x800000])
        mp(0x801fc000,0x4000)             # C stack area
        mp(0x80010000,0x20000); mp(cfg.HELP,0x1000); mp(cfg.ROMPG,0x2000)
        mp(0x80100000,0x1000*max(1,len(rpages)))
        for k,pg in enumerate(sorted(rpages)):      # resident ROM pages visible to the blob's RT_MEMRD fast path
            u.mem_write(P(0x80100000+0x1000*k),rom[pg*4096:pg*4096+4096].ljust(4096,b'\0')); u.mem_write(P(cfg.ROMPG)+4*(pg&2047),struct.pack('<I',0x80100000+0x1000*k))
        u.mmio_map(P(s.ioh)&~0xfff,0x1000,s._ior,None,s._iow,None)
        s.rom_unmapped=False; s.rompages=collections.Counter(); s.errs=[]; s.mmio_hits=0
        s.nmemrd=s.nmemwr=0; s.helper_sites=collections.Counter()
        u.hook_add(UC_HOOK_CODE,s._memrd,None,rt['RT_MEMRD_SLOW'],rt['RT_MEMRD_SLOW'])
        u.hook_add(UC_HOOK_CODE,s._memwr,None,rt['RT_MEMWR'],rt['RT_MEMWR'])
        u.hook_add(UC_HOOK_CODE,s._miss,None,rt['RT_MISS'],rt['RT_MISS'])
        u.hook_add(UC_HOOK_CODE,lambda uc,a,sz,ud:(setattr(s,'nvbl',getattr(s,'nvbl',0)+1),uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_28))),None,rt['RT_VBL'],rt['RT_VBL'])
        s.misses=[]; s.nswi=0; s.stoperr=False
        io.mem=s
        if 0x100 in gmap: u.hook_add(UC_HOOK_CODE,lambda uc,a,sz,ud:(s.io.vblank(),setattr(s,'nswi',s.nswi+1)),None,gmap[0x100],gmap[0x100])
    def protect_rom(s):
        s.u.mem_protect(0x08000000,0x800000,0); s.rom_unmapped=True
    # ---- helpers
    def romrd(s,ea,size):
        off=ea&0x01ffffff
        s.rompages[off>>12]+=1
        if off+size>len(s.rom): return 0
        return int.from_bytes(s.rom[off:off+size],'little')
    def rd(s,a,n):        # guest-address read (DMA source etc.)
        if a>>24==4: return s.io.read(a&0x3ff,n)
        if (a>>24) in (8,10,12): return s.romrd(a,n)
        if a>>24==13: return 1
        return int.from_bytes(s.u.mem_read(P(s.host(a)),n),'little')
    def wr(s,a,n,v):
        if a>>24==4: s.io.write(a&0x3ff,n,v); return
        s.u.mem_write(P(s.host(a)),(v&((1<<(8*n))-1)).to_bytes(n,'little'))
    def host(s,a):
        h=s.cfg.host(a); return a if h is None else h
    def unmap(s,h):
        h&=0xffffffff
        for g,n,hb in s.cfg.reg:
            if hb<=h<hb+n: return g+h-hb
        return h
    def _ior(s,uc,off,size,ud): s.mmio_hits+=1; s.errs.append(('mmio-read',off,uc.reg_read(UC_MIPS_REG_PC))); return s.io.read(off,size) if off<0x400 else 0
    def _iow(s,uc,off,size,val,ud): s.mmio_hits+=1; s.errs.append(('mmio-write',off,uc.reg_read(UC_MIPS_REG_PC)))
    def _memrd(s,uc,addr,sz,ud):
        ea=uc.reg_read(UC_MIPS_REG_24); kind=uc.reg_read(UC_MIPS_REG_2)
        size=(1,1,2,2,4)[kind]; sg=kind in(1,3)
        s.nmemrd+=1
        if os.environ.get('RDLOG') and len(s.rdlog)<4000000: s.rdlog.append((ea,kind))
        if (ea>>24) in (8,10,12): v=s.romrd(ea,size)
        elif ea>>24==13: v=1
        elif s.ioh<=ea<s.ioh+0x400: v=s.io.read(ea-s.ioh,size)
        elif 0x80180000<=ea<0x80200000: v=int.from_bytes(uc.mem_read(P(ea),size),'little')
        else:
            s.errs.append(('bad-read',ea,uc.reg_read(UC_MIPS_REG_28))); v=0
            if s.stoperr: uc.emu_stop()
        if sg and v&(1<<(8*size-1)): v-=1<<(8*size)
        uc.reg_write(UC_MIPS_REG_2,v&0xffffffff); uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_28))
    def _memwr(s,uc,addr,sz,ud):
        ea=uc.reg_read(UC_MIPS_REG_24); size=uc.reg_read(UC_MIPS_REG_2); val=uc.reg_read(UC_MIPS_REG_3)
        s.nmemwr+=1
        if s.ioh<=ea<s.ioh+0x400:
            off=ea-s.ioh
            if size==4 and 0xb0<=off<0xe0 and (off-0xb0)%12 in (0,4): val=s.unmap(val)
            s.io.write(off,size,val)
        elif 0x80180000<=ea<0x80200000: uc.mem_write(P(ea),(val&((1<<(8*size))-1)).to_bytes(size,'little'))
        elif ea>>24==13: pass
        else: s.errs.append(('bad-write',ea,uc.reg_read(UC_MIPS_REG_28)))
        uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_28))
    def _miss(s,uc,addr,sz,ud):
        g=uc.reg_read(UC_MIPS_REG_25)&~1; s.ovl_calls+=1
        if s.cold and g in s.coldrows:
            h,hs,he=s.coldrows[g]
            for k in range((hs-s.cstart)>>14,((he-1-s.cstart)>>14)+1):
                if k not in s.ovl_loaded:
                    s.ovl_loaded.add(k); s.ovl_loads+=1; d=s.cold[0][k*16384:(k+1)*16384]; uc.mem_write(P(s.cstart)+k*16384,d)
            uc.reg_write(UC_MIPS_REG_PC,h); return
        s.misses.append(g); uc.emu_stop()
    def dlist(s):
        raw=bytes(s.u.mem_read(P(s.cfg.DL),0x2020)); n=struct.unpack_from('<I',raw,0)[0]
        return n,[struct.unpack_from('<5I',raw,0x20+(k&255)*32) for k in range(max(0,n-256),n)]
    def r(s,k): return s.u.reg_read(UC_MIPS_REG_0+k)
    def setr(s,k,v): s.u.reg_write(UC_MIPS_REG_0+k,v&0xffffffff)
    GM={0:16,1:17,2:18,3:19,4:20,5:21,6:22,7:23,8:11,9:12,10:13,11:14,12:15,13:30,14:31}
    def ram(s,name):
        base={'EWRAM':(0x02000000,0x40000),'IWRAM':(0x03000000,0x8000),'PAL':(0x05000000,0x400),'VRAM':(0x06000000,0x18000),'OAM':(0x07000000,0x400)}[name]
        return bytes(s.u.mem_read(P(s.cfg.host(base[0])),base[1]))
