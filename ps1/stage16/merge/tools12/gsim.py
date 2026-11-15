#!/usr/bin/env python3
"""TEST-ONLY: unicorn-MIPS sim of the PS1 exe + a small GPU command interpreter (LoadImage, flat rects, axis-aligned textured quads 4/8 bpp with CLUT, draw offset)
that renders the frames the exe sends, independent of any emulator GPU plugin.  Used to measure the PPU-lite output against mGBA frames.
usage: gsim.py EXE ISO ELF OUTPREFIX total_frames [shot_every_present]  -> writes OUTPREFIX_<n>.png (320x240 GPU frame) and pickles state dumps"""
import sys,os,struct,time,pickle
sys.path.insert(0,'t')
import numpy as np
from sim4 import *
from PIL import Image
class Gpu:
    def __init__(s):
        s.vram=np.zeros((512,1024),np.uint16); s.st=0; s.buf=[]; s.need=0; s.cmd=0; s.ox=0; s.oy=0; s.img=None; s.frames=[]; s.dispy=0; s.nq=0
        s.area=(0,0,1023,511); s.hist=[]; s.rdp=(0,0,1,1,0); s.unk={}; s.cc={}; s.fc=[]
    def rdw(s):
        x,y,wd,ht,pos=s.rdp; n=wd*ht; v=0
        for k in (0,1):
            if pos<n:
                r,c=divmod(pos,wd); v|=int(s.vram[(y+r)&511,(x+c)&1023])<<(16*k); pos+=1
        s.rdp=(x,y,wd,ht,pos); return v
    def gp1(s,v):
        c=v>>24
        if c==5:
            s.fc.append(dict(s.cc)); s.cc={}; s.fc=s.fc[-6:]
            s.frames.append(s.vram[(v>>10)&0x1ff:((v>>10)&0x1ff)+240,0:320].copy())
    def w0(s,w):
        if s.img is not None:
            x,y,wd,ht,pos=s.img
            n=wd*ht
            for k in (0,1):
                if pos<n:
                    r,c=divmod(pos,wd); 
                    if y+r<512 and x+c<1024: s.vram[y+r,x+c]=(w>>(16*k))&0xffff
                    pos+=1
            s.img=(x,y,wd,ht,pos) if pos<n else None
            return
        if s.need:
            s.buf.append(w)
            if len(s.buf)==s.need: s.run()
            return
        c=w>>24; s.cc[c]=s.cc.get(c,0)+1 if (not s.need and s.img is None) else s.cc.get(c,0); s.hist.append(w); s.hist=s.hist[-40:]
        if c==0xa0 or c==0xc0: s.cmd=c; s.need=3; s.buf=[w]
        elif c in (0x2c,0x2d,0x2e,0x2f): s.cmd=c; s.need=9; s.buf=[w]
        elif c==0x60 or c==0x02: s.cmd=c; s.need=3; s.buf=[w]
        elif c in (0x64,0x65,0x66,0x67): s.cmd=c; s.need=4; s.buf=[w]; print('TEXRECT',hex(c),[hex(x) for x in s.hist[-12:]])
        elif c==0xe5: s.ox=w&0x7ff; s.oy=(w>>11)&0x7ff; s.ox=s.ox-2048 if s.ox>=1024 else s.ox; s.oy=s.oy-2048 if s.oy>=1024 else s.oy
        elif c==0xe3: s.area=(w&0x3ff,(w>>10)&0x1ff)+s.area[2:]
        elif c==0xe4: s.area=s.area[:2]+(w&0x3ff,(w>>10)&0x1ff)
        elif c not in (0xe1,0xe2,0xe6,0x01,0x03,0x00): s.unk[c]=s.unk.get(c,0)+1; s.unkh=getattr(s,'unkh',[])+[[hex(x) for x in s.hist[-6:]]]
        # others ignored (E1, E2, E6, 01, 03 ...)
    def run(s):
        b=s.buf; s.need=0; c=s.cmd
        if getattr(s,'dump',0) and c!=0xa0: print('CMD',[hex(x) for x in b])
        elif getattr(s,'dump',0): print('A0',b[1]&0x3ff,(b[1]>>16)&0x1ff,b[2]&0xffff,b[2]>>16)
        if c==0xc0:
            s.rdp=(b[1]&0x3ff,(b[1]>>16)&0x1ff,b[2]&0xffff or 1024,(b[2]>>16)&0xffff or 512,0)
        elif c==0xa0:
            x=b[1]&0x3ff; y=(b[1]>>16)&0x1ff; wd=b[2]&0xffff or 1024; ht=(b[2]>>16)&0xffff or 512; s.img=(x,y,wd,ht,0); s.nA=getattr(s,'nA',0)+1
        elif c in (0x60,0x02):
            r=b[0]&0xff; g=(b[0]>>8)&0xff; bl=(b[0]>>16)&0xff; v=(r>>3)|((g>>3)<<5)|((bl>>3)<<10)
            if c==0x60:
                x=(b[1]&0xffff)-(0x10000 if b[1]&0x8000 else 0)+s.ox; y=((b[1]>>16)&0xffff)-(0x10000 if (b[1]>>16)&0x8000 else 0)+s.oy; w=b[2]&0xffff; h=b[2]>>16
            else: x=b[1]&0x3f0; y=(b[1]>>16)&0x1ff; w=((b[2]&0x3ff)+15)&~15; h=(b[2]>>16)&0x1ff
            x0,y0=max(x,s.area[0] if c==0x60 else 0),max(y,s.area[1] if c==0x60 else 0); x1=min(x+w,(s.area[2]+1) if c==0x60 else 1024); y1=min(y+h,(s.area[3]+1) if c==0x60 else 512)
            if x1>x0 and y1>y0: s.vram[y0:y1,x0:x1]=v
        elif c in (0x2c,0x2d,0x2e,0x2f):
            sx=lambda w:((w&0xffff)-(0x10000 if w&0x8000 else 0), ((w>>16)&0xffff)-(0x10000 if (w>>16)&0x8000 else 0))
            v=[sx(b[1]),sx(b[3]),sx(b[5]),sx(b[7])]; tex=[(b[2]&255,(b[2]>>8)&255),(b[4]&255,(b[4]>>8)&255),(b[6]&255,(b[6]>>8)&255),(b[8]&255,(b[8]>>8)&255)]
            clut=b[2]>>16; tp=b[4]>>16
            cx=(clut&63)*16; cy=(clut>>6)&511
            tx=(tp&15)*64; ty=((tp>>4)&1)*256; mode=(tp>>7)&3; bm=(tp>>5)&3; semi=(c&2)!=0
            xs_=[p[0]+s.ox for p in v]; ys_=[p[1]+s.oy for p in v]
            minx=max(min(xs_),s.area[0]); maxx=min(max(xs_),s.area[2]+1); miny=max(min(ys_),s.area[1]); maxy=min(max(ys_),s.area[3]+1)
            if maxx<=minx or maxy<=miny: return
            gx,gy=np.meshgrid(np.arange(minx,maxx)+0.5,np.arange(miny,maxy)+0.5)
            U=np.zeros(gx.shape); V=np.zeros(gx.shape); cov=np.zeros(gx.shape,bool)
            for tri in ((0,1,2),(1,2,3)):
                (xa,ya),(xb,yb),(xc,yc)=[(xs_[k],ys_[k]) for k in tri]
                den=(yb-yc)*(xa-xc)+(xc-xb)*(ya-yc)
                if den==0: continue
                l1=((yb-yc)*(gx-xc)+(xc-xb)*(gy-yc))/den; l2=((yc-ya)*(gx-xc)+(xa-xc)*(gy-yc))/den; l3=1-l1-l2
                eps=-1e-9
                m=(l1>=eps)&(l2>=eps)&(l3>=eps)&~cov
                ua,va=tex[tri[0]]; ub,vb=tex[tri[1]]; uc,vc=tex[tri[2]]
                U=np.where(m,l1*ua+l2*ub+l3*uc,U); V=np.where(m,l1*va+l2*vb+l3*vc,V); cov|=m
            if not cov.any(): return
            uu=np.clip(np.floor(U).astype(int),0,255); vv=np.clip(np.floor(V).astype(int),0,255)
            if mode==1:
                hw=s.vram[ty+vv, tx+(uu>>1)]; idx=(hw>>(8*(uu&1)))&0xff; col=s.vram[cy, cx+idx]
            elif mode==0:
                hw=s.vram[ty+vv, tx+(uu>>2)]; idx=(hw>>(4*(uu&3)))&0xf; col=s.vram[cy, cx+idx]
            else: col=s.vram[ty+vv, tx+uu]
            ys0=miny; xs0=minx
            m=cov&(col!=0)
            dst=s.vram[miny:maxy,minx:maxx].astype(np.int32)
            if semi:
                st_=(col>>15)&1; bl=m&(st_==1); op=m&(st_==0)
                B=[(dst>>(5*k))&31 for k in range(3)]; Fc=[(col.astype(np.int32)>>(5*k))&31 for k in range(3)]
                if bm==0: R=[(B[k]+Fc[k])//2 for k in range(3)]
                elif bm==1: R=[np.minimum(31,B[k]+Fc[k]) for k in range(3)]
                elif bm==2: R=[np.maximum(0,B[k]-Fc[k]) for k in range(3)]
                else: R=[np.minimum(31,B[k]+Fc[k]//4) for k in range(3)]
                blend=R[0]|(R[1]<<5)|(R[2]<<10)
                res=np.where(bl,blend,np.where(op,col.astype(np.int32),dst))
            else: res=np.where(m,col.astype(np.int32),dst)
            s.vram[miny:maxy,minx:maxx]=res.astype(np.uint16); s.nq+=1
class GSim(Sim):
    def __init__(s,exe,iso,elf):
        super().__init__(exe,iso,elf); s.gpu=Gpu()
        def wr(off,val):
            if off==0x810: s.gpu.w0(val&0xffffffff)
            elif off==0x814: s.gpu.gp1(val&0xffffffff)
        s.mw=wr; s.mr=s.gpu.rdw
def to_rgb(f):
    p=f.astype(np.uint32); r=(p&31)<<3; g=((p>>5)&31)<<3; b=((p>>10)&31)<<3
    return np.stack([r|r>>5,g|g>>5,b|b>>5],-1).astype(np.uint8)
