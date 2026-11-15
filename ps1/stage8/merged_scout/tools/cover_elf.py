import sys,os,pickle,collections
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import elfsyms,disc
disc.SF_HI=0x081b0000+0x94e8c
P=pickle.load(open(sys.argv[2],'rb'))
fs,secs,_=elfsyms.load(sys.argv[1])
miss=[];hit=0;tb=0;mb=0
# ground truth: size by mapping symbols of .text code bytes vs discovered bytes in the SF text range
for a,sz,nm,mode,sec in fs:
    if sec!='.text' or sz==0: continue
    if a in P.ins: hit+=1
    else: miss.append((sz,a,nm))
print('SF .text FUNC symbols with size>0: found by discovery %d, missed %d (%d bytes)'%(hit,len(miss),sum(m[0] for m in miss)))
for sz,a,nm in sorted(miss,reverse=True)[:40]: print('  %08x %5d %s'%(a,sz,nm))
cov=set()
for a,i in P.ins.items():
    if disc.in_sf(a) or 0x081b0000<=a<0x08244e8c: cov.update(range(a,a+i.size))
print('SF text bytes decoded as instructions',len(cov),'of Thumb+ARM code bytes (mapping syms)',227502+860)
