#!/usr/bin/env python3
"""Function-level differential fuzz: every discovered function entry is run on unicorn-ARM (original) and unicorn-MIPS (translated) from the
same realistic RAM state (the boot state after NBOOT frames) with the same random arguments / callee registers / stack words.
Compared after return: r0-r12, sp, EWRAM/IWRAM/PAL/VRAM/OAM images (host pointers normalised), and the I/O write sequence.
usage: fuzzfn.py ROM OUTDIR PROGPKL TRIALS [NBOOT] [SEED] [limit_functions]"""
import sys,struct,random,pickle,time,collections
sys.path.insert(0,'.')
import numpy as np
from gbaenv import *
import t2m,disc
rom=open(sys.argv[1],'rb').read(); OUT=sys.argv[2]; PP=sys.argv[3]; TRIALS=int(sys.argv[4])
NBOOT=int(sys.argv[5]) if len(sys.argv)>5 else 300
random.seed(int(sys.argv[6]) if len(sys.argv)>6 else 1)
ONFLY=1
LIM=int(sys.argv[7]) if len(sys.argv)>7 else 10**9
cfg=t2m.Cfg('B'); blob=open(OUT+'/payback_B.bin','rb').read(); meta=pickle.load(open(OUT+'/meta_B.pkl','rb'))
gmap={}
for l in open(OUT+'/payback_B.map'):
    a,h=l.split(); gmap[int(a,16)]=int(h,16)
inv={h:g for g,h in gmap.items()}
invs=collections.defaultdict(set)
for g_,h_ in gmap.items(): invs[h_].add(g_)
entries=set(meta['entries'])
P=pickle.load(open(PP,'rb'))
funcs=sorted(a for a in (P.callt|set(getattr(P,'orph',[]))|set(getattr(P,'dptr',[]))) if a in P.ins and a in gmap and (a>>24==8 or a>>24==3))
funcs=funcs[:LIM]
ONLY=[int(x,16) for x in __import__('os').environ.get('ONLY','').split(',') if x]
if ONLY: funcs=[f for f in ONLY if f in set(funcs)]
NR=['EWRAM','IWRAM','PAL','VRAM','OAM']
class BIo(Io):
    def __init__(s,h): super().__init__(); s.h=h; s.nd=0; s.stopat=None
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2:
            s.nd+=1
            if s.stopat and s.nd>=s.stopat: s.h[0].emu_stop()
ha=[None]; hm=[None]; ioa=BIo(ha); iom=BIo(hm)
A=ArmSide(rom,ioa); ha[0]=A.u
M=MipsSide(rom,iom,cfg,blob,meta['rt'],entries); hm[0]=M.u
Z4K=bytes(0x1000)
DIRTY={id(A.u):set(),id(M.u):set()}
def romw(uc,acc,addr,sz,val,ud):
    DIRTY[id(uc)].add(addr&~0xfff)
for uc_ in (A.u,M.u): uc_.hook_add(UC_HOOK_MEM_WRITE,romw,None,0x08000000,0x087fffff)
MISS=[]; SWIS=[]
def miss_hook(uc,a_,sz,ud): MISS.append(M.r(25))
def swi_hook(uc,a_,sz,ud): SWIS.append(M.r(25))
RTM=meta['rt']['RT_MISS']; RTS=meta['rt']['RT_SWI']
M.u.hook_add(UC_HOOK_CODE,miss_hook,None,RTM,RTM)
M.u.hook_add(UC_HOOK_CODE,swi_hook,None,RTS,RTS)
ODP={id(A.u):set(),id(M.u):set()}
def unm(uc,acc,addr,sz,val,ud):
    if addr>=0x00100000: return False      # only the low 1 MB is demand-mapped (zero pages); other wild pointers fault and the trial is skipped
    try: uc.mem_map(addr&~0xfff,0x1000); ODP[id(uc)].add(addr&~0xfff); return True
    except Exception: return False
if ONFLY:
    pass
ioa.stopat=iom.stopat=NBOOT
A.u.emu_start(0x08000000,0,count=2000000000)
for uc_ in (A.u,M.u):
    uc_.hook_add(UC_HOOK_MEM_READ_UNMAPPED|UC_HOOK_MEM_WRITE_UNMAPPED|UC_HOOK_MEM_FETCH_UNMAPPED,unm)
