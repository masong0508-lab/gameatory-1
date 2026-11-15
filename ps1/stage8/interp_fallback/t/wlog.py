import sys,struct,bisect
sys.path.insert(0,'t')
from sim4 import *
from unicorn.mips_const import *
V,PRD,LO,HI,F0,F1=sys.argv[1],sys.argv[2],int(sys.argv[3],16),int(sys.argv[4],16),int(sys.argv[5]),int(sys.argv[6])
s=Sim('out/%s.exe'%V,'out/%s.iso'%V,'out/bld_%s/payback.elf'%V); sym=s.sym; CY=sym['io_cyc']
mm=[]
for l in open('out/%s/payback_P.map'%PRD):
    a,h=l.split(); mm.append((int(h,16),int(a,16)))
mm.sort(); hs=[h for h,_ in mm]
def g(h):
    if h<0x80030000: return 'C%x'%h
    j=bisect.bisect_right(hs,h)-1; return 'g%08x'%mm[j][1]
log=[]; st=dict(on=False)
def mw(uc,acc,a,sz,v,ud):
    if st['on']: log.append('%x sz%d v=%08x pc=%08x(%s) ra=%08x(%s) f=%d'%(a,sz,v&0xffffffff,uc.reg_read(UC_MIPS_REG_PC),g(uc.reg_read(UC_MIPS_REG_PC)),uc.reg_read(UC_MIPS_REG_31),g(uc.reg_read(UC_MIPS_REG_31)),s.r32(CY)//280896))
s.u.hook_add(UC_HOOK_MEM_WRITE,mw,None,LO,HI)
def cb(s):
    f=s.r32(CY)//280896
    if f>=F0: st['on']=True
    return f>=F1
s.cb=cb; s.run(count=40000000000)
open("logs/wlog_%s_%s.txt"%(V,sys.argv[7] if len(sys.argv)>7 else "x"),'w').write('\n'.join(log)); print(V,len(log),'writes')
