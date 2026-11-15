import sys,bisect
sys.argv=['x','../../../roms/Payback (Europe) (En,Fr,De,Es,It).gba','out/pr','P','400','1']
src=open('lockstep2.py').read().split("t0=time.time()")[0]
exec(src)
M.stoperr=True
M.u.emu_start(gmap[0x08000000],0,count=4000000000)
print('errs',M.errs,'ticks',iom.nd)
from mips import dis
ra=M.r(28)
for k in range(4):
    w=int.from_bytes(M.u.mem_read((ra+4*k)&0x1fffffff,4),'little'); print(hex(ra+4*k),dis(w,ra+4*k))
w=int.from_bytes(M.u.mem_read((ra+4)&0x1fffffff,4),'little'); tgt=((ra+8)&0xf0000000)|((w&0x3ffffff)<<2)
hs=sorted((h,g) for g,h in gmap.items()); j=bisect.bisect_right([h for h,g in hs],tgt)-1
print('done label',hex(tgt),'guest ~',hex(hs[j][1]))
print('regs',[hex(M.r(k)) for k in range(16,24)])
