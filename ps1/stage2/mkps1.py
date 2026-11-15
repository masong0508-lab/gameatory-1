#!/usr/bin/env python3
"""Packaging for the PS1 build (our tool, code only): usage mkps1.py ROM OUTDIR TAG BOOTIMG ROMPAGES.pkl DESTDIR
Writes DESTDIR/{syms.c,blob.s,rompack.bin,...}; ROM data pages (resident set) are cut from the user's ROM into rompack.bin (local build output)."""
import sys,struct,pickle
rom=open(sys.argv[1],'rb').read(); OUT=sys.argv[2]; TAG=sys.argv[3]; BOOT=sys.argv[4]; PAGES=pickle.load(open(sys.argv[5],'rb')); D=sys.argv[6]
gmap={}
for l in open(OUT+'/payback_%s.map'%TAG):
    a,h=l.split(); gmap[int(a,16)]=int(h,16)
import os
L=[int(x) for x in os.environ.get('LBAS','0,0,0').split(',')]
meta=pickle.load(open(OUT+'/meta_%s.pkl'%TAG,'rb'))
open(D+'/syms.c','w').write('unsigned GUEST_MAIN_HOST=0x%08x;\nconst unsigned COLD_HOST=0x%08x;\nconst unsigned CD_ROM_LBA=%d, CD_COLD_LBA=%d, CD_COLD_PAGES=%d;\n'%(gmap[0x08022dc8],meta['cold']['start'],L[0],L[1],L[2]))
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
