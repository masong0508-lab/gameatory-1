#!/usr/bin/env python3
"""TEST-ONLY: for each gsim PNG frame find the best matching mGBA frame (global search over all recorded frames) and report pixel diff numbers.
usage: gbest.py PREFIX f1,f2,... [lo hi]  -> table + PREFIX_best.json + PREFIX_cmp_<f>.png (mGBA | PS1 | 3x abs diff)"""
import sys,json,numpy as np
from PIL import Image
import os
F=np.load(os.environ.get('REF','out/mframes.npy'),mmap_mode='r')
pre=sys.argv[1]; fr=[int(x) for x in sys.argv[2].split(',')]; lo=int(sys.argv[3]) if len(sys.argv)>3 else 0; hi=int(sys.argv[4]) if len(sys.argv)>4 else 1800
res={}
for f in fr:
    a=np.asarray(Image.open('%s_f%04d.png'%(pre,f)).convert('RGB').resize((240,160),Image.BOX)).astype(np.int16)
    best=(1e9,-1)
    for c0 in range(lo,hi,100):
        blk=np.asarray(F[c0:min(hi,c0+100)]).astype(np.int16)
        d=np.abs(blk-a[None]).mean((1,2,3)); k=int(d.argmin())
        if d[k]<best[0]: best=(float(d[k]),c0+k)
    md,k=best; m=np.asarray(F[k]).astype(np.int16); d=np.abs(m-a)
    pc=float((d.sum(2)>24).mean()*100)
    res[f]=dict(best=k,mad=round(md,2),pct24=round(pc,1))
    print('ps1 gf %d  best mGBA frame %d  mean abs diff %.2f  pixels differing >24: %.1f%%'%(f,k,md,pc),flush=True)
    out=np.concatenate([m.astype(np.uint8),a.astype(np.uint8),np.clip(d*3,0,255).astype(np.uint8)],1)
    Image.fromarray(out).resize((1440,320),Image.NEAREST).save('%s_cmp%s_%04d.png'%(pre,os.environ.get('TAG',''),f))
json.dump(res,open(pre+os.environ.get('TAG','')+'_best.json','w'))
print('MEAN mean-abs-diff %.2f   mean pct>24 %.1f'%(np.mean([r['mad'] for r in res.values()]),np.mean([r['pct24'] for r in res.values()])))
