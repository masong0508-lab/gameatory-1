#!/usr/bin/env python3
"""TEST-ONLY state-injection render test: the PS1 PPU-lite is fed the GBA PAL/OAM/VRAM/DISPCNT of a real mGBA run (original ROM, same state), so the
display stage can be compared to the original frame without any timeline difference.  usage: gsim_inj.py EXE ISO ELF STATES.pkl OUTPREFIX [bldalpha_menu bldalpha_level]
For every state: write PAL/OAM/VRAM/DISPCNT (+BLD regs) into the guest shadows at the entry of present(), capture the frame the PS1 GPU model displays for that present."""
import sys,os,pickle,struct,time
sys.path.insert(0,'tools12'); sys.path.insert(0,'t')
from gsim import *
exe,iso,elf,stf,out=sys.argv[1:6]
S=pickle.load(open(stf,'rb')); keys=sorted(S)
BLD=int(os.environ.get('BLD_MENU','0x1010'),16), int(os.environ.get('BLD_LEVEL','0x808'),16)
s=GSim(exe,iso,elf); sym=s.sym; IO=sym['io']; CY=sym['io_cyc']
st={'i':0,'pend':None,'n':0}; T0=time.time(); frames={}
def put(addr,b): s.u.mem_write(addr&0x1fffffff,b)
def cb(s):
    st['n']+=1
    if st['pend'] is not None and st['n']>st['wait']:
        f=st['pend']; frames[f]=s.gpu.frames[-1].copy(); Image.fromarray(to_rgb(frames[f])).save('%s_f%04d.png'%(out,f)); st['pend']=None
        print('captured',f,'t %.0f'%(time.time()-T0),flush=True)
    if st['pend'] is None and st['n']>=40 and st['i']<len(keys):
        f=keys[st['i']]; st['i']+=1; d=S[f]
        put(PAL,d['pal']); put(PAL+0x400,d['oam']); put(VRAM,d['vr'])
        put(IO+0,struct.pack('<H',d['disp'])); put(IO+0xc,struct.pack('<H',2)); put(IO+0x50,struct.pack('<H',0x2440))
        put(IO+0x52,struct.pack('<H',BLD[1] if f>=1090 else BLD[0]))
        st['pend']=f; st['wait']=st['n']
    return st['i']>=len(keys) and st['pend'] is None
s.cb=cb; s.run(count=30000000000)
pickle.dump({k:v for k,v in frames.items()},open(out+'_frames.pkl','wb')); print('done',len(frames))
