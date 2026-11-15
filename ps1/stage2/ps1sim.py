#!/usr/bin/env python3
"""Minimal PS1 model on unicorn-MIPS to run the *real* payback.exe (C runtime + translated blob + boot image) and count R3000 instructions.
GPU/IRQ/BIOS-putchar/root-counter stubs only.  usage: ps1sim.py payback.exe MAXTICKS [maxins]"""
import sys,struct,collections,subprocess
from unicorn import *
from unicorn.mips_const import *
exe=open(sys.argv[1],'rb').read(); MAXT=int(sys.argv[2]); MAXI=int(sys.argv[3]) if len(sys.argv)>3 else 3000000000
taddr,tsize=struct.unpack_from('<II',exe,0x18),None
pc0,gp0_,taddr,tsize=struct.unpack_from('<IIII',exe,0x10)
u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
u.mem_map(0,0x200000)
import os
isop=os.environ.get('ISO') or sys.argv[1].replace('payback_sim.exe','payback.iso').replace('payback.exe','payback.iso')
if os.path.exists(isop):
    d=open(isop,'rb').read(); u.mem_map(0x10000000,(len(d)+0xfff)&~0xfff); u.mem_write(0x10000000,d)
u.mem_write(taddr&0x1fffffff,exe[0x800:0x800+tsize])
out=bytearray(); gp0w=[]; rc=[0]; frames=[]
def mmio_r(uc,off,size,ud):
    a=0x1f801000+off
    if a==0x1f801814: return 0x1c000000
    if a==0x1f801070: return 1
    if a==0x1f801110: rc[0]=(rc[0]+7)&0xffff; return rc[0]
    return 0
def mmio_w(uc,off,size,val,ud):
    a=0x1f801000+off
    if a==0x1f801810: gp0w.append(val)
u.mmio_map(0x1f801000,0x1000,mmio_r,None,mmio_w,None)
u.mem_map(0x1f000000,0x10000)
def a0(uc,addr,sz,ud):
    r9=uc.reg_read(UC_MIPS_REG_9)
    if r9==0x3c: out.append(uc.reg_read(UC_MIPS_REG_4)&0xff)
    uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_31))
u.hook_add(UC_HOOK_CODE,a0,None,0xa0,0xa0)
# symbols
nm=subprocess.run(['llvm-nm','-n',os.environ.get('ELF') or sys.argv[1].replace('payback_sim.exe','bld_sim/payback.elf').replace('payback.exe','bld/payback.elf')],capture_output=True,text=True).stdout
sym={l.split()[2]:int(l.split()[0],16) for l in nm.splitlines() if len(l.split())==3}
cnt=[0]; last=[0]; per=[]
def vbl(uc,addr,sz,ud):
    n=cnt[0]; per.append(n-last[0]); last[0]=n
    if len(per)>=MAXT: uc.emu_stop()
u.hook_add(UC_HOOK_CODE,vbl,None,sym['h_vbl'],sym['h_vbl'])
mr=[]; mrall=[]
u.hook_add(UC_HOOK_CODE,lambda uc,a,sz,ud:(mrall.append((uc.reg_read(UC_MIPS_REG_4),uc.reg_read(UC_MIPS_REG_5))) if len(mrall)<4000000 else 0),None,sym['h_memrd'],sym['h_memrd'])
u.hook_add(UC_HOOK_CODE,lambda uc,a,sz,ud:(mr.append((uc.reg_read(UC_MIPS_REG_4),uc.reg_read(UC_MIPS_REG_5),uc.reg_read(UC_MIPS_REG_31))),mr.pop(0) if len(mr)>24 else 0),None,sym['h_memrd'],sym['h_memrd'])
iow=[]
u.hook_add(UC_HOOK_CODE,lambda uc,a,sz,ud:iow.append((uc.reg_read(UC_MIPS_REG_4),uc.reg_read(UC_MIPS_REG_5),uc.reg_read(UC_MIPS_REG_6))),None,sym['io_write'],sym['io_write'])
def cnt_blk(uc,a,sz,ud): cnt[0]+=sz//4
u.hook_add(UC_HOOK_BLOCK,cnt_blk)
u.reg_write(UC_MIPS_REG_29,0x801fd000)
try: u.emu_start(pc0&0x1fffffff|0x80000000 if False else pc0,0,count=MAXI)
except Exception as e: print('exc',e,hex(u.reg_read(UC_MIPS_REG_PC)))
print(out.decode('latin1'))
print('last memrd (ea,kind,ra):',[(hex(a),k,hex(r)) for a,k,r in mr])
print('vbl callbacks',len(per),'instrs total',cnt[0])
if per[1:]: 
    import statistics
    p=per[1:]; print('R3000 insns per guest frame (incl. helpers): mean %.0f median %.0f max %d min %d'%(statistics.mean(p),statistics.median(p),max(p),min(p)))
    print('first 20',per[:20]); print('last 20',per[-20:])
if '--where' in sys.argv:
    import bisect
    c=collections.Counter()
    u.hook_add(UC_HOOK_CODE,lambda uc,a,sz,ud:c.__setitem__(a,c[a]+1))
    try: u.emu_start(u.reg_read(UC_MIPS_REG_PC),0,count=20000)
    except Exception as e: print(e)
    m=sorted((int(h,16),int(a,16)) for a,h in (l.split() for l in open('out/pr/payback_P.map')))
    hs=[x for x,_ in m]
    bl=[(a,n) for a,n in c.items() if 0x80031000<=a<0x80080000]; print('blob pcs',sorted(bl)[-80:])
    for a,n in c.most_common(8):
        A=a|0x80000000; j=bisect.bisect_right(hs,A)-1
        print(hex(A),n,'guest~',hex(m[j][1]),'ra',hex(u.reg_read(UC_MIPS_REG_31)))
    print('regs s0-s7',[hex(u.reg_read(UC_MIPS_REG_16+k)) for k in range(8)],'fp',hex(u.reg_read(UC_MIPS_REG_30)))
if '--where' in sys.argv:
    print('t8 t9 at v0',[hex(u.reg_read(r)) for r in (UC_MIPS_REG_24,UC_MIPS_REG_25,UC_MIPS_REG_1,UC_MIPS_REG_2)],'gp',hex(u.reg_read(UC_MIPS_REG_28)))
    ring=[]
    u.hook_add(UC_HOOK_CODE,lambda uc,a,sz,ud:(ring.append(a),ring.pop(0) if len(ring)>40 else 0))
    u.emu_start(u.reg_read(UC_MIPS_REG_PC),0,count=300)
    print([hex(x) for x in ring[:40]])

import pickle; pickle.dump(iow,open('out/ps1_iow.pkl','wb'))

for nme in ('cold_loads','cold_calls','cd_sectors','rom_miss_count','rom_miss_last','io_vc','io_nd','g_nvbl','g_pres'):
    if nme in sym: print(nme,hex(int.from_bytes(u.mem_read(sym[nme]&0x1fffffff,4),'little')))

pickle.dump(mrall,open('out/ps1_rd.pkl','wb'))
