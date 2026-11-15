import sys,os,struct,ctypes,bisect,collections,pickle,random
sys.path.insert(0,'.')
from emu import Emu
import scenes
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/'
e=Emu(SP+'roms/Payback (Europe) (En,Fr,De,Es,It).gba')
bm=(ctypes.c_uint8*(0x800000//2//8))()
orig=e.run
cov_on=[False]
def run(n=1,keys=None):
    if not cov_on[0]: return orig(n,keys)
    if n==0: return orig(0,keys)
    e.set_keys(keys or []); e.L.gba_cover(e.h,n,bm); orig(0,keys)
e.run=run
tv=scenes.title_visible
def tv2(f):
    r=tv(f)
    if r: cov_on[0]=True
    return r
scenes.title_visible=tv2
scenes.boot_to_level(e)
seed=int(sys.argv[1]) if len(sys.argv)>1 else 1
rnd=random.Random(seed)
K=['A','B','SELECT','START','RIGHT','LEFT','UP','DOWN','R','L']
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
data=bytes(bm); pickle.dump(data,open(SP+'v12/ps1/stage3/cover_full_%d.pkl'%seed,'wb'))
print('touched halfwords',sum(bin(b).count('1') for b in data),'clock',e.r32(0x02001e00),'lives',e.r16(0x02001e4e),'map',e.r16(0x02001d40))
