"""Python compositor for PPU-lite state taken from the unicorn sim of the PS1 exe (model-level check of the C code: L0 list + L1 page + palette -> 240x160 RGB)."""
import struct,numpy as np,sys
sys.path.insert(0,'tools12'); from pagerender import pal_rgb
def compose(s,rom,level=False):
    disp=struct.unpack_from('<H',s['io'],0)[0]; lp=1 if disp&0x10 else 0; base=0xa000 if lp else 0
    pal=pal_rgb(s['pal']); fr=np.zeros((160,240,3),np.uint8); fr[:]=pal[0]
    if disp&0x80 or (disp&7)!=4: return fr,disp
    nl0=s['nl0'][lp]; imgs=s['pimg']
    for k in range(nl0):
        x,y,w,h,cx,cy,iid=struct.unpack_from('<6hH',s['l0'],(lp*20+k)*14)
        key=struct.unpack_from('<I',imgs,iid*20)[0]
        iw=struct.unpack_from('<H',rom,key-0x8000000)[0]; ih=rom[key-0x8000000+2]; src=(struct.unpack_from('<I',rom,key-0x8000000+4)[0]+0x809d694)&0x1ffffff
        buf=np.frombuffer(rom,np.uint8,iw*ih,src).reshape(ih,iw)
        fr[y:y+h,x:x+w]=pal[buf[cy:cy+h,cx:cx+w]]
    l1=np.frombuffer(s['vr'][base:base+38400],np.uint8).reshape(160,240)
    m=l1!=0; fr[m]=pal[l1[m]]
    return fr,disp
