"""TEST-ONLY: record the pad plan for 'title -> Play single player game -> story city C level L -> start'.  usage: padstory.py ROM C L OUT.json"""
import sys,os,json,struct
sys.path.insert(0,'mgba'); sys.dont_write_bytecode=True
from emu import Emu
import scenes
ROM=sys.argv[1]; C=int(sys.argv[2]); L=int(sys.argv[3]); OUT=sys.argv[4]
POKE0=900
e=Emu(ROM); log=[]
orig=e.run
def run(n=1,keys=None):
    if keys is not None: e.set_keys(keys)
    m=e.keys
    for _ in range(n):
        log.append(m)
        if len(log)>=POKE0 and e.r32(0x02001e00)==0:
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
e.run(max(0,POKE0+30-len(log)),[])
e.tap('A',6,120)
for _ in range(C): e.tap('RIGHT',6,40)
for _ in range(L): e.tap('DOWN',6,30)
for k in range(12):
    e.tap('A',6,90)
    if e.r32(0x02001e00)>0: break
for k in range(40):
    e.run(60,[])
    if e.r32(0x02001e00)>0: break
e.run(60,[])
print('C',C,'L',L,'PB_MAP',e.r16(0x02001d40),'1e66',e.r16(0x02001e66),'clock',e.r32(0x02001e00),'frames',len(log))
e.screenshot(OUT.replace('.json','.png'))
rl=[]; i=0
while i<len(log):
    j=i
    while j<len(log) and log[j]==log[i]: j+=1
    if log[i]: rl.append([i,j,log[i]])
    i=j
json.dump({'plan':rl,'frames':len(log),'clock':e.r32(0x02001e00),'map':e.r16(0x02001e66),'poke0':POKE0},open(OUT,'w'))
print(rl)
