from common import *
import time
e=Emu(ROM); scenes.boot_to_level(e)
st0=e.save_state(); tab=0x03000c60
t0=time.time()
def defidx(e,q):
    dp=e.r32(q+0x1c); return (dp-0x08354af4)//0x3c if 0x08354af4<=dp<0x08354af4+128*0x3c else -1
hits=[]
for ci_car in (1,2,4,5,6,8,9):
    for off in (60,120,200):
        for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
            e.load_state(st0)
            q=e.r32(tab+4*ci_car); cx=s32(e.r32(q+4)); cz=s32(e.r32(q+8)); chd=s16(e.r16(q+0x12))
            p=e.r32(tab+0); e.w32(p+4,(cx+dx*off)&0xffffffff); e.w32(p+8,(cz+dz*off)&0xffffffff)
            e.run(1,[])
            ok=False; info=None
            for k in range(8):
                e.run(2,['L']); e.run(3,[])
                s=state(e)
                if s['ci']!=0 or defidx(e,e.r32(tab+4*s['ci']))!=49:
                    ok=True; info=(s['ci'],defidx(e,e.r32(tab+4*s['ci']))); break
            if ok: hits.append((ci_car,off,dx,dz,info)); print('HIT',ci_car,off,dx,dz,info,flush=True)
print('done',time.time()-t0,'hits',hits)
