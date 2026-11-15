"""stage 4: record the pad timeline (GBA frame -> pressed mask) of scenes.boot_to_level and the frame at which the level clock starts.  usage: padlog.py ROM OUT.json"""
import sys,os,json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from emu import Emu
import scenes
e=Emu(sys.argv[1]); log=[]
orig=e.run
def run(n=1,keys=None):
    if keys is not None: e.set_keys(keys)
    m=e.keys
    for _ in range(n):
        log.append(m)
        orig(1,None)
    return e
e.run=run
scenes.boot_to_level(e)
# run-length encode: [start,end,mask_pressed]
rl=[]; i=0
while i<len(log):
    j=i
    while j<len(log) and log[j]==log[i]: j+=1
    if log[i]: rl.append([i,j,log[i]])
    i=j
json.dump({'plan':rl,'frames':len(log),'clock':e.r32(0x02001e00)},open(sys.argv[2],'wb') if False else open(sys.argv[2],'w'))
print(rl,len(log),e.r32(0x02001e00))
