#!/usr/bin/env python3
"""TEST-ONLY: compare state-injection frames (PS1 GPU model, 320x240) with the mGBA frame of the SAME state.  usage: icmp.py PREFIX [frames_csv]
numbers per frame: mean abs diff over RGB (0..255), % pixels with |dR|+|dG|+|dB|>24, versus (a) the real mGBA frame (with OBJ), (b) the BG-only render."""
import sys,glob,re,json,numpy as np
from PIL import Image
pre=sys.argv[1]; F=np.load('out/mframes.npy',mmap_mode='r'); B=np.load('out/mbg.npy',mmap_mode='r')
fr=sorted(int(re.search(r'_f(\d+)\.png',p).group(1)) for p in glob.glob(pre+'_f*.png'))
if len(sys.argv)>2: fr=[int(x) for x in sys.argv[2].split(',')]
rows=[]; tiles=[]
for f in fr:
    a=np.asarray(Image.open('%s_f%04d.png'%(pre,f)).convert('RGB')).astype(int)            # PS1 320x240
    xi=np.floor((np.arange(320)+0.5)*0.75).astype(int); yi=np.floor((np.arange(240)+0.5)*160/240).astype(int)                                     # the ideal point-sampled 4:3 / 3:2 upscale of a GBA frame
    up=lambda g:np.asarray(g)[yi][:,xi].astype(int)
    m=up(F[f]); b=up(B[f])
    d=np.abs(a-m); db=np.abs(a-b)
    r=dict(f=f,mad=round(float(d.mean()),2),pct=round(float((d.sum(2)>24).mean()*100),1),mad_bg=round(float(db.mean()),2),pct_bg=round(float((db.sum(2)>24).mean()*100),1)); rows.append(r)
    print('frame %4d  vs real mGBA frame: mean abs diff %5.2f  px>24 %5.1f%%   | vs BG-only render: %5.2f  %5.1f%%'%(f,r['mad'],r['pct'],r['mad_bg'],r['pct_bg']),flush=True)
    tiles.append(np.concatenate([m.astype(np.uint8),a.astype(np.uint8),np.clip(d*3,0,255).astype(np.uint8)],1))
    del d
print('MEAN vs real: %.2f / %.1f%%   vs BG-only: %.2f / %.1f%%'%(np.mean([r['mad'] for r in rows]),np.mean([r['pct'] for r in rows]),np.mean([r['mad_bg'] for r in rows]),np.mean([r['pct_bg'] for r in rows])))
json.dump(rows,open(pre+'_icmp.json','w'))
for i,t in enumerate(tiles): Image.fromarray(t).resize((1440,240),Image.NEAREST).save('%s_icmp_%04d.png'%(pre,fr[i]))
