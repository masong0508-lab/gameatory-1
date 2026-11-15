#!/usr/bin/env python3 -I
"""Stage 3 data packer (our tool; its input is the locally converted world of stage 2b, never committed).
usage: mksf3.py W0DIR OUTDIR   ->  OUTDIR/SF3W.BIN (compact world), SF3A.BIN (atlas pages + clut + font)
World compaction: the 128x128 per-cell tables of the stage-2b blob are huge but nearly empty: cells (276 distinct of 16384) become a u16 index
plus a dictionary, deck (809 cells used) a sorted sparse list; wall/lots/spare tables that sf.c never reads are dropped."""
import sys,struct,array
w0,out=sys.argv[1],sys.argv[2]
d=open(w0+'/WORLD.SFW','rb').read()
h=struct.unpack('<25I',d[:100]); so=list(h[9:25]); nbox,nramp,ntree=h[1],h[3],h[7]
def seg(a,b): return d[a:b]
boxes=seg(so[0],so[1]); ramps=seg(so[2],so[3]); sector=seg(so[4],so[5]); items=seg(so[5],so[6]); trees=seg(so[9],so[10])
ctex=seg(so[10],so[10]+32768); btex=seg(so[11],so[12]); dtex=seg(so[15],so[15]+32768)
cells=seg(so[6],so[6]+98304); dict_={}; idx=array.array('H')
for i in range(16384):
    c=cells[i*6:i*6+6]
    if c not in dict_: dict_[c]=len(dict_)
    idx.append(dict_[c])
cd=b''.join(sorted(dict_,key=dict_.get))
deck=seg(so[12],so[12]+65536); dk=b''; nd=0
for i in range(16384):
    e=deck[4*i:4*i+4]
    if any(e): dk+=struct.pack('<H',i)+e; nd+=1
parts=[('boxes',boxes),('ramps',ramps),('sector',sector),('items',items),('trees',trees),('ctex',ctex),('btex',btex),('dtex',dtex),('cellidx',idx.tobytes()),('celldict',cd),('deck',dk)]
off=18*4; offs=[]; body=b''
for n,b in parts:
    off=(off+3)&~3; body+=b'\0'*(off-18*4-len(body)); offs.append(off); body+=b; off+=len(b)
hdr=[0x57334653,nbox,nramp,ntree,len(dict_),nd]+offs+[off]
hb=struct.pack('<%dI'%len(hdr),*hdr).ljust(18*4,b'\0')
blob=hb+body; blob+=b'\0'*((-len(blob))%2048)
open(out+'/SF3W.BIN','wb').write(blob)
print('SF3W.BIN',len(blob),'cells dict',len(dict_),'deck',nd,'offs',offs)
a=open(w0+'/ATLAS.VRM','rb').read(); npg=struct.unpack_from('<I',a,0)[0]
rects=a[16:16+npg*8]; pages=a[16+npg*8:16+npg*8+npg*65536]
assert len(pages)==npg*65536,(len(pages),npg)
clut=open(w0+'/CLUT.BIN','rb').read(); font=open(w0+'/FONT.VRM','rb').read()
hdr=struct.pack('<IIII',npg,len(clut),len(font),0)+rects
hdr=hdr.ljust(2048,b'\0')
blob=hdr+pages+clut.ljust((len(clut)+2047)&~2047,b'\0')+font.ljust((len(font)+2047)&~2047,b'\0')
open(out+'/SF3A.BIN','wb').write(blob); print('SF3A.BIN',len(blob),'pages',npg,'clut',len(clut),'font',len(font))
