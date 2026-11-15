import sys,json
sys.path.insert(0,'w13'); from common import *
plan=json.load(open(sys.argv[1]))['plan']
def keys_at(f):
    for a,b,m in plan:
        if a<=f<b: return m
    return 0
KN=['A','B','SELECT','START','RIGHT','LEFT','UP','DOWN','R','L']
def mk(m): return [KN[i] for i in range(10) if m>>i&1]
e=Emu(ROM); f=0
ends=[b for a,b,m in plan]; starts=[a for a,b,m in plan]
last=max(ends)+10
while f<last:
    if f in starts or f in ends:
        i=starts.index(f) if f in starts else -1
        print('f',f,'start' if f in starts else 'end','mask',[m for a,b,m in plan if a==f or b==f],'cur',e.r8(0x03007e68),'clk',e.r32(0x02001e00))
    e.run(1,mk(keys_at(f))); f+=1
print('final clk',e.r32(0x02001e00))
