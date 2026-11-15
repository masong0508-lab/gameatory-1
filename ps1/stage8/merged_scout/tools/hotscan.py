#!/usr/bin/env python3
"""hotscan.py ELF IW OUT : the Stunt Fox IWRAM overlays (.hot .. .hot11: ARM code lent over Payback's IWRAM image at run time).  Builds the SF-version IWRAM image
(Payback's image + the sections), discovers from the ELF's function symbols (ground truth; plus the thunks), runs the translator on it and reports instructions/words
and unsupported constructs.  Also checks the sections against the ROM's hot LMA copies."""
import sys,os,subprocess,pickle,collections,tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import elfsyms,disc,t2m,prune,mips as M
elf,iwp=sys.argv[1],sys.argv[2]   # usage: hotscan.py ELF IW.bin [ROM]
fs,secs,_=elfsyms.load(elf)
iw=bytearray(open(iwp,'rb').read()); tmp=tempfile.mkdtemp()
hot={n:v for n,v in secs.items() if n.startswith('.hot')}
for n,(a,sz) in sorted(hot.items(),key=lambda kv:kv[1]):
    p=os.path.join(tmp,n); subprocess.run(['llvm-objcopy','--dump-section',n+'='+p,elf,os.devnull],check=False,capture_output=True)
    d=open(p,'rb').read(); iw[a&0x7fff:(a&0x7fff)+len(d)]=d
    print('%-7s %08x +%4d'%(n,a,sz))
open(os.path.join(tmp,'iw_sf.bin'),'wb').write(iw)
seeds=[(a,'A') for a,sz,nm,mode,sec in fs if sec and sec.startswith('.hot')]
for n,(a,sz) in hot.items(): seeds.append((a,'A'))
disc.IWCODE_END=0x03007400
rom=open(sys.argv[3],'rb').read() if len(sys.argv)>3 else b''   # the merged ROM (only for literal reads of ARM code that points into ROM)
img=disc.Img(rom,bytes(iw))
P=disc.Prog(img); P.run(seeds)
# thunks the SF Thumb code uses to enter the hot code (lld veneers in .text: ARM bx/ldr pc)
n=len(P.ins); ar=sum(1 for i in P.ins.values() if i.mode=='A')
print('hot overlay discovery: %d insns (ARM %d, Thumb %d), bad %d, indirect sites %d'%(n,ar,n-ar,P.bad,len(P.indirect)))
inh=sum(i.size for a,i in P.ins.items())
print('decoded bytes %d of section bytes %d'%(inh,sum(sz for a,sz in hot.values())))
ops=collections.Counter(i.op for i in P.ins.values()); print(dict(ops))
for a in P.indirect: i=P.ins[a]; print('  indirect %08x %s %s'%(a,i.op,getattr(i,'raw',None) and hex(i.raw)))
T=t2m.Tr(P,t2m.Cfg('P'),False); T.run(); it,nh=M.hazard_pass(T.A.it); w=sum(1 for x in it if not (isinstance(x,tuple) and x[0]=='L'))
print('translated: %d MIPS words = %.1f KiB (%.2fx), hazard nops %d'%(w,w*4/1024,w/n,nh)); print('stats',dict(T.st)); print('unsafe',dict(T.unsafe))
print('self-modifying / pc-relative stores:',sum(1 for i in P.ins.values() if i.op=='mem' and not i.ld and i.rn==15))
