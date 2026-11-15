import sys,bisect; sys.path.insert(0,'t')
from sim4 import *
from unicorn.mips_const import *
V='f1'; s=Sim('out/%s.exe'%V,'out/%s.iso'%V,'out/bld_%s/payback.elf'%V)
sym=s.sym
M=sorted((int(h,16),int(a,16)) for a,h in (l.split() for l in open('out/pr_%s/payback_P.map'%V)))
HS=[x for x,_ in M]
def g(h):
    j=bisect.bisect_right(HS,h)-1; return '%08x+%d'%(M[j][1],(h-M[j][0])) if j>=0 else '?'
ring=[]
blk=[]
def bh(uc,a,sz,ud):
    blk.append(a); del blk[:-3000]
s.u.hook_add(UC_HOOK_BLOCK,bh)
def hm(uc,a,sz,ud):
    ring.append(('miss',uc.reg_read(UC_MIPS_REG_4),uc.reg_read(UC_MIPS_REG_31)))
    ring[:]=ring[-40:]
s.u.hook_add(UC_HOOK_CODE,hm,None,sym['h_miss'],sym['h_miss'])
armed=[0]
evs=[]
def ha(uc,a,sz,ud): del evs[:]
s.u.hook_add(UC_HOOK_CODE,ha,None,sym['h_miss'],sym['h_miss'])
def ww(uc,acc,addr,sz,val,ud):
    if 1: evs.append(('W',hex(addr),sz,hex(val),'pc',hex(uc.reg_read(UC_MIPS_REG_PC)),'ra',hex(uc.reg_read(UC_MIPS_REG_31))))
s.u.hook_add(UC_HOOK_MEM_WRITE,ww,None,0x801fff68,0x801fff8f)
s.u.hook_add(UC_HOOK_MEM_WRITE,ww,None,0x1fff68,0x1fff8f)
s.cb=lambda s: s.r32(sym['io_cyc'])//280896>1100
s.run(count=30000000000)

for e in evs[:40]: print(e)
