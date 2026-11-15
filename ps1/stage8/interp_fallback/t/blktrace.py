import sys,struct,bisect,subprocess
sys.path.insert(0,'t')
from sim4 import *
from unicorn.mips_const import *
# usage: blktrace.py V PRD F0 WADDR WVAL NBLK  : after the second..first write of WVAL to physical WADDR at frame>=F0, log NBLK blocks, annotated
V,PRD,F0,WA,WV,NB=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4],16),int(sys.argv[5],16),int(sys.argv[6])
s=Sim('out/%s.exe'%V,'out/%s.iso'%V,'out/bld_%s/payback.elf'%V); sym=s.sym; CY=sym['io_cyc']
mm=[]
for l in open('out/%s/payback_P.map'%PRD):
    a,h=l.split(); mm.append((int(h,16),int(a,16)))
mm.sort(); hs=[h for h,_ in mm]
nm=subprocess.run(['llvm-nm','-n','out/bld_%s/payback.elf'%V],capture_output=True,text=True).stdout.split('\n')
sy=sorted((int(l.split()[0],16),l.split()[2]) for l in nm if len(l.split())==3); sa=[a for a,_ in sy]
def ann(h):
    if h<0x80030000 or 0x800d4000<=h<0x80100000 and False:
        j=bisect.bisect_right(sa,h)-1; return '%s+%x'%(sy[j][1],h-sy[j][0])
    if h>=0x80030000 and h<0x80030400: return 'RT%x'%h
    j=bisect.bisect_right(hs,h)-1; return 'g%08x+%x'%(mm[j][1],h-mm[j][0])
st=dict(on=False,n=0,f=0,hits=0); log=[]
def mw(uc,acc,a,sz,v,ud):
    if st['f']>=F0 and not st['on'] and (v&0xffffffff)==WV: st['on']=True
def blk(uc,a,sz,ud):
    if st['on'] and st['n']<NB: st['n']+=1; log.append(ann(a)+' ra=%x'%uc.reg_read(UC_MIPS_REG_31))
    elif st['on'] and st['n']>=NB: uc.emu_stop()
def hm(uc,a,sz,ud):
    if st['on']: log.append('H_MISS target=%08x ra=%x'%(uc.reg_read(UC_MIPS_REG_4),uc.reg_read(UC_MIPS_REG_31)))
s.u.hook_add(UC_HOOK_CODE,hm,None,sym['h_miss'],sym['h_miss'])
s.u.hook_add(UC_HOOK_MEM_WRITE,mw,None,WA,WA+3); s.u.hook_add(UC_HOOK_BLOCK,blk)
def cb(s): st['f']=s.r32(CY)//280896; return False
s.cb=cb; s.run(count=40000000000)
print('\n'.join(log))