M.u.emu_start(gmap[0x08000000],0,count=4000000000)
print('boot to frame',NBOOT,'arm nd',ioa.nd,'mips nd',iom.nd,flush=True)
baseA={n:A.ram(n) for n in NR}; baseM={n:M.ram(n) for n in NR}
ioregs=bytes(ioa.regs); 
pools=[]
# argument pool built from the live state: RAM words that are RAM pointers, ROM pointers, small ints
ew=np.frombuffer(baseA['EWRAM'],dtype='<u4'); iw=np.frombuffer(baseA['IWRAM'],dtype='<u4')
ptrs=[int(x) for x in np.concatenate([ew[(ew>>24)==2][:3000],iw[(iw>>24)==3][:3000]])]
SENT_A=0x08700000; SENT_M=0x81fff000
SP_A=0x03007f00
def mapv(v): h=cfg.host(v); return v if h is None else h
def rnd_arg(allow_ptr=True):
    """integers / ROM addresses; with allow_ptr also RAM-region pointers (those make host-pointer arithmetic observable: model-B limit)"""
    while True:
        r=random.random()
        if r<.15: return 0
        if r<.35: return random.randrange(0,16)
        if r<.5: return random.randrange(0,300)
        if r<.65:
            if allow_ptr and ptrs: return random.choice(ptrs)
            continue
        if r<.75:
            if allow_ptr: return 0x02000000+4*random.randrange(0,0x10000)
            continue
        if r<.82:
            if allow_ptr: return 0x03000000+4*random.randrange(0,0x1f80)
            continue
        if r<.88: return 0x08000000+4*random.randrange(0,0x1f0000)
        if r<.92: return (-random.randrange(1,100))&0xffffffff
        return random.getrandbits(16)
DELTAS={(h-g)&0xffffffff for g,n,h in cfg.reg}
def eqv(a,b):
    if ((b-a)&0xffffffff) in DELTAS: return True     # same linear pointer arithmetic on host vs guest base (incl. out-of-range indexes)
    if a==b or (cfg.host(a) is not None and b==cfg.host(a)): return True
    if (a&~1)==SENT_A and b==SENT_M: return True
    return (a&~1) in invs.get(b,())
def reset(side,io,base):
    if side is A:
        for n in NR: A.u.mem_write(dict((a,b) for a,b,_ in REGIONS)[n],base[n])
    else:
        for n in NR: M.u.mem_write(P_(M.hostbase[n]),base[n])
    for pg in ODP[id(side.u)]: side.u.mem_write(pg,Z4K)
    dp=DIRTY[id(side.u)]
    if dp:
        for pg in dp: side.u.mem_write(pg,rom[pg-0x08000000:pg-0x08000000+0x1000])
        if side is M: M.seen={x for x in M.seen if (x&~0xfff) not in dp}
        dp.clear()
    io.regs[:]=ioregs; io.log=[]; io.nread=0; io.vc=0; io.tm=[0]*4; io.nwr=0
