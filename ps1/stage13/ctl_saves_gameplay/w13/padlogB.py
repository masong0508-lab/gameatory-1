"""record the pad plan of title -> level with an EXISTING save (slot 1 used): boot a blank game to the level once (creates the profile in the in-memory save), reset, then the stock path without the name screen"""
import sys,json
from common import *
e=Emu(ROM); scenes.boot_to_level(e)
e.reset(); 
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
e.tap('A',6,80)       # Play game -> select slot
e.tap('A',6,60)       # slot 1 (used) -> game menu
e.tap('DOWN'); e.tap('DOWN')
e.tap('A',6,60)       # rampage setup
e.tap('A',6,600)
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
json.dump({'plan':rl,'frames':len(log),'clock':e.r32(0x02001e00)},open('pad_boot_B.json','w'))
print(rl,len(log),e.r32(0x02001e00))
# first frame at which the clock runs
