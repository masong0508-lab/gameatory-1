import sys,collections
sys.argv=['x','../../../roms/Payback (Europe) (En,Fr,De,Es,It).gba','out/pr','P','300','1']
src=open('lockstep2.py').read().split("t0=time.time()")[0]
exec(src)
cnt=collections.Counter(); sites=collections.Counter()
orig=M._memrd
def hk(uc,addr,sz,ud):
    ea=uc.reg_read(UC_MIPS_REG_24); cnt[(ea-M.ioh) if M.ioh<=ea<M.ioh+0x400 else ('rom' if ea>>24 in(8,10,12) else 'other')]+=1
    sites[uc.reg_read(UC_MIPS_REG_28)]+=1
M.u.hook_add(UC_HOOK_CODE,hk,None,gmap and meta['rt']['RT_MEMRD'],meta['rt']['RT_MEMRD'])
M.u.emu_start(gmap[0x08000000],0,count=4000000000)
print(iom.nd,{(hex(k) if isinstance(k,int) else k):v for k,v in cnt.most_common(8)})
print([(hex(a),c) for a,c in sites.most_common(5)])
