import sys,json
sys.path.insert(0,'w13'); from common import *
plan=json.load(open('out/pad_boot.json'))['plan']
def keys_at(f):
    for a,b,m in plan:
        if a<=f<b: return m
    return 0
KN=['A','B','SELECT','START','RIGHT','LEFT','UP','DOWN','R','L']
def mk(m): return [KN[i] for i in range(10) if m>>i&1]
e=Emu(ROM); f=0
while f<700: e.run(1,mk(keys_at(f))); f+=1
def snap(): return bytes(e.read(0x02000000,0x40000))+bytes(e.read(0x03000000,0x8000))
S=[snap()]
for k in ['DOWN']*5+['UP']*2:
    e.tap(k,6,40); S.append(snap())
import numpy as np
A=[np.frombuffer(s,np.uint8) for s in S]
# bytes that take values v0,v0+1,... for Down presses
for i in range(len(A[0])):
    seq=[int(a[i]) for a in A]
    if seq[0]==0 and seq[1:6]==[1,2,3,4,5] and seq[6]==4 and seq[7]==3:
        a=0x02000000+i if i<0x40000 else 0x03000000+i-0x40000; print('exact',hex(a),seq)
    elif len(set(seq))>2 and all(seq[j+1]-seq[j] in (1,) for j in range(5)):
        a=0x02000000+i if i<0x40000 else 0x03000000+i-0x40000; print('mono',hex(a),seq)
