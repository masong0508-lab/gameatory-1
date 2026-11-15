import sys,json
sys.path.insert(0,'w13'); from common import *
plan=json.load(open('out/pad_boot.json'))['plan']
def keys_at(f):
    for a,b,m in plan:
        if a<=f<b: return m
    return 0
KN=['A','B','SELECT','START','RIGHT','LEFT','UP','DOWN','R','L']
def mk(m): return [KN[i] for i in range(10) if m>>i&1]
e=Emu(ROM)
f=0
while f<700:
    e.run(1,mk(keys_at(f))); f+=1
def snap():
    return bytes(e.read(0x02000000,0x40000))+bytes(e.read(0x03000000,0x8000))
import numpy as np
def diff(a,b):
    A=np.frombuffer(a,np.uint8); B=np.frombuffer(b,np.uint8); idx=np.nonzero(A!=B)[0]; return idx
def addr(i): return 0x02000000+i if i<0x40000 else 0x03000000+i-0x40000
e.screenshot('/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/v12/ps1/s15_merge/run/cp0.png')
s0=snap(); e.run(30,[]); s1=snap()   # idle drift
idle=set(addr(i) for i in diff(s0,s1))
print('idle changing bytes',len(idle))
e.tap('DOWN',6,40); s2=snap(); e.screenshot('/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/v12/ps1/s15_merge/run/cp1.png')
d1=[addr(i) for i in diff(s1,s2)]
e.run(30,[]); s2b=snap()
idle2=set(addr(i) for i in diff(s2,s2b))
cand=[a for a in d1 if a not in idle and a not in idle2]
print('Down candidates',len(cand),[hex(a) for a in cand[:60]])
e.tap('UP',6,40); s3=snap(); e.run(30,[]); s3b=snap()
idle3=set(addr(i) for i in diff(s3,s3b))
d2=set(addr(i) for i in diff(s2b,s3))
c2=[a for a in cand if a in d2 and a not in idle3]
print('Up reverts',[(hex(a),s1[a-0x02000000 if a<0x03000000 else 0x40000+a-0x03000000],s2[a-0x02000000 if a<0x03000000 else 0x40000+a-0x03000000],s3[a-0x02000000 if a<0x03000000 else 0x40000+a-0x03000000]) for a in c2])
print('--- sequence')
for k in ['DOWN','DOWN','DOWN','UP','UP','UP','UP']:
    e.tap(k,6,40); print(k,e.r8(0x02001c94),e.r8(0x2001ca5))
