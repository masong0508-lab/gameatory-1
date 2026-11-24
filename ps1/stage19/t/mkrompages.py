#!/usr/bin/env python3
"""ROM pages read at run time by the scenario -> the pages preloaded into the disc's rompack (most-read first, at most N) and the page cache geometry.
usage: mkrompages.py PAGES N coldtab_P.bin OUT_rompages.pkl   prints PCACHE_ADDR and NSLOT for the build (memory map: coldtab 0x8011c000, rompack, page cache, draw list 0x8017c000)
PAGES is either snapdump.py's touched.pkl.rompages (a pickled {page: read count}) or a text list (*.txt): page numbers in hex, most important
first, '#' starts a comment.  A text list must hold at least N pages; it carries no ROM data, only page indices."""
import sys,pickle,os
src=sys.argv[1]; N=int(sys.argv[2]); ctab=os.path.getsize(sys.argv[3])
if src.endswith('.txt'):
    order=[int(t,16) for line in open(src) for t in line.split('#',1)[0].split()]
    assert len(order)==len(set(order)),'duplicate page in %s'%src
    assert len(order)>=N,'%s lists %d pages, %d wanted'%(src,len(order),N)
    lim=int(os.environ.get('ROMPAGES','2048'))     # Milestone B: 4096 for the 16 MiB merged ROM
    assert all(0<=p<lim for p in order),'page outside the %d-page window'%lim
    pg={p:len(order)-i for i,p in enumerate(order)}
else:
    pg=pickle.load(open(src,'rb'))
top=sorted(pg,key=lambda p:-pg[p])[:N]
pickle.dump(sorted(top),open(sys.argv[4],'wb'))
start=(0x8011c000+ctab+15)&~15; end=start+4+4*len(top)+4096*len(top)
pc=(end+0xfff)&~0xfff; ns=((0x8017c000-pc)//16384)*4
assert ns>=16,'page cache too small: %d slots'%ns
print('pages touched %d, in rompack %d (%d KiB), PCACHE_ADDR=0x%08x NSLOT=%d'%(len(pg),len(top),(end-start)//1024,pc,ns),file=sys.stderr)
print('-DPCACHE_ADDR=0x%08x -DNSLOT=%d'%(pc,ns))
