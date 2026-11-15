#!/usr/bin/env python3
"""TEST-ONLY reference model of the GBA OBJ layer in bitmap mode 4 (regular + rotation/scaling sprites, 4/8 bpp, 1D/2D mapping, semi-transparent alpha) used to check
the understanding of the hardware against mGBA, independent of the PS1 code.  render(state, bgrgb) -> RGB image 160x240"""
import struct,numpy as np
SZ=[[(8,8),(16,16),(32,32),(64,64)],[(16,8),(32,8),(32,16),(64,32)],[(8,16),(8,32),(16,32),(32,64)]]
def render(vr,pal,oam,disp,bgrgb,eva=16,evb=16,bg2pri=2):
    img=bgrgb.astype(np.int32).copy(); P=np.frombuffer(pal,'<u2')[256:512]; O=struct.unpack('<512H',oam)
    vr=np.frombuffer(vr,np.uint8); map1d=bool(disp&0x40)
    order=sorted(range(128),key=lambda i:(-(O[i*4+2]>>10&3),-i))      # low priority first, higher index first
    for i in order:
        a0,a1,a2=O[i*4:i*4+3]; aff=a0>>8&1; dbl=a0>>9&1
        if not aff and dbl: continue
        sh=a0>>14; sz=a1>>14
        if sh>2: continue
        gm=a0>>10&3
        if gm==2: continue
        pri=a2>>10&3
        if pri>bg2pri: continue
        w,h=SZ[sh][sz]; bw,bh=(2*w,2*h) if dbl else (w,h)
        y=a0&255; x=a1&511
        if y>=160: y-=256
        if x>=256: x-=512
        tile=a2&1023
        if tile<512: continue
        b8=a0>>13&1; tw=w//8
        if aff:
            g=a1>>9&31; pa,pb,pc,pd=[struct.unpack('<h',struct.pack('<H',O[(4*g+k)*4+3]))[0] for k in range(4)]
        for sy in range(bh):
            Y=y+sy
            if not(0<=Y<160): continue
            for sx in range(bw):
                X=x+sx
                if not(0<=X<240): continue
                if aff:
                    ix=sx-bw//2; iy=sy-bh//2
                    u=((pa*ix+pb*iy)>>8)+w//2; v=((pc*ix+pd*iy)>>8)+h//2
                    if not(0<=u<w and 0<=v<h): continue
                else:
                    u=sx; v=sy
                    if a1>>12&1: u=w-1-u
                    if a1>>13&1: v=h-1-v
                ttx=u>>3; tty=v>>3; px=u&7; py=v&7
                if b8:
                    slot=tile+(tty*tw+ttx)*2 if map1d else tile+tty*32+ttx*2
                    off=0x10000+slot*32+py*8+px
                    if off>=0x18000: continue
                    ci=int(vr[off])
                else:
                    slot=tile+(tty*tw+ttx) if map1d else tile+tty*32+ttx
                    off=0x10000+slot*32+py*4+(px>>1)
                    if off>=0x18000: continue
                    bt=int(vr[off]); ci=(bt>>4 if px&1 else bt&15)
                    if ci: ci+= (a2>>12)*16
                if ci==0 and not b8: continue
                if ci==0: continue
                c=int(P[ci]); r=(c&31); gg=(c>>5)&31; bl=(c>>10)&31
                if gm==1:
                    d=img[Y,X]; sc=np.array([r,gg,bl])
                    dst5=np.array([d[0]>>3,d[1]>>3,d[2]>>3])
                    out=np.minimum(31,(sc*eva+dst5*evb)//16)
                    img[Y,X]=[ (int(out[0])<<3)|(int(out[0])>>2),(int(out[1])<<3)|(int(out[1])>>2),(int(out[2])<<3)|(int(out[2])>>2)]
                else:
                    img[Y,X]=[(r<<3)|(r>>2),(gg<<3)|(gg>>2),(bl<<3)|(bl>>2)]
    return img.astype(np.uint8)
