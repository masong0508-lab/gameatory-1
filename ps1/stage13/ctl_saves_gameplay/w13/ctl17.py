from common import *
import sys,math
e=Emu(ROM); scenes.boot_to_level(e)
st0=e.save_state()
def cars(e):
    return [x for x in ents(e) if x[1]==0]
print('level state',state(e)); cs=cars(e); print('cars',len(cs),cs[:6])
me=state(e); print('me',me)
tab=0x03000c60
def pokepos(e,x,z):
    p=e.r32(tab+4*state(e)['ci']); e.w32(p+4,x&0xffffffff); e.w32(p+8,z&0xffffffff)
res=[]
for (i,cls,cx,cz,hd,idx) in cs[:8]:
    for off in (300,700,1200):
        e.load_state(st0)
        q=e.r32(tab+4*i); cxr=s32(e.r32(q+4)); czr=s32(e.r32(q+8))
        pokepos(e,cxr+off*2,czr)    # raw units are double the >>1 units
        e.run(3,[])
        before=state(e)
        for k in range(4):
            e.run(8,['L']); e.run(10,[])
            s=state(e)
            if s['ci']!=before['ci'] or s.get('cls')!=before.get('cls'): break
        s=state(e)
        print('car',i,'def',idx,'off',off,'ci',before['ci'],'->',s['ci'],'cls',before.get('cls'),'->',s.get('cls'),'clk',s['clk'],flush=True)
        res.append((i,off,s['ci']!=before['ci']))
print('ENTERED',[r for r in res if r[2]])
