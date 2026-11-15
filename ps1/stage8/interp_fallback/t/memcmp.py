#!/usr/bin/env python3
"""compare two simlog memory dumps (EWRAM 256K, IWRAM 32K, PAL 2x1K, VRAM 96K) word by word: classes = identical, pointer-form (raw GBA address vs host address of the same location), code-address (host vs guest return address / host vs host),
other (real divergence).  usage: memcmp.py A.bin B.bin"""
import sys,struct
a=open(sys.argv[1],'rb').read(); b=open(sys.argv[2],'rb').read()
def mp(v):
    if v-0x02000000<=0x40000: return 0x801b0000+v-0x02000000
    if v-0x03000000<0x01000000: return 0x801f0000+(v&0x7fff)
    return v
names=[(0,0x40000,'EWRAM'),(0x40000,0x8000,'IWRAM'),(0x48000,0x800,'PAL'),(0x48800,0x18000,'VRAM')]
def reg(o):
    for s,n,nm in names:
        if s<=o<s+n: return nm
cnt={'ptr':0,'code':0,'other':0}; other=[]
for o in range(0,len(a),4):
    x,y=struct.unpack_from('<I',a,o)[0],struct.unpack_from('<I',b,o)[0]
    if x==y: continue
    if mp(x)==mp(y): cnt['ptr']+=1
    elif (x>>24 in (0x80,0x08,0x03,0x02)) and (y>>24 in (0x80,0x08,0x03,0x02)) and ((x>>24)==0x80 or (y>>24)==0x80) and ((x>>24)==8 or (y>>24)==8 or (x>>24)==0x80 and (y>>24)==0x80): cnt['code']+=1
    else: cnt['other']+=1; other.append((o,x,y))
print(cnt)
for o,x,y in other[:40]: print(reg(o),hex(o),'%08x %08x'%(x,y))
