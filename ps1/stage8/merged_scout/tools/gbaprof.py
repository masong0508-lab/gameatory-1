#!/usr/bin/env python3
"""gbaprof.py ROM ELF OUT.json : mGBA (libmgba, emulator-only, GBA side) busy-cycle profile of the merged ROM in the standard scenes:
city on foot, Arwing low, Arwing climbing (planet), higher (space).  Reports, per scene, busy share of a 280896-cycle frame and the split by
function (SF functions from the ELF symbols, Payback by nearest discovered entry)."""
import sys,os,json,ctypes,bisect,collections
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,os.path.join(HERE,'..','mg')); sys.path.insert(0,HERE)
from emu import Emu
import scenes,elfsyms,numpy as np
rom,elf,outj=sys.argv[1:4]
OWN=elfsyms.owners(os.path.dirname(elf))
e=Emu(rom,elf); L=e.L
L.gba_pcprof.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
SBINS={}
COV=np.zeros((0x400000+0x4000)//8+16,np.uint8); SCOV={}
fs,secs,_=elfsyms.load(elf)
fs=sorted(fs); fa=[f[0] for f in fs]
import pickle
sys.path.insert(0,os.path.join(HERE,'..'))
P=pickle.load(open(os.path.join(HERE,'..','out','prog_pb.pkl'),'rb')); pe=sorted(a for a in P.entries if a>>24==8)
def name(pc):
    if pc>>24==3:
        for hn,(ha,hs) in secs.items():
            if hn.startswith('.hot') and ha<=pc<ha+hs:
                k=bisect.bisect_right(fa,pc)-1
                return 'IW SF %s'%(fs[k][2] if k>=0 else hn)
        return 'IW Payback/other'
    if 0x081b0000<=pc<0x08244e8c:
        k=bisect.bisect_right(fa,pc)-1
        return 'SF '+(fs[k][2] if k>=0 else '?')
    k=bisect.bisect_right(pe,pc)-1
    return 'PB %08x'%pe[k] if k>=0 else 'PB ?'
def modname(n):
    return n
def prof(frames,nm='x'):
    cv=np.zeros_like(COV); k0=e.r32(e.S['key_calls']); v0=e.r32(e.S['frame_count'])
    bins=np.zeros(0x202001,np.uint64); tot=np.zeros(4,np.uint64)
    L.gba_pcprof(e.h,frames,bins.ctypes.data,tot.ctypes.data,cv.ctypes.data); SCOV[nm]=cv; COV[:]|=cv
    busy=int(tot[1]); idle=int(tot[0]); fr=int(tot[2]); arm=int(tot[3])
    nz=np.nonzero(bins)[0]; agg=collections.Counter(); SBINS[nm]=(nz.copy(),bins[nz].copy(),fr)
    for i in nz:
        i=int(i)
        pc=0x08000000+(i<<4) if i<0x200000 else 0x03000000+((i-0x200000)<<2) if i<0x202000 else 0
        agg[name(pc) if pc else 'other']+=int(bins[i])
    dk=e.r32(e.S['key_calls'])-k0; dv=e.r32(e.S['frame_count'])-v0
    iwb=collections.Counter()
    for i in nz:
        i=int(i)
        if 0x200000<=i<0x202000: iwb[0x03000000+((i-0x200000)<<2)&~0x7f]+=int(bins[i])
    mods=collections.Counter()
    for k,v in agg.items():
        if k.startswith('IW SF'): mods['SF raster/hot ARM (IWRAM)']+=v
        elif k.startswith('SF '): mods['SF Thumb: '+OWN.get(k[3:],'?')]+=v
        elif k.startswith('IW'): mods['Payback IWRAM (mixer, IRQ, ARM code)']+=v
        elif k.startswith('PB'): mods['Payback ROM Thumb']+=v
        else: mods[k]+=v
    return dict(iw_blocks=[('%08x'%k,v/fr) for k,v in iwb.most_common(14)],mods=[(k,v/fr) for k,v in mods.most_common()],vbl=dv,ticks=dk,vpt=(dv/dk if dk else None),frames=fr,arm_pct=100.0*arm/max(1,busy),halt_steps_per_frame=idle/fr,busy_per_frame=busy/fr,idle_per_frame=idle/fr,busy_pct=100.0*busy/(busy+idle) if busy+idle else 0,top=[(k,v/fr) for k,v in agg.most_common(25)],
                sf=sum(v for k,v in agg.items() if k.startswith('SF') or k.startswith('IW SF'))/fr,pb=sum(v for k,v in agg.items() if k.startswith('PB') or k=='IW Payback/other')/fr)
res={}
def scene(nm,frames=120):
    r=prof(frames,nm); r['mode']=scenes.mode(e); r['r_polys']=e.r32(e.S['r_polys']) if 'r_polys' in e.S else None; res[nm]=r
    print('%-14s %.0f guest insns/frame (SF %.0f, Payback %.0f; ARM-state %.1f%%) halt steps/frame %.0f vbl/tick %s mode=%s polys=%s'%(nm,r['busy_per_frame'],r['sf'],r['pb'],r['arm_pct'],r['halt_steps_per_frame'],r.get('vpt'),r['mode'],r['r_polys']),flush=True)
    e.screenshot(os.path.join(HERE,'..','out','shot_%s.png'%nm,),2)

import struct
MAGIC=0x42443253
def mb(cmd,arg=0,frames=40):
    a=e.S['s2_dbg']; seq=e.r32(a+12)
    e.w8(a+4,cmd&255); e.w8(a+5,cmd>>8); e.w8(a+6,arg&255); e.w8(a+7,arg>>8); e.w32(a,MAGIC)
    for _ in range(frames):
        e.run(1)
        if e.r32(a+12)!=seq: return e.r32(a+8)
    return None
def setv(a,v):
    for k,x in enumerate(v): e.w32(a+4*k,x&0xffffffff)
def s32(a): return e.s32(a)
scenes.boot_to_level(e); print('in level, clock',scenes.clock(e),flush=True)
scenes.walk(e,60)
scene('city_foot')
ok=scenes.arwing(e); print('arwing',ok,flush=True)
scene('arwing_low')
B=e.S['ship']; 
print('ship y',s32(B+4)>>8)
for arg in (400,1000,1600,2600):
    print('alt cmd',arg,mb(83,arg),flush=True); e.run(40,[]); print('  ship y',s32(B+4)>>8,flush=True)
    scene('air_alt%d'%arg,90)
# dock at the station
sx,sy,sz=[s32(e.S['station_pos']+4*i) for i in range(3)]
print('station at',sx,sy,sz)
e.run(5,[])
setv(B,((sx+3000)<<8,(sy-140)<<8,(sz+9000)<<8)); setv(B+12,(0,0,-(90<<8))); setv(B+24,(-16384,0,0)); setv(B+36,(0,16384,0)); setv(B+48,(0,0,-16384))
e.run(20,['A']); e.run(40,['SELECT'])
for k in range(30):
    e.run(30,[])
    if e.r32(e.S['sg_state'])==2: break
print('sg_state',e.r32(e.S['sg_state']),flush=True)
scene('near_station',60) if e.r32(e.S['sg_state'])!=2 else None
if e.r32(e.S['sg_state'])==2:
    scene('hangar',90)
    mb(32); e.run(30,[])
    for rid in (1,2,4,6):
        mb(34,rid); e.run(20,[]); scene('station_room%d'%rid,90)
json.dump(res,open(outj,'w'),indent=1)
pickle.dump(SCOV,open(os.path.join(HERE,'..','out','scene_cov.pkl'),'wb'))
pickle.dump(SBINS,open(os.path.join(HERE,'..','out','scene_bins.pkl'),'wb'))
