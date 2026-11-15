#!/usr/bin/env python3
"""pcxboot.py disc.cue home out [max_s]: boot a Payback PS1 disc in PCSXR (EMULATOR-ONLY, HLE BIOS) with the memory card the HOME holds and no key input at all; reports which menu-assist plan the runtime chose
and when the level clock first runs (first GS line).  Used for the 'existing save' boot test."""
import sys,os,time,re
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import pcx
cue,home,out=sys.argv[1:4]; MAXS=int(sys.argv[4]) if len(sys.argv)>4 else 1500
r=pcx.Run(cue,home,out); t0=time.time()
try:
    l=r.wait(r'ASSIST plan',120); print('plan line:',l)
    l=r.wait(r'MC (loaded|no save|file)',5,from_start=True); print('card line:',l)
    l=r.wait(r'GS gf|SF3 frame 1 ',MAXS,from_start=True); print('LEVEL clock runs: first GS line after %.0f s wall:'%(time.time()-t0),l)
    time.sleep(20); print('last GS:',r.last(r'GS gf|SF3 frame')); print('write lines:',r.last(r'MC '))
finally: r.stop()
