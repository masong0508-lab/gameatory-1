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
    blk.append(a); del blk[:-300]
s.u.hook_add(UC_HOOK_BLOCK,bh)
def hm(uc,a,sz,ud):
    ring.append(('miss',uc.reg_read(UC_MIPS_REG_4),uc.reg_read(UC_MIPS_REG_31)))
    ring[:]=ring[-40:]
s.u.hook_add(UC_HOOK_CODE,hm,None,sym['h_miss'],sym['h_miss'])
evs=[]
def ww(uc,acc,addr,sz,val,ud):
    evs.append((hex(addr),sz,hex(val),'pc',hex(uc.reg_read(UC_MIPS_REG_PC)),'ra',hex(uc.reg_read(UC_MIPS_REG_31)),'blk',[g(x) for x in blk[-3:]]))
    del evs[:-6]
s.u.hook_add(UC_HOOK_MEM_WRITE,ww,None,0x17c3c8,0x17c3d7)
s.u.hook_add(UC_HOOK_MEM_WRITE,ww,None,0x8017c3c8,0x8017c3d7)
s.cb=lambda s: s.r32(sym['io_cyc'])//280896>1121
s.run(count=30000000000)
print([(hex(x),g(x)) for x in blk[-40:]])
print('regs',[hex(s.u.reg_read(r)) for r in range(UC_MIPS_REG_1,UC_MIPS_REG_1+31)])
from capstone import *
for a,n in ((0x8017c3c8,0x30),):
    for i in Cs(CS_ARCH_MIPS,CS_MODE_MIPS32+CS_MODE_LITTLE_ENDIAN).disasm(s.rd(a,n),a): print('D',hex(i.address),i.mnemonic,i.op_str)
print('raw',s.rd(0x8017c3c8,48).hex())

for e in evs: print('E',e)
