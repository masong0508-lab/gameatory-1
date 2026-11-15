"""TEST-ONLY: record the pad plan for 'title -> rampage setup -> city K -> play' and replay-verify.  usage: padcity.py ROM K OUT.json"""
import sys,os,json
sys.path.insert(0,'mgba'); sys.dont_write_bytecode=True
from emu import Emu
import scenes
ROM=sys.argv[1]; K=int(sys.argv[2]); OUT=sys.argv[3]
POKE0=900
e=Emu(ROM); log=[]
orig=e.run
def run(n=1,keys=None):
    if keys is not None: e.set_keys(keys)
    m=e.keys
    for _ in range(n):
        log.append(m)
        if K>0 and len(log)>=POKE0 and e.r32(0x02001e00)==0:
            for i in range(16): e.w16(0x020026d0+2*i,5)
        orig(1,None)
    return e
e.run=run
e.run(300,[])
for i in range(60):
    e.run(30,[])
    if scenes.title_visible(e.frame): break
    if i%2: e.tap('A',6,0)
e.run(60,[])
e.tap('A',6,80); e.tap('A',6,60); e.tap('A',6,60)
e.tap('DOWN'); e.tap('DOWN')
e.tap('A',6,60)       # rampage setup
if K>0:
    e.tap('UP',6,30); e.tap('UP',6,30)
    for _ in range(K): e.tap('RIGHT',6,30)
    e.tap('DOWN',6,30); e.tap('DOWN',6,30)
e.tap('A',6,600)
for _ in range(3):
    if e.r32(0x02001e00)>0: break
    e.tap('A',6,120)
f0=len(log)
e.run(60,[])
print('K',K,'map',e.r16(0x02001d40),'clock',e.r32(0x02001e00),'frames',len(log))
e.screenshot(OUT.replace('.json','.png'))
rl=[]; i=0
while i<len(log):
    j=i
    while j<len(log) and log[j]==log[i]: j+=1
    if log[i]: rl.append([i,j,log[i]])
    i=j
json.dump({'plan':rl,'frames':len(log),'clock':e.r32(0x02001e00),'map':e.r16(0x02001d40),'poke0':POKE0 if K>0 else 0},open(OUT,'w'))
print(rl)
