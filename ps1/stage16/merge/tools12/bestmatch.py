import numpy as np
F=None
def load():
    global F
    if F is None: F=np.load('out/mframes.npy',mmap_mode='r')
    return F
def best(fr,lo=0,hi=1800,mask=None,chunk=100):
    F=load(); out=[]
    for a in range(lo,hi,chunk):
        c=np.asarray(F[a:min(a+chunk,hi)])
        d=(c!=fr[None]).any(3)
        if mask is not None: d=d&mask[None]
        out.append(d.sum((1,2)))
    d=np.concatenate(out); k=int(d.argmin()); return lo+k,int(d[k])
