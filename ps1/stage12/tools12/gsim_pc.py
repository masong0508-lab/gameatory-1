import sys,os,time,bisect
sys.path.insert(0,'tools12'); sys.path.insert(0,'t')
from gsim import *
exe,iso,elf=sys.argv[1:4]
s=GSim(exe,iso,elf)
syms=sorted((v,k) for k,v in s.sym.items()); addrs=[a for a,_ in syms]
def name(pc):
    i=bisect.bisect_right(addrs,pc)-1; return syms[i][1]+'+%x'%(pc-syms[i][0]) if i>=0 else hex(pc)
pc=s.pc0
T=time.time()
for it in range(int(sys.argv[4])):
    try: s.u.emu_start(pc,0,count=20000000)
    except UcError as e: print('exc',e); break
    pc=s.u.reg_read(UC_MIPS_REG_PC)
    print(it,name(pc),'vbl',s.vbl,'quads',s.gpu.nq,'t %.0f'%(time.time()-T),flush=True)
