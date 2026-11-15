#!/usr/bin/env python3
"""padmap.py disc.cue home out: press every PS1 button with xdotool in PCSXR, read the guest's PADRAW lines (PS1 bit layout) and check the expected bit.  Boot-time only (guest runs fast then)."""
import sys,time; sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import pcx
cue,home,out=sys.argv[1:4]
EXP=dict(SELECT=0x1,START=0x8,UP=0x10,RIGHT=0x20,DOWN=0x40,LEFT=0x80,L2=0x100,R2=0x200,L1=0x400,R1=0x800,TRIANGLE=0x1000,CIRCLE=0x2000,CROSS=0x4000,SQUARE=0x8000)
r=pcx.Run(cue,home,out)
try:
    print('first PADRAW:',r.wait('PADRAW',60))
    time.sleep(3)
    ok=0
    for k,m in EXP.items():
        r.mark(); r.down(k); l=r.wait(r'PADRAW 0000%04x'%m,25); r.up(k)
        got=l is not None; ok+=got; print('%-9s expect %04x %s %s'%(k,m,'OK  ' if got else 'FAIL',l or ''),flush=True)
        r.wait(r'PADRAW 00000000',15); 
    # chord
    r.mark(); r.down('UP'); r.down('CROSS'); l=r.wait(r'PADRAW 00004010',25); r.up('UP'); r.up('CROSS'); print('chord Up+Cross',l); ok+=l is not None
    print('RESULT',ok,'/ 15')
finally: r.stop()
