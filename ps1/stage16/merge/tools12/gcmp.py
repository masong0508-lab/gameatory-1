#!/usr/bin/env python3
"""TEST-ONLY: compare gsim PNG frames (PS1 GPU model, 320x240) with mGBA frames of the original ROM.  usage: gcmp.py PREFIX f1,f2,...  [win=6]
prints per frame: best mGBA frame in +-win, mean abs diff (0..255 per channel), % pixels differing by more than 24 (sum of |dRGB|), writes PREFIX_cmp_<f>.png (mGBA | PS1 | abs diff)"""
import sys,numpy as np
from PIL import Image
F=np.load('out/mframes.npy',mmap_mode='r')
pre=sys.argv[1]; fr=[int(x) for x in sys.argv[2].split(',')]; win=int(sys.argv[3]) if len(sys.argv)>3 else 6
res=[]
for f in fr:
    im=Image.open('%s_f%04d.png'%(pre,f)).convert('RGB').resize((240,160),Image.BOX); a=np.asarray(im).astype(int)
    best=None
    for k in range(max(0,f-win),min(1800,f+win+1)):
        m=np.asarray(F[k]).astype(int); d=np.abs(m-a); md=d.mean(); 
        if best is None or md<best[1]: best=(k,md,float((d.sum(2)>24).mean()*100),m,d)
    k,md,pc,m,d=best; res.append((f,k,md,pc))
    print('ps1 frame %d  best mGBA %d  mean abs diff %.2f  pixels >24: %.1f%%'%(f,k,md,pc))
    out=np.concatenate([m.astype(np.uint8),a.astype(np.uint8),np.clip(d*3,0,255).astype(np.uint8)],1)
    Image.fromarray(out).resize((1440,320),Image.NEAREST).save('%s_cmp_%04d.png'%(pre,f))
print('mean of mean-abs-diff %.2f'%np.mean([r[2] for r in res]))
