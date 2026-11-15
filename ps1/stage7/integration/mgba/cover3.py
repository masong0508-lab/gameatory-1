"""stage 4 coverage (code only): from power-on through the menus into the level, walk, drive, pause; ROM + IWRAM halfword bitmap -> pickle of (addr,size) like explore coverage.
usage: cover3.py ROM OUT.pkl [seed]"""
import sys,os,ctypes,pickle,random
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from emu import Emu
import scenes
rom,outp=sys.argv[1],sys.argv[2]; seed=int(sys.argv[3]) if len(sys.argv)>3 else 1
e=Emu(rom)
bm=(ctypes.c_uint8*((0x800000+0x8000)//2//8))()
orig=e.run
def run(n=1,keys=None):
    if n==0: return orig(0,keys)
    e.set_keys(keys or []); e.L.gba_cover(e.h,n,bm); e.frames+=n; e._fb=None
e.run=run
scenes.boot_to_level(e)
rnd=random.Random(seed); K=['A','B','SELECT','START','RIGHT','LEFT','UP','DOWN','R','L']
def rkeys():
    ks=[k for k in K if rnd.random()<0.18 and k not in('SELECT','START')]
    if rnd.random()<0.6: ks.append('UP')
    return ks
for ph in range(40):
    if ph==10: e.w16(0x02001db8,6)
    if ph==20: e.w16(0x02001db8,0)
    if ph==26: e.w16(0x02001db8,5)
    for i in range(30): run(30,rkeys())
    if ph%8==7: run(8,['START']); run(40,[]); run(8,['START']); run(40,[])
data=bytes(bm); lst=[]
for h in range(0x400000):
    if data[h>>3]>>(h&7)&1: lst.append((0x08000000+2*h,2))
for h in range(0x4000):
    k=0x400000+h
    if data[k>>3]>>(k&7)&1: lst.append((0x03000000+2*h,2))
pickle.dump(lst,open(outp,'wb'))
print('touched halfwords rom',sum(1 for a,_ in lst if a>>24==8),'iwram',sum(1 for a,_ in lst if a>>24==3),'clock',e.r32(0x02001e00),'map',e.r16(0x02001d40))
