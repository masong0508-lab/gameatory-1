#!/usr/bin/env python3 -I
"""remksf3m.py: rebuild SF3M.BIN from existing per-map files (sf3m/m<N>/WORLD.SFW, SF3A.BIN, SIDE.BIN + manifest.json) with the stage 7c mksf3.py (loops kept in SF3W).
usage: remksf3m.py SF3M_DIR   (rewrites m<N>/SF3W.BIN, SF3M.BIN and manifest.json).  Derived from the player's ROM: build output only, never committed."""
import sys,os,struct,subprocess,json
d=sys.argv[1]; here=os.path.dirname(os.path.abspath(__file__)); man=json.load(open(d+'/manifest.json'))
pad=lambda b:b+b'\0'*((-len(b))%2048)
hdr=struct.pack('<4sI',b'SF3M',11); body=b''; sec=1
for n in range(11):
    w=d+'/m%d'%n
    subprocess.run([sys.executable,'-I',here+'/mksf3.py',w,w],check=True,stdout=subprocess.DEVNULL)
    parts=[open(w+'/SF3W.BIN','rb').read(),open(w+'/SF3A.BIN','rb').read(),open(w+'/SIDE.BIN','rb').read()]
    sd=man[n]['s']; assert len(parts[2])==sd,(n,len(parts[2]),sd)
    hdr+=struct.pack('<8I',sec,len(parts[0])//2048,len(parts[1])//2048,len(parts[2]),*man[n]['start'],0)
    for p in parts: body+=pad(p); sec+=len(pad(p))//2048
    man[n]['w']=len(parts[0])
open(d+'/SF3M.BIN','wb').write(pad(hdr)+body); json.dump(man,open(d+'/manifest.json','w')); print('SF3M.BIN sectors',sec)
