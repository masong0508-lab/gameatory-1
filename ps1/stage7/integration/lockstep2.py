#!/usr/bin/env python3
"""Lockstep for the pruned/PS1-layout build: ARM original (stubs hooked) vs translated MIPS in the PS1 memory layout (ROM only via RT_MEMRD).
sync = every vblank / DISPCNT write ("tick").  Compared: I/O write sequence, draw list, EWRAM/IWRAM/PAL/VRAM/OAM at each tick.
usage: lockstep2.py ROM OUTDIR TAG NTICKS [every] [pad-list]   env BOOT=file to write the boot image at guest main"""
import sys,os,struct,time,pickle,collections
sys.path.insert(0,'.')
import numpy as np
from gbaenv import *
from msim import MSim
import t2m,prune
rom=open(sys.argv[1],'rb').read(); OUT=sys.argv[2]; TAG=sys.argv[3]; NT=int(sys.argv[4]); EVERY=int(sys.argv[5]) if len(sys.argv)>5 else 1
PAD=eval(sys.argv[6]) if len(sys.argv)>6 else [0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81]
cfg=t2m.Cfg('P')
blob=open(OUT+'/payback_%s.bin'%TAG,'rb').read(); meta=pickle.load(open(OUT+'/meta_%s.pkl'%TAG,'rb'))
coldb=open(OUT+'/cold_%s.bin'%TAG,'rb').read(); coldt=open(OUT+'/coldtab_%s.bin'%TAG,'rb').read()
gmap={}
for l in open(OUT+'/payback_%s.map'%TAG):
    a,h=l.split(); gmap[int(a,16)]=int(h,16)
