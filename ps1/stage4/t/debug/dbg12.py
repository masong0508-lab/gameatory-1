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
cnt=[0]
def wr(uc,a,sz,ud):
    ea=uc.reg_read(UC_MIPS_REG_4)
    if (ea>>24) in (2,3):
        print('BADWR ea',hex(ea),'size',uc.reg_read(UC_MIPS_REG_5),'val',hex(uc.reg_read(UC_MIPS_REG_6)),'ra',hex(uc.reg_read(UC_MIPS_REG_31)))
        print([(hex(x),g(x)) for x in blk[-6:]])
        print('regs',[hex(uc.reg_read(r)) for r in range(UC_MIPS_REG_1,UC_MIPS_REG_1+31)])
        cnt[0]+=1
        if cnt[0]>0: uc.emu_stop()
s.u.hook_add(UC_HOOK_CODE,wr,None,sym['h_memwr'],sym['h_memwr'])
s.cb=lambda s: s.r32(sym['io_cyc'])//280896>1100
s.run(count=30000000000)
