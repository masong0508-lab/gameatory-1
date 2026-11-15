from common import *
import time,math
e=Emu(ROM); scenes.boot_to_level(e)
st0=e.save_state(); tab=0x03000c60
def defidx(e,q):
    dp=e.r32(q+0x1c); return (dp-0x08354af4)//0x3c if 0x08354af4<=dp<0x08354af4+128*0x3c else -1
def me(e):
    s=state(e); q=e.r32(tab+4*s['ci']); return dict(ci=s['ci'],idx=defidx(e,q),cls=s.get('cls'),x=s['x'],z=s['z'],hd=s['hd'],hp=s['hp'])
def go(carc,off,dx,dz):
    e.load_state(st0)
    q=e.r32(tab+4*carc); cx=s32(e.r32(q+4)); cz=s32(e.r32(q+8)); px,pz=cx+dx*off,cz+dz*off
    p=e.r32(tab+0); e.w32(p+4,px&0xffffffff); e.w32(p+8,pz&0xffffffff)
    e.w16(p+0x12,int(math.atan2(cx-px,cz-pz)/(2*math.pi)*5760)%5760); e.run(1,[])
    for k in range(12):
        e.run(3,['A','L'])
        m=me(e)
        if m['idx']!=49: return k,m
    return None,me(e)
for args in ((6,500,-1,0),(6,300,-1,0),(8,500,0,1),(9,500,0,-1)):
    k,m=go(*args); print('case',args,'enter at',k,m,flush=True)
    if k is None: continue
    e.run(4,[]); print('  settled',me(e))
    for name,keys,n in (('drive A',['A'],60),('left',['A','LEFT'],40),('right',['A','RIGHT'],40),('brake B',['B'],40),('idle',[],20),('exit L',['L'],10),('after',[],30)):
        a=me(e); e.run(n,keys); b=me(e)
        print('  %-8s d=%6d dhd=%5d cls %s->%s idx %s->%s ci %d->%d'%(name,math.hypot(b['x']-a['x'],b['z']-a['z']),((b['hd']-a['hd']+2880)%5760)-2880,a['cls'],b['cls'],a['idx'],b['idx'],a['ci'],b['ci']),flush=True)