invs=collections.defaultdict(set)
for g_,h_ in gmap.items(): invs[h_].add(g_)
MAIN=0x08022dc8
class SyncIo(Io):
    def __init__(s,side=None): super().__init__(); s.side=side; s.nd=0; s.snaps={}; s.dls={}
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=PAD[(s.nd//30)%len(PAD)]
        return super().read(off,size)
    def tick(s):
        s.nd+=1
        if s.nd%EVERY==0 or s.nd<=3: s.snaps[s.nd]=s.side.snap(); s.dls[s.nd]=s.side.dlsnap()
        if s.nd>=NT: s.side.u.emu_stop()
    def vblank(s): super().vblank(); s.tick()
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.tick()
class Arm2(ArmSide):
    def snap(s): return {nm:np.frombuffer(s.ram(nm),dtype='<u4').copy() for nm in('EWRAM','IWRAM','PAL','VRAM','OAM')}
    def dlsnap(s): return len(s.dl)
class Mips2(MSim):
    def snap(s):
        d={}
        for nm in('EWRAM','IWRAM'): d[nm]=norm_words(cfg,s.ram(nm),0,None)
        for nm in('PAL','VRAM','OAM'): d[nm]=np.frombuffer(s.ram(nm),dtype='<u4').copy()
        return d
    def dlsnap(s): return s.dlist()[0]
A=Arm2.__new__(Arm2); ioa=SyncIo(A); Arm2.__init__(A,rom,ioa,stubs=prune.stub_by_addr())
M=Mips2.__new__(Mips2); iom=SyncIo(M); Mips2.__init__(M,rom,iom,cfg,blob,meta['rt'],gmap,cold=((coldb,coldt,meta['cold']['start']) if coldb else None),rpages=(pickle.load(open(os.environ['PAGES'],'rb')) if os.environ.get('PAGES') else ()))
bootdone=[False]
def atmain(uc,a,sz,ud):
    if bootdone[0]: return
    bootdone[0]=True
    if os.environ.get('BOOT'):
        regs=[M.r(k) for k in range(32)]
        img=b''.join(M.ram(n) for n in('EWRAM','IWRAM','PAL','VRAM','OAM'))+bytes(iom.regs)
        st=[iom.vc,iom.nread,iom.tm[0],iom.tm[1],iom.tm[2],iom.tm[3],iom.nd,0]
        open(os.environ['BOOT'],'wb').write(struct.pack('<32I',*regs)+struct.pack('<8I',*st)+img)
        print('boot image written at main, tick',iom.nd,'regs',[hex(x) for x in regs[16:24]],'sp',hex(regs[30]),'lr',hex(regs[31]))
    M.protect_rom()
M.u.hook_add(UC_HOOK_CODE,atmain,None,gmap[MAIN],gmap[MAIN])
t0=time.time()
try: A.u.emu_start(0x08000000,0,count=int(os.environ.get('MAXINS','4000000000')))
except Exception as e: print('ARM exc',e)
print('ARM done: ticks',ioa.nd,'io',len(ioa.log),'dl',len(A.dl),round(time.time()-t0,1),'s')
try: M.u.emu_start(gmap[0x08000000],0,count=int(os.environ.get('MAXINS','4000000000'))*3)
except Exception as e: print('MIPS exc',e,hex(M.u.reg_read(UC_MIPS_REG_PC)),'ra',hex(M.r(31)))
print('MIPS done: ticks',iom.nd,'io',len(iom.log),'dl',M.dlist()[0],'memrd',M.nmemrd,'memwr',M.nmemwr,'rompages',len(M.rompages),'ovl loads',M.ovl_loads,'ovl calls',M.ovl_calls,'misses',[hex(x) for x in M.misses],'errs',M.errs[:5],round(time.time()-t0,1),'s')
la,lm=ioa.log,iom.log
if os.environ.get('RDLOG'): pickle.dump(M.rdlog,open(os.environ['RDLOG'],'wb'))
if os.environ.get('LOGDUMP'): pickle.dump(la,open(os.environ['LOGDUMP'],'wb'))
n=min(len(la),len(lm)); bad=next((i for i in range(n) if la[i]!=lm[i]),None)
print('io writes arm %d mips %d first mismatch %s'%(len(la),len(lm),None if bad is None else (bad,la[bad],lm[bad])))
# draw lists
dn,dm=M.dlist()
ad=A.dl[-len(dm):] if len(dm)<len(A.dl) else A.dl
def nrm(v):
    for g,n_,h in cfg.reg:
        if h<=v<=h+n_: return g+v-h
    return v
dbad=[(k,x,y) for k,(x,y) in enumerate(zip(ad,[tuple(nrm(v) for v in e) for e in dm])) if x!=y]
print('draw list: arm %d mips %d compared last %d mismatches %d'%(len(A.dl),dn,len(dm),len(dbad)),dbad[:2])
tot=collections.Counter(); shown=0
for k in sorted(set(ioa.snaps)&set(iom.snaps)):
    sa,sm=ioa.snaps[k],iom.snaps[k]; msg=''
    for nm in sa:
        a,m=sa[nm],sm[nm]
        d=np.nonzero(a!=m)[0]
        d=[x for x in d if (int(a[x])&~1) not in invs.get(int(m[x]),())]
        tot[nm]+=len(d)
        if d: msg+='  %s:%d first@%x a=%08x m=%08x'%(nm,len(d),4*d[0],a[d[0]],m[d[0]])
    if msg and shown<10: print('tick',k,msg); shown+=1
print('snapshots compared',len(set(ioa.snaps)&set(iom.snaps)),'word diffs',dict(tot))
print('ROM pages touched via helper: %d (%d KiB)'%(len(M.rompages),4*len(M.rompages)))
pg=set(M.rompages)
for e in A.dl:     # descriptor words the PS1 draw code reads (w,h) for blit boxes
    if e[0] in (2,4) and (e[1]>>24) in (8,10,12): pg.add((e[1]&0x1ffffff)>>12); pg.add(((e[1]&0x1ffffff)+3)>>12)
print('ROM pages incl. draw-list descriptors: %d (%d KiB)'%(len(pg),4*len(pg)))
pickle.dump(sorted(pg),open(OUT+'/rompages_%s.pkl'%TAG,'wb'))
