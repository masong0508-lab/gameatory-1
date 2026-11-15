#!/usr/bin/env python3
"""mont.py OUT.png RUNPREFIX K...: pick, per run, the last rendered screenshot (the 640x480 emulator window, top-left of the 800x600 root) and tile them (3 columns, 320x240 each) with the map id; skips the debug (menu) view"""
import sys,glob,os
from PIL import Image,ImageDraw
import numpy as np
out=sys.argv[1]; pre=sys.argv[2]; ks=sys.argv[3:]
tiles=[]
for k in ks:
    best=None
    for f in sorted(glob.glob('%s%s_t*.png'%(pre,k))):
        try: im=Image.open(f).convert('RGB').crop((0,0,640,480))
        except Exception: continue
        a=np.asarray(im).astype(int)
        low=a[240:480]; v=low.std()
        hud=(a[8:28,10:470].sum(axis=2)<60).mean()      # the sf3 HUD bar is black behind white text
        dbg=(a[260:420,40:600].mean()<40 and a[260:420,40:600].std()<40)      # the menu debug view is a dark page with thin boxes
        if v>20 and hud>0.5 and not dbg: best=(f,im)
    if best is None: continue
    im=best[1].resize((320,240)); d=ImageDraw.Draw(im); d.rectangle((0,224,319,239),fill=(0,0,0)); d.text((4,226),'run %s  %s'%(k,os.path.basename(best[0])[-9:-4]),fill=(255,255,255)); tiles.append(im)
n=len(tiles); cols=3; rows=(n+cols-1)//cols
W=Image.new('RGB',(320*cols,240*rows))
for i,t in enumerate(tiles): W.paste(t,(320*(i%cols),240*(i//cols)))
W.save(out); print('tiles',n)
