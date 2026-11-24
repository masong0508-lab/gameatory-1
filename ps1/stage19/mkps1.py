#!/usr/bin/env python3
"""Packaging for the PS1 build (our tool, code only): usage mkps1.py ROM OUTDIR TAG BOOTIMG ROMPAGES.pkl DESTDIR
Writes DESTDIR/{syms.c,blob.s,rompack.bin,...}; ROM data pages (resident set) are cut from the user's ROM into rompack.bin (local build output)."""
import sys,struct,pickle
rom=open(sys.argv[1],'rb').read(); OUT=sys.argv[2]; TAG=sys.argv[3]; BOOT=sys.argv[4]; PAGES=pickle.load(open(sys.argv[5],'rb')); D=sys.argv[6]
gmap={}
for l in open(OUT+'/payback_%s.map'%TAG):
    a,h=l.split(); gmap[int(a,16)]=int(h,16)
import os
L=[int(x) for x in os.environ.get('LBAS','0,0,0,0,0,0').split(',')]
meta=pickle.load(open(OUT+'/meta_%s.pkl'%TAG,'rb'))
open(D+'/syms.c','w').write('unsigned GUEST_MAIN_HOST=0x%08x;\nconst unsigned COLD_HOST=0x%08x;\nconst unsigned CD_ROM_LBA=%d, CD_COLD_LBA=%d, CD_COLD_PAGES=%d;\nconst unsigned CD_SNAPST_LBA=%d;\nconst unsigned CD_SF3W_LBA=%d, CD_SF3W_SECS=%d, CD_SF3A_LBA=%d, CD_SNAP_LBA=%d, CD_SNAP_N=%d;\n'%(gmap[0x08022dc8],meta['cold']['start'],L[0],L[1],L[2],L[6] if len(L)>6 else 0,L[3],os.path.getsize(os.path.dirname(os.path.abspath(__file__))+'/out/SF3W.BIN')//2048 if os.path.exists(os.path.dirname(os.path.abspath(__file__))+'/out/SF3W.BIN') else 0,L[4],L[5],int(os.environ.get('NSNAP','0'))))
# stage 7: interpreter fallback tables: the hot hash (guest entry -> host entry) and the ROM ranges that start ARM state code
rt=meta['rt']; nslots=(rt['HEND']-rt['HASH'])//8-64
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
P=pickle.load(open(os.environ.get('PROGPKL',os.path.dirname(os.path.abspath(__file__))+'/out/s2/prog_pr.pkl'),'rb'))
ra=sorted(a for a,i in P.ins.items() if i.mode=='A' and a>>24==8); runs=[]
for a in ra:
    if runs and a<=runs[-1][1]: runs[-1][1]=a+4
    else: runs.append([a,a+4])
open(D+'/syms.c','a').write('const unsigned HASH_HOST=0x%08x, HASH_NSLOTS=%d, ARMTAB_N=%d, RT_BX_HOST=0x%08x;\nconst unsigned ARMTAB[]={%s};\n'%(rt['HASH'],nslots,len(runs),rt['RT_BX'],','.join('0x%x,0x%x'%(a,b) for a,b in runs)))
import prune
stb=[(a,i) for i,(a,n) in sorted(prune.STUBS.items())]
assert [i for a,i in stb]==list(range(1,len(stb)+1)) or os.environ.get('PRUNE_DROP')   # Milestone B: ids may have gaps (interp_glue.h MERGED looks a thunk up by id)
open(D+'/syms.c','a').write('const unsigned STUBTAB_N=%d, RT_STUB_HOST=0x%08x;\nconst unsigned STUBTAB[]={%s};\n'%(len(stb),rt['RT_STUB'],','.join('0x%x,%d'%(a,i) for a,i in stb)))
open(D+'/blobs.s','w').write('''.section .blob,"a"
.incbin "%s/payback_%s.bin"
.section .bootimg,"a"
.global bootimg
bootimg:
.incbin "%s"
.section .coldtab,"a"
.global coldtab
coldtab:
.incbin "%s/coldtab_%s.bin"
.section .rompack,"a"
.global rompack
rompack:
.incbin "%s/rompack.bin"
'''%(OUT,TAG,BOOT,OUT,TAG,D))
pages=[] if os.environ.get('STREAM') else sorted(PAGES)
b=struct.pack('<I',len(pages))+b''.join(struct.pack('<I',p) for p in pages)+b''.join(rom[p*4096:p*4096+4096].ljust(4096,b'\0') for p in pages)
open(D+'/rompack.bin','wb').write(b)
print('rompack: %d pages (%d KiB)'%(len(pages),len(b)//1024))
