import sys,os,struct,ctypes,bisect,collections,pickle
sys.path.insert(0,'.')
from emu import Emu
import scenes, numpy as np
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/'
e=Emu(SP+'roms/Payback (Europe) (En,Fr,De,Es,It).gba')
scenes.boot_to_level(e)
bm=(ctypes.c_uint8*(0x800000//2//8))()
def cover(n,keys): 
    e.set_keys(keys); e._L=e.L; e.L.gba_cover(e.h,n,bm)
def pad_plan(n,plan,step=40):
    for i in range(0,n,step): cover(step,plan[(i//step)%len(plan)])
# walking, punching
pad_plan(400,[['UP'],['UP','LEFT'],['UP'],['UP','RIGHT'],['A'],['A'],['DOWN'],['LEFT']])
# switch to car 6 and drive
e.w16(0x02001db8,6)
pad_plan(500,[['UP'],['UP','LEFT'],['UP'],['UP','RIGHT'],['UP'],['A'],['DOWN'],['UP','LEFT'],['R'],['UP','RIGHT']])
# pause menu and back
cover(8,['START']); cover(60,[]); cover(8,['START']); cover(60,[])
data=bytes(bm); pickle.dump(data,open(SP+'v12/ps1/stage3/cover_inlevel.pkl','wb'))
print('touched halfwords',sum(bin(b).count('1') for b in data))
