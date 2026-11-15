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
def rd(uc,a,sz,ud):
    ea=uc.reg_read(UC_MIPS_REG_4)
    if (ea>>24)==0x80 and not (0x8017f000<=ea<0x80180400 or 0x80180000<=ea<0x80200000): pass
    if ea<0x1000 or (0x80<=(ea>>24)<0xff and not(0x8017f000<=ea<0x80200000)):
        ra=uc.reg_read(UC_MIPS_REG_31); print('BADRD ea',hex(ea),'ra',hex(ra),g(ra),'kind',uc.reg_read(UC_MIPS_REG_5))
        print([ (k,hex(x),hex(y),g(y)) for k,x,y in ring[-6:]])
        print([g(x) for x in blk[-3000:]])
        print('regs',[hex(uc.reg_read(r)) for r in range(UC_MIPS_REG_1,UC_MIPS_REG_1+31)])
        cur=s.rd(IW,0x8000); open('out/iw_fail.bin','wb').write(cur)
        cnt[0]+=1
        if cnt[0]>2: uc.emu_stop()
s.u.hook_add(UC_HOOK_CODE,rd,None,sym['h_memrd'],sym['h_memrd'])
s.cb=lambda s: s.r32(sym['io_cyc'])//280896>1030
s.run(count=30000000000)
print(s.out.decode('latin1')[-200:])
