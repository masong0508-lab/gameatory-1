#!/usr/bin/env python3
"""TEST-ONLY: PS1 PPU-lite frame (state injection) vs the reference Python OBJ model of the same state (checks the PS1 implementation, not the hardware understanding).
usage: pvm.py PREFIX"""
import sys,pickle,glob,re,numpy as np
sys.path.insert(0,'tools12')
from PIL import Image
from objmodel import render
pre=sys.argv[1]; B=np.load('out/mbg.npy',mmap_mode='r'); S=pickle.load(open('out/mstates.pkl','rb'))
xi=np.floor((np.arange(320)+0.5)*0.75).astype(int); yi=np.floor((np.arange(240)+0.5)*160/240).astype(int)
fr=sorted(int(re.search(r'_f(\d+)\.png',p).group(1)) for p in glob.glob(pre+'_f*.png'))
res={}
for f in fr:
    d=S[f]; eva,evb=((16,16) if f<1090 else (8,8))
    m=render(d['vr'],d['pal'],d['oam'],d['disp'],np.asarray(B[f]),eva,evb)
    a=np.asarray(Image.open('%s_f%04d.png'%(pre,f)).convert('RGB')).astype(int); r=m[yi][:,xi].astype(int); e=np.abs(a-r)
    res[f]=(round(float(e.mean()),2),round(float((e.sum(2)>24).mean()*100),1)); print('frame',f,'PS1 vs model: mean abs diff %.2f  px>24 %.1f%%'%res[f],flush=True)
    Image.fromarray(np.concatenate([r.astype(np.uint8),a.astype(np.uint8),np.clip(e*3,0,255).astype(np.uint8)],1)).save('%s_pvm_%04d.png'%(pre,f))
pickle.dump(res,open(pre+'_pvm.pkl','wb')); print('MEAN',np.mean([v[0] for v in res.values()]).round(2))
