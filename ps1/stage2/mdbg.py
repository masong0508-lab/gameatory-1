import sys
sys.argv=['x','../../../roms/Payback (Europe) (En,Fr,De,Es,It).gba','out/pr','P','100','1']
src=open('lockstep2.py').read().split("t0=time.time()")[0]
exec(src)
ring=[]
def h(uc,a,sz,ud):
    ring.append((a,uc.reg_read(UC_MIPS_REG_28),uc.reg_read(UC_MIPS_REG_31),uc.reg_read(UC_MIPS_REG_2)))
    if len(ring)>60: ring.pop(0)
M.u.hook_add(UC_HOOK_CODE,h)
try: M.u.emu_start(gmap[0x08000000],0,count=4000000000)
except Exception as e: print(e)
import bisect
from mips import dis
for a,gp,ra,v0 in ring: 
    w=int.from_bytes(M.u.mem_read(a&0x1fffffff,4),'little') if a else 0
    print(hex(a),dis(w,a),'gp',hex(gp),'ra',hex(ra),'v0',hex(v0))
print('misses',[hex(x) for x in M.misses],'lr',[hex(M.r(k)) for k in (31,15,16,17,25)])
