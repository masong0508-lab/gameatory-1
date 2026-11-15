"""plan C: initialised save, no profile.  Boot blank until the title (init writes done), reset, then the stock path WITH the name screen"""
import sys,json
from common import *
e=Emu(ROM)
e.run(300,[])
for i in range(60):
    e.run(30,[])
    if scenes.title_visible(e.frame): break
    if i%2: e.tap('A',6,0)
e.run(60,[])
e.reset()
log=[]; orig=e.run
def run(n=1,keys=None):
    if keys is not None: e.set_keys(keys)
    m=e.keys
    for _ in range(n): log.append(m); orig(1,None)
    return e
e.run=run
e.run(300,[])
for i in range(60):
    e.run(30,[])
    if scenes.title_visible(e.frame): break
    if i%2: e.tap('A',6,0)
else: raise SystemExit('no title')
e.run(60,[])
e.tap('A',6,80); e.tap('A',6,60); e.tap('A',6,60)   # play game, slot, name
e.tap('DOWN'); e.tap('DOWN')
e.tap('A',6,60); e.tap('A',6,600)
for _ in range(3):
    if scenes.in_level(e,0): break
    e.tap('A',6,120)
assert scenes.in_level(e,0),'not in level'
e.run(60,[])
rl=[]; i=0
while i<len(log):
    j=i
    while j<len(log) and log[j]==log[i]: j+=1
    if log[i]: rl.append([i,j,log[i]])
    i=j
json.dump({'plan':rl,'frames':len(log),'clock':e.r32(0x02001e00)},open('pad_boot_C.json','w'))
print(rl,len(log),e.r32(0x02001e00))