def P_(h): return h&0x1fffffff if h>=0x80000000 else h
GMAP=MipsSide.GM
FAULTS=[]
MISSED=collections.Counter()
TRACEALL=int(__import__('os').environ.get('TRACEALL','0')); TA=[]; TM=[]
PCS=[int(x,16) for x in __import__('os').environ.get('PCS','').split(',') if x]
import bisect
hs_=sorted(inv)
def execute(f,thumb,regs,stack,trace=False):
    reset(A,ioa,baseA); reset(M,iom,baseM); del MISS[:]; del SWIS[:]
    ta=[]; tm=[]; hs=[]
    if trace:
        for n,gb_,sz_ in REGIONS:
            if n in('SRAM',): continue
            hb=cfg.host(gb_)&0x1fffffff
            hs.append((A.u,A.u.hook_add(UC_HOOK_MEM_WRITE,lambda uc,acc,addr,sz,val,ud,gb_=gb_: ta.append((addr,sz,val&((1<<8*sz)-1),uc.reg_read(UC_ARM_REG_PC))),None,gb_,gb_+sz_-1)))
            hs.append((M.u,M.u.hook_add(UC_HOOK_MEM_WRITE,lambda uc,acc,addr,sz,val,ud,hb=hb,gb_=gb_: tm.append((addr-hb+gb_,sz,val&((1<<8*sz)-1),inv.get(hs_[bisect.bisect_right(hs_,uc.reg_read(UC_MIPS_REG_PC))-1],0))),None,hb,hb+sz_-1)))
    if trace and PCS:
        for pc_ in PCS:
            hs.append((A.u,A.u.hook_add(UC_HOOK_CODE,lambda uc,a_,sz,ud: print('      ARM @%x'%a_,[hex(uc.reg_read(UC_ARM_REG_R0+k)) for k in range(8)],'NZCV',hex(uc.reg_read(UC_ARM_REG_CPSR)>>28)),None,pc_,pc_)))
            hs.append((M.u,M.u.hook_add(UC_HOOK_CODE,lambda uc,a_,sz,ud: print('      MIPS @%x'%inv.get(a_,0),[hex(M.r(GMAP[k])) for k in range(8)],'NZCV',[M.r(r) for r in(4,5,6,7)]),None,gmap[pc_],gmap[pc_])))
    if trace and TRACEALL:
        def ca(uc,a_,sz,ud): TA.append((a_,tuple(uc.reg_read(UC_ARM_REG_R0+k) for k in range(13))))
        def cm(uc,a_,sz,ud):
            g=inv.get(a_)
            if g is not None: TM.append((g,tuple(M.r(GMAP[k]) for k in range(13))))
        hs.append((A.u,A.u.hook_add(UC_HOOK_CODE,ca)))
        hs.append((M.u,M.u.hook_add(UC_HOOK_CODE,cm,None,cfg.BASE,cfg.BASE+len(blob))))
    if trace and (PCS or TRACEALL):
        A.u.ctl_flush_tb(); M.u.ctl_flush_tb()
    u=A.u
    u.reg_write(UC_ARM_REG_CPSR,0x1f|(0x20 if thumb else 0))
    for k in range(13): u.reg_write(UC_ARM_REG_R0+k,regs[k])
    u.reg_write(UC_ARM_REG_SP,SP_A); u.reg_write(UC_ARM_REG_LR,SENT_A|(1 if thumb else 0))
    u.mem_write(SP_A,struct.pack('<16I',*stack))
    st=None
    try: u.emu_start(f|(1 if thumb else 0),SENT_A,count=400000)
    except Exception as e: st='arm_fault'
    if st is None and u.reg_read(UC_ARM_REG_PC)&~1!=SENT_A: st='arm_timeout'
    err=None
    if st is None:
        m=M.u
        for k in range(13): M.setr(GMAP[k],mapv(regs[k]))
        M.setr(30,mapv(SP_A)); M.setr(31,SENT_M)
        for r in(4,5,6,7): M.setr(r,0)
        m.mem_write(P_(mapv(SP_A)),struct.pack('<16I',*stack))
        try: m.emu_start(gmap[f],SENT_M,count=4000000)
        except Exception as e: err=str(e)
    for uc_,h in hs: uc_.hook_del(h)
    return st,err,ta,tm
