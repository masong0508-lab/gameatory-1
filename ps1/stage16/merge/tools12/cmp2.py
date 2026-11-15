import sys,numpy as np; sys.path.insert(0,'tools12'); from cmpshot import game,F
from PIL import Image
def best(a,lo,hi,mask=None):
    m=np.ones((160,240),bool) if mask is None else mask; res=[]
    for c in range(lo,hi,100):
        d=np.abs(np.asarray(F[c:min(c+100,hi)]).astype(np.int16)-a[None].astype(np.int16)).mean(3)[:,m].mean(1); res.append(d)
    d=np.concatenate(res); k=int(d.argmin()); return lo+k,float(d[k])
def mk(y0=0,x1=240): m=np.zeros((160,240),bool); m[y0:,:x1]=True; return m
if __name__=='__main__':
    # name lo hi y0 x1
    p,lo,hi,y0,x1=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5])
    a=game(p); k,d=best(a,lo,hi,mk(y0,x1)); print(p.split('/')[-1],'range',lo,hi,'mask y>=%d x<%d'%(y0,x1),'best',k,'diff %.2f'%d)
    Image.fromarray(np.concatenate([np.asarray(F[k]),a],1)).resize((960,320),Image.NEAREST).save(p.replace('.png','_c2.png'))
