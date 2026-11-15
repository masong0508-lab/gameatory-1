import sys,os,time,bisect
sys.path.insert(0,'tools12'); sys.path.insert(0,'t')
from gsim import *
exe,iso,elf=sys.argv[1:4]; lo=int(sys.argv[4],16); hi=int(sys.argv[5],16); TOTAL=int(sys.argv[6])
s=GSim(exe,iso,elf)
syms=sorted((v,k) for k,v in s.sym.items()); addrs=[a for a,_ in syms]
def name(pc):
    i=bisect.bisect_right(addrs,pc)-1; return syms[i][1]+'+%x'%(pc-syms[i][0]) if i>=0 else hex(pc)
hits={}; CY=s.sym['io_cyc']
def vw(uc,acc,addr,sz,val,ud):
    pc=uc.reg_read(UC_MIPS_REG_PC); k=name(pc).split('+')[0]
    h=hits.setdefault(k,[0,0,None,None]); h[0]+=1; h[1]+=(val!=0)
    if h[2] is None: h[2]=(s.r32(CY)//280896,hex(addr),hex(val&0xffffffff))
    h[3]=(s.r32(CY)//280896,hex(addr),hex(val&0xffffffff))
s.u.hook_add(UC_HOOK_MEM_WRITE,vw,None,lo&0x1fffffff,hi&0x1fffffff)
s.cb=lambda s: s.r32(CY)//280896>=TOTAL
s.run(count=30000000000)
for k,v in hits.items(): print(k,'writes',v[0],'nonzero',v[1],'first',v[2],'last',v[3])
