#!/usr/bin/env python3
"""ROM pages read at run time by the scenario (snapdump.py writes touched.pkl.rompages) -> the pages preloaded into the disc's rompack (most-read first, at most N) and the page cache geometry.
usage: mkrompages.py touched.pkl.rompages N coldtab_P.bin OUT_rompages.pkl   prints PCACHE_ADDR and NSLOT for the build (memory map: coldtab 0x8011c000, rompack, page cache, draw list 0x8017c000)"""
import sys,pickle,os
pg=pickle.load(open(sys.argv[1],'rb')); N=int(sys.argv[2]); ctab=os.path.getsize(sys.argv[3])
top=sorted(pg,key=lambda p:-pg[p])[:N]
pickle.dump(sorted(top),open(sys.argv[4],'wb'))
start=(0x8011c000+ctab+15)&~15; end=start+4+4*len(top)+4096*len(top)
pc=(end+0xfff)&~0xfff; ns=((0x8017c000-pc)//16384)*4
assert ns>=16,'page cache too small: %d slots'%ns
print('pages touched %d, in rompack %d (%d KiB), PCACHE_ADDR=0x%08x NSLOT=%d'%(len(pg),len(top),(end-start)//1024,pc,ns),file=sys.stderr)
print('-DPCACHE_ADDR=0x%08x -DNSLOT=%d'%(pc,ns))
