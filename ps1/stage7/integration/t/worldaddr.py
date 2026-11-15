#!/usr/bin/env python3
"""worldaddr.py PRDIR : address of the renderer's world window = end of the cold prefix of PRDIR (tier 0 for the title-boot disc), rounded up to 2 KiB; asserts the biggest map (239616 bytes) fits below SF_PBUF (0x80108000)."""
import pickle,os,sys
P=sys.argv[1]; m=pickle.load(open('out/%s/meta_P.pkl'%P,'rb'))['cold']; sz=os.path.getsize('out/%s/cold_P.bin'%P); e=m['start']+((sz+2047)&~2047); w=(e+2047)&~2047     # the preload reads whole sectors
assert 0x80108000-w>=239616,('world window too small',hex(w))
print('0x%08x'%w)
