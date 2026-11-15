from common import *
import time,math
e=Emu(ROM); scenes.boot_to_level(e)
st0=e.save_state(); tab=0x03000c60
def defidx(e,q):
    dp=e.r32(q+0x1c); return (dp-0x08354af4)//0x3c if 0x08354af4<=dp<0x08354af4+128*0x3c else -1
# are cars parked?
a=[(s32(e.r32(e.r32(tab+4*i)+4)),s32(e.r32(e.r32(tab+4*i)+8))) for i in range(11)]
e.run(300,[])
b=[(s32(e.r32(e.r32(tab+4*i)+4)),s32(e.r32(e.r32(tab+4*i)+8))) for i in range(11)]
print('moved in 300 frames',[(i,math.hypot(b[i][0]-a[i][0],b[i][1]-a[i][1])) for i in range(11)])
hits=[]
for ci_car in (1,2,4,5,6,8,9):
    for off in (150,300,500):
        for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
            e.load_state(st0)
            q=e.r32(tab+4*ci_car); cx=s32(e.r32(q+4)); cz=s32(e.r32(q+8))
            px,pz=cx+dx*off,cz+dz*off
            p=e.r32(tab+0); e.w32(p+4,px&0xffffffff); e.w32(p+8,pz&0xffffffff)
            hd=int(math.atan2(cx-px,cz-pz)/(2*math.pi)*5760)%5760; e.w16(p+0x12,hd)
            e.run(1,[])
            for k in range(12):
                e.run(3,['A','L']); 
                s=state(e)
                if s['ci']!=0 or defidx(e,e.r32(tab+4*s['ci']))!=49:
                    hits.append((ci_car,off,dx,dz,(s['ci'],defidx(e,e.r32(tab+4*s['ci'])),k))); print('HIT',hits[-1],flush=True); break
print('hits',hits)
