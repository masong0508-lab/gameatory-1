#!/usr/bin/env python3
"""rtrip.py EXE CARD PREV_EE [N]: save/load round trip on the unicorn sim (SIM-ONLY, real memory-card driver over a modelled SIO0).
Boots the disc with CARD (written by an earlier session), dumps the guest's EEPROM image at gframe 120 (the runtime has loaded the card file into it by then) and compares it with PREV_EE
(the guest's EEPROM image at the end of the earlier session); then lets the menu assist/boot run on to the level.  Prints MATCH/DIFF and the plan the assist chose."""
import sys,os,time
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))+'/../t')
from sim13 import *
exe,card,prev=sys.argv[1:4]; N=int(sys.argv[4]) if len(sys.argv)>4 else 1400
s=Sim13('out/%s.exe'%exe,'out/%s.iso'%exe,'out/bld_%s/payback.elf'%exe,card=card)
s.pad=lambda: 0
st=dict(lvl=None,ee=None); T0=time.time()
def cb(s):
    f=s.gframe()
    if st['ee'] is None and f>=120: st['ee']=s.rd(s.sym['ee'],8192)
    if st['lvl'] is None and s.r32(EW+0x1e00): st['lvl']=f
    return f>=N
s.cb=cb; s.run(count=30000000000)
o=s.out.decode('latin1'); pe=open(prev,'rb').read()
d=[i for i in range(8192) if st['ee'][i]!=pe[i]]
print('ROUNDTRIP eeprom image after card load vs end of previous session:','MATCH (8192 bytes identical)' if not d else 'DIFF %d bytes, first at %s'%(len(d),d[:8]))
print('non-ff bytes',sum(1 for b in st['ee'] if b!=0xff),'level clock runs at gframe',st['lvl'],'wall %.0f'%(time.time()-T0),'card reads',s.sio.ncard_r,'writes',s.sio.ncard_w)
print('\n'.join(l for l in o.split('\n') if l.startswith(('ASSIST','MC '))))
