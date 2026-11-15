import sys; sys.path.insert(0,'t')
from sim4 import *
from capstone import *
s=Sim('out/f1.exe','out/f1.iso','out/bld_f1/payback.elf')
s.cb=lambda s: s.r32(s.sym['io_cyc'])//280896>3
s.run(count=30000000000)
a=int(sys.argv[1],16); n=int(sys.argv[2],16)
for i in Cs(CS_ARCH_MIPS,CS_MODE_MIPS32+CS_MODE_LITTLE_ENDIAN).disasm(s.rd(a,n),a): print(hex(i.address),i.mnemonic,i.op_str)