stats=collections.Counter(); bad=collections.defaultdict(list); t0=time.time()
for fi,f in enumerate(funcs):
    thumb=P.ins[f].mode=='T'
    for tr in range(TRIALS):
        kind=tr&1 if TRIALS>1 else 0      # even trials: integer-only arguments; odd trials: RAM pointers allowed
        regs=[rnd_arg(kind==1) if k<4 else (random.randrange(0,64) if random.random()<.7 else rnd_arg(kind==1)) for k in range(13)]
        stack=[random.randrange(0,64) for _ in range(16)]
        st,err,ta,tm=execute(f,thumb,regs,stack)
        if st: stats[st]+=1; continue
        stats['ran_k%d'%kind]+=1
        m=M.u
        if err and 'UNALIGNED' in err: stats['skip_unaligned']+=1; continue     # ARM rotate-on-unaligned semantics are not translated (R3000 traps)
        if MISS or SWIS:
            stats['rt_miss_trial' if MISS else 'swi_trial']+=1
            for t_ in MISS: MISSED[t_>>12]+=1
            continue      # unresolved indirect target / BIOS call: reported separately, not compared
        stats['ran']+=1
        why=[]
        if err or m.reg_read(UC_MIPS_REG_PC)!=SENT_M:
            why.append('mips_fault' if err else 'mips_timeout')
            fp=m.reg_read(UC_MIPS_REG_PC); stats['f:'+(err or 'timeout')[:28]]+=1
            FAULTS.append((f,hex(inv.get(fp,0)) if fp in inv else hex(fp),err,[hex(x) for x in regs[:4]]))
        else:
            ra=[A.r(k) for k in range(15)]; rm=M.gregs()
            for k in range(14):
                a=ra[k]; b=rm[k]
                ok=eqv(a,b)
                if k==13: ok=(rm[13]==mapv(SP_A))
                if not ok: why.append('r%d'%k)
            if ioa.log!=iom.log: why.append('io')
            for n in NR:
                a=np.frombuffer(A.ram(n),dtype='<u4')
                if n in('EWRAM','IWRAM'): b=norm_words(cfg,M.ram(n),0,entries)
                else: b=np.frombuffer(M.ram(n),dtype='<u4')
                d=np.nonzero(a!=b)[0]
                d=[x for x in d if not eqv(int(a[x]),int(b[x]))]
                if d:
                    why.append('ram_'+n)
                    if stats['mismatch']<int(__import__('os').environ.get('SHOW','8')): print('   ',hex(f),n,len(d),[(hex(4*x),hex(int(a[x])),hex(int(b[x]))) for x in d[:5]],'sp',hex(SP_A))
        if why:
            stats['mismatch']+=1; stats['mismatch_k%d'%kind]+=1
            for w in why: stats['m_'+w]+=1
            bad[f].append((tr,why,regs[:4]))
            if kind==0 and len(bad[f])==1 and stats['mismatch_k0']<=int(__import__('os').environ.get('SHOW','8')):
                del TA[:]; del TM[:]
                _,_,ta,tm=execute(f,thumb,regs,stack,True)
                if TRACEALL:
                    print('    insn trace lens',len(TA),len(TM))
                    qa=0; qm=0
                    while qa<len(TA) and qm<len(TM):
                        pa,ra_=TA[qa]; pm,rm_=TM[qm]
                        if (pa&~1)!=pm:      # resync over instructions that have no code of their own (folded) on either side
                            for d_ in range(1,8):
                                if qa+d_<len(TA) and (TA[qa+d_][0]&~1)==pm: qa+=d_; break
                                if qm+d_<len(TM) and TM[qm+d_][0]==(pa&~1): qm+=d_; break
                            else:
                                print('    PATH DIVERGENCE at arm#%d pc %x vs mips#%d pc %x'%(qa,pa,qm,pm))
                                for z in range(max(0,qa-4),qa+1): print('       ',hex(TA[z][0]),[hex(x) for x in TA[z][1][:9]])
                                break
                            continue
                        if not all(eqv(x,y) for x,y in zip(ra_,rm_)):
                            print('    FIRST REG DIVERGENCE at arm#%d pc %x (state before executing it)'%(qa,pa))
                            for z in range(max(0,qa-4),qa+1): print('       arm',hex(TA[z][0]),[hex(x) for x in TA[z][1][:9]])
                            for z in range(max(0,qm-4),qm+1): print('       mips',hex(TM[z][0]),[hex(x) for x in TM[z][1][:9]])
                            break
                        qa+=1; qm+=1
                for i_ in range(min(len(ta),len(tm))):
                    if ta[i_][:2]!=tm[i_][:2] or not eqv(ta[i_][2],tm[i_][2]):
                        print('    first store divergence #%d'%i_,'arm addr %x sz %d val %x pc %x | mips addr %x sz %d val %x gpc %x'%(ta[i_]+tm[i_]) if False else ('arm',[hex(x) for x in ta[i_]],'mips',[hex(x) for x in tm[i_]])); break
                else: print('    stores equal',len(ta),len(tm))
            if stats['mismatch']<=int(__import__('os').environ.get('SHOW','8')) and not err: print('  MISMATCH',hex(f),why,'args',[hex(x) for x in regs[:4]],'arm',[hex(x) for x in ra[:6]],'mips',[hex(x) for x in rm[:6]])
        else: stats['ok']+=1
    if (fi+1)%50==0: print('  %d/%d funcs %s %.0fs'%(fi+1,len(funcs),dict(stats),time.time()-t0),flush=True)
print('functions',len(funcs),'trials',TRIALS,'->',dict(stats),'funcs with mismatch',len(bad),'%.0fs'%(time.time()-t0))
pickle.dump({f:v for f,v in bad.items()},open(OUT+'/fuzzfn_bad.pkl','wb'))
print('rt_miss target pages',[(hex(k<<12),v) for k,v in MISSED.most_common(12)])
for x in FAULTS[:12]: print('fault',hex(x[0]),x[1:])
for f in list(bad)[:25]: print(hex(f),P.ins[f].mode,bad[f][0])
