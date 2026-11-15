import sys,numpy as np
from PIL import Image
F=np.load('out/mframes.npy',mmap_mode='r')   # (1800,160,240,3)
def game(path):
    im=np.array(Image.open(path).convert('RGB').crop((0,0,640,480)))   # display window 640x480 = PS1 320x240 at 2x
    gx=np.arange(240); gy=np.arange(160); sx=np.floor((gx+0.5)*320/240*2.0).astype(int); sy=np.floor((gy+0.5)*1.5*2.0).astype(int)
    return im[sy][:,sx]
def best(a,lo=0,hi=1800):
    ds=[]
    for c in range(lo,hi,100): ds.append(np.abs(np.asarray(F[c:min(c+100,hi)]).astype(np.int16)-a[None].astype(np.int16)).mean((1,2,3)))
    d=np.concatenate(ds); k=int(d.argmin()); return k+lo,float(d[k])
if __name__=='__main__':
    for p in sys.argv[1:]:
        a=game(p); k,d=best(a); print(p,'best mgba frame',k,'mean abs diff %.2f'%d)
        Image.fromarray(np.concatenate([F[k],a],1)).resize((960,320),Image.NEAREST).save(p.replace('.png','_cmp.png'))
