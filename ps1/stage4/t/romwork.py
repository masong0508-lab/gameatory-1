import sys; sys.path.insert(0,'t')
from sim4 import *
s=Sim('out/s4t.exe','out/s4t.iso','out/bld_s4t/payback.elf')
pages={}; tl=[]
def hm(uc,a,sz,ud):
    ea=uc.reg_read(UC_MIPS_REG_4)
    if (ea>>24) in (8,10,12): pages[(ea&0x1ffffff)>>12]=pages.get((ea&0x1ffffff)>>12,0)+1
s.u.hook_add(UC_HOOK_CODE,hm,None,s.sym['h_memrd'],s.sym['h_memrd'])
N=int(sys.argv[2])
def cb(s):
    tl.append((s.vbl,len(pages)))
    return s.vbl>N
s.cb=cb
s.run(count=int(sys.argv[1]))
print('vbl',s.vbl,'distinct 4K rom pages',len(pages),'reads',sum(pages.values())); print(tl[::max(1,len(tl)//12)])
import pickle; pickle.dump(pages,open('out/rom_pages_level.pkl','wb'))
print(s.out.decode('latin1')[-300:])
