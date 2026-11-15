"""Python reference of the PPU-lite blit semantics (ground for the C port): a literal port of Payback's gfx_blit_image (0x08028ac4, id 2, transparent
copy 0x3005eb8) and gfx_blit_image_m4 (0x08028c08, id 4, opaque copy 0x3005f68) onto the mode-4 page in the VRAM shadow.  No Payback data in this file."""
import struct
IMG_BASE=0x0809d694
def s32(v): v&=0xffffffff; return v-(1<<32) if v&0x80000000 else v
class Blit:
    def __init__(s,rom,vram,ewram=None):
        s.rom=rom; s.vr=vram; s.ew=ewram
    def rd16(s,a): return struct.unpack_from('<H',s.rom,a-0x8000000)[0]
    def rd8(s,a): return s.rom[a-0x8000000]
    def rd32(s,a): return struct.unpack_from('<I',s.rom,a-0x8000000)[0]
    def hdr(s,img):
        w=s.rd16(img); h=s.rd8(img+2); src=(s.rd32(img+4)+IMG_BASE)&0xffffffff
        return w,h,src
    def copy(s,dst,src,w,h,sskip,dskip,transp):
        rom=s.rom; vr=s.vr
        for _ in range(h):
            so=src-0x8000000
            if transp:
                for i in range(w):
                    b=rom[so+i]
                    if b: vr[dst+i]=b
            else:
                vr[dst:dst+w]=rom[so:so+w]
            src+=w+sskip; dst+=w+dskip
    def blit2(s,img,x,y,disp):
        w,h,src=s.hdr(img); x=s32(x); y=s32(y); ow=w
        if y<0: src+=(-y)*w; h+=y; y=0
        if y+h>160: h=160-y
        if h<=0: return
        if x<0: src+=-x; w+=x; x=0
        if x+w>240: w=240-x
        if w<=0: return
        base=0 if disp&0x10 else 0xa000
        s.copy(base+y*240+x,src,w,h,ow-w,240-w,True)
    def blit4(s,img,x,y,disp,limw=240,limh=160,stride=240):
        w,h,src=s.hdr(img); x=s32(x); y=s32(y); ow=w
        if y<0: src+=(-y)*w; h+=y; y=0
        if y+h>limh: h-=y+h-limh
        if h<=0: return
        if x<0: src+=-x; w+=x; x=0
        if x+w>limw: w-=x+w-limw
        if w<=0: return
        base=0 if disp&0x10 else 0xa000
        s.copy(base+y*stride+x,src,w,h,ow-w,stride-w,False)
