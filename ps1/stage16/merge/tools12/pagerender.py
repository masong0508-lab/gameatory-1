import numpy as np, struct
def pal_rgb(pal):
    p=np.frombuffer(pal[:512],'<u2').astype(np.uint32)
    r=(p&31)<<3|(p&31)>>2; g=((p>>5)&31)<<3|((p>>5)&31)>>2; b=((p>>10)&31)<<3|((p>>10)&31)>>2
    return np.stack([r,g,b],1).astype(np.uint8)
def page_img(vr,pal,disp):
    off=0xa000 if disp&0x10 else 0
    idx=np.frombuffer(vr[off:off+240*160],np.uint8).reshape(160,240)
    return pal_rgb(pal)[idx]
