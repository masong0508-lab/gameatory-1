#!/usr/bin/env python3
"""mkiw.py: IWRAM image at Payback's main (crt0 run on unicorn-ARM: copies the ROM's IWRAM code/data) -> OUT/iw.bin.  usage: mkiw.py ROM OUT"""
import sys
from unicorn import *
ROM=open(sys.argv[1],'rb').read()
u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
u.mem_map(0x08000000,0x800000); u.mem_write(0x08000000,ROM[:0x800000])
u.mem_map(0x02000000,0x40000); u.mem_map(0x03000000,0x8000)
for a,n in ((0x04000000,0x1000),(0x05000000,0x1000),(0x06000000,0x20000),(0x07000000,0x1000),(0x0e000000,0x10000)): u.mem_map(a,n)
u.emu_start(0x08000000,0x08022dc8,count=2000000)
open(sys.argv[2],'wb').write(bytes(u.mem_read(0x03000000,0x8000)))
