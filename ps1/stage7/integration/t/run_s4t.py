import sys; sys.path.insert(0,'t')
from sim4 import *
s=Sim('out/s4t.exe','out/s4t.iso','out/bld_s4t/payback.elf')
N=int(sys.argv[1]) if len(sys.argv)>1 else 40
s.cb=lambda s: s.vbl>N
s.run(count=int(sys.argv[2]) if len(sys.argv)>2 else 30000000000)
print(s.out.decode('latin1')[-1500:]); print('pc',hex(s.u.reg_read(UC_MIPS_REG_PC)),'vbl',s.vbl)
