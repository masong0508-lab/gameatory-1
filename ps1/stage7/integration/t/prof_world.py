#!/usr/bin/env python3
"""EMULATOR-ONLY (mGBA, original Payback ROM given on the command line, nothing stored): GBA cycle cost of Payback's world renderer 0x0800adac in a live level.
usage: prof_world.py ROM [frames_per_phase]"""
import sys,os,ctypes,random
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','mgba'))
from emu import Emu
import scenes
rom=sys.argv[1]; N=int(sys.argv[2]) if len(sys.argv)>2 else 300
e=Emu(rom); scenes.boot_to_level(e)
rnd=random.Random(3); K=['A','B','RIGHT','LEFT','UP','DOWN','R','L']
BK=(ctypes.c_uint64*0x20700)()
def phase(name,idx):
    if idx is not None: e.w16(0x02001db8,idx)
    tot=0; idle=0; el=0; calls=0; mx=0; fmax=0; fr=0
    for blk in range(N//30):
        ks=[k for k in K if rnd.random()<0.18]+['UP']
        e.set_keys(ks); out=(ctypes.c_uint64*7)()
        e.L.gba_prof(e.h,30,0x0800adac,out,BK)
        calls+=out[0]; tot+=out[1]; idle+=out[5]; el+=out[6]; mx=max(mx,out[2]); fmax=max(fmax,out[4]); fr+=out[3]
    print('%-6s frames %d calls %d  busy cycles/frame %.0f (%.1f%% of a 280896-cycle frame = %.0f scanlines), halted inside calls %.0f/frame, elapsed inside %.0f/frame, avg busy per call %.0f cycles = %.1f ms at 16.78 MHz, max busy per call %d, busiest frame %d'%(name,fr,calls,tot/fr,100*tot/fr/280896,tot/fr/1232,idle/fr,el/fr,tot/max(calls,1),1000*tot/max(calls,1)/16777216,mx,fmax))
phase('foot',None); phase('car',6); phase('walk2',0)
print('clock',e.r32(0x02001e00))

tot=sum(BK); top=sorted(range(len(BK)),key=lambda i:-BK[i])[:10]
print('where the cycles inside the calls go (64-byte buckets, %% of elapsed inside calls):')
for i in top: print('  %s %.1f%%'%(hex(0x08000000+(i<<6)) if i<0x20000 else ('IWRAM '+hex(0x03000000+((i-0x20000)<<6)) if i<0x20600 else 'other'),100*BK[i]/tot))
