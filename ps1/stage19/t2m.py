#!/usr/bin/env python3
"""t2m: static translator GBA ARM7TDMI (Thumb + ARM) -> MIPS-I (R3000).  Our own code; reads the user's ROM, writes a
binary blob + map in a scratch directory.  Usage: t2m.py ROM IWRAM_IMAGE OUTDIR [--map B|ident]

Register map: r0-r7 -> $16-$23, r8-r12 -> $11-$15, sp -> $30, lr -> $31 (jal writes it), temps $1 $2 $3 $8 $9 $10 $24 $25 $28 $29,
explicit flag registers N=$4 Z=$5 C=$6 V=$7 (0/1); $26/$27 untouched.  Flags are lazy: fused with the consumer where the
walk in `decide` proves the operands intact and no join in between, else materialised into $4-$7 (only the live bits).
Memory model B: constants in RAM/IO/pal/VRAM/OAM/SRAM regions become host addresses; ROM and code pointers stay guest values
(indirect jumps go through a hash lookup, guest ROM data reads are served by the harness / cache)."""
import sys,struct,collections,pickle,os,time,bisect
import armdec as D
from armdec import *
import semantics as S
import mips as M
from mips import *
import disc
class Cfg:
    BASE=0x81000000
    ROMPG=0x8002a000       # 2048 x u32: host pointer of each resident 4 KiB ROM page (0 = not resident -> C slow path)
    ROMPG_N=int(os.environ.get('T2M_ROMPG_N','2048'))   # Milestone B: 4096 for the 16 MiB merged ROM (0x8002a000..0x8002e000); 2048 = every original-game build
    HELP=0x80028000        # table of C helper pointers filled by the PS1 runtime: [0]=memrd [1]=memwr [2]=miss
    PLAIN=(0x80180000,0x80200000)
    DL=0x801a0000          # draw-list ring (host address)
    def __init__(s,mode='B'):
        s.mode=mode
        s.BASE=Cfg.BASE
        # (guest base, size, host base)
        if mode=='P':
            # PS1 layout. plain window 0x80180000-0x80200000 (PAL,OAM,VRAM,EWRAM,IWRAM; EWRAM directly below IWRAM = GBA mirror semantics)
            s.BASE=0x80030000; s.DL=0x8017c000
            s.reg=[(0x02000000,0x40000,0x801b0000),(0x03000000,0x8000,0x801f0000),(0x04000000,0x400,0x8017f000),(0x05000000,0x400,0x80180000),
                   (0x06000000,0x18000,0x80181000),(0x07000000,0x400,0x80180400)]
        elif mode=='B':
            s.reg=[(0x02000000,0x40000,0x80100000),(0x03000000,0x8000,0x80150000),(0x04000000,0x400,0x80160000),(0x05000000,0x400,0x80170000),
                   (0x06000000,0x18000,0x80190000),(0x07000000,0x400,0x80180000),(0x0e000000,0x10000,0x801c0000)]
        else:
            s.reg=[(0x02000000,0x40000,0x02000000),(0x03000000,0x8000,0x03000000),(0x04000000,0x400,0x04000000),(0x05000000,0x400,0x05000000),
                   (0x06000000,0x18000,0x06000000),(0x07000000,0x400,0x07000000),(0x0e000000,0x10000,0x0e000000)]
    def host(s,v):
        v&=0xffffffff
        if 0x03000000<=v<0x04000000: return s.reg[1][2]+(v&0x7fff)      # IWRAM mirrors every 32 KB
        for g,n,h in s.reg:
            if g<=v<=g+n: return h+v-g
        return None
TEMPS=[1,2,3,8,9,10,24,25,28,29]
FN,FZ,FC,FV=4,5,6,7
FREG={NF:4,ZF:5,CF:6,VF:7}
GM={0:16,1:17,2:18,3:19,4:20,5:21,6:22,7:23,8:11,9:12,10:13,11:14,12:15,13:30,14:31}
class Src:
    __slots__=('kind','a','b','res')
    def __init__(s,kind,a=None,b=None,res=None): s.kind=kind;s.a=a;s.b=b;s.res=res
def bits(m): return [b for b in (NF,ZF,CF,VF) if m&b]
def falls(i):
    if i.op in('undef','stub'): return False
    if i.cond!=14: return True
    if i.op in('b','bx'): return False
    if i.op=='dp' and i.rd==15 and i.opc not in(TST,TEQ,CMP,CMN): return False
    if i.op=='mem' and i.ld and i.rd==15: return False
    if i.op=='ldm' and i.ld and (i.regs>>15)&1: return False
    return True
def gwrites(i):
    """guest registers written by an instruction"""
    op=i.op
    if op=='dp': return set() if i.opc in(TST,TEQ,CMP,CMN) else {i.rd}
    if op=='mem': return ({i.rd} if i.ld else set())|({i.rn} if (i.wb or not i.pre) else set())
    if op=='mul': return {i.rd}
    if op=='mull': return {i.rd,i.rdhi}
    if op=='ldm': return ({r for r in range(16) if i.regs>>r&1} if i.ld else set())|({i.rn} if i.wb else set())
    if op in('mrs','swp'): return {i.rd}
    if op=='bl': return {0,1,2,3,12,14}
    return set()
def mapK(opc_a,opc_b): pass
class Tr:
    def __init__(s,P,cfg,verbose=True):
        s.P=P; s.cfg=cfg; s.img=P.img; s.A=Asm(); s.cur=None; s._ntr=0
        _obr=s.A.br
        def _br(w,lab):      # stage 4: conditional branch to another function's label (tail call): via a trampoline next to the code, so the +-128 KB branch range never matters
            if isinstance(lab,tuple) and lab[0]=='g' and s.cur is not None and s.fn_of(lab[1])!=s.fn_of(s.cur.addr):
                s._ntr+=1; tl=('trj',s._ntr); _obr(w,tl); s.slow.append(('fn',tl,lambda l=lab: s.A.j(l)))
            else: _obr(w,lab)
        s.A.br=_br; s.st=collections.Counter(); s.verbose=verbose
        s.ins=P.ins; s.order=sorted(s.ins)
        s.ent=set(P.entries)|set(P.jt)|set(P.callt)
        s.cold_rank=getattr(P,'cold_rank',None); s.grp=getattr(P,'grp',{}); s.cold=set(getattr(P,'cold',()) or ()); s.funcs=list(getattr(P,'funcs',()) or []); s.miss_t=set(); s.fend={}
        s.unsafe=collections.Counter()
        s.vol=set()    # pc-relative literal slots that are stored to at run time (self-modifying data): loads must be real
        for a_,i_ in s.ins.items():
            if i_.op=='mem' and not i_.ld and i_.rn==15 and i_.imm is not None:
                pc_=(a_+4)&~3 if i_.mode=='T' else a_+8
                s.vol.add((pc_+(i_.imm if i_.up else -i_.imm))&~3)
    # ------------------------------------------------------------------ analysis
    def analyse(s):
        t0=time.time(); ins=s.ins; order=s.order
        s.labels=set(s.ent)
        for a in order:
            i=ins[a]
            if i.op=='b': s.labels.add(i.target)
        s.labels&=set(ins)
        # successor lists, flags liveness
        n=len(order); idx={a:k for k,a in enumerate(order)}; s.idx=idx
        use=[0]*n; dfn=[0]*n; succ=[None]*n; cut=[False]*n
        for k,a in enumerate(order):
            i=ins[a]; u,d=D.flag_use_def(i)
            use[k]=u; dfn[k]=d if i.cond==14 else 0
            sc=[]
            if i.op=='b' and i.target in idx: sc.append(idx[i.target])
            if falls(i) and (a+i.size) in idx: sc.append(idx[a+i.size])
            succ[k]=sc
            if i.op in('bl','swi'): cut[k]=True
        pred=[[] for _ in range(n)]
        for k in range(n):
            for t in succ[k]: pred[t].append(k)
        lin=[0]*n; lout=[0]*n
        work=list(range(n)); inwork=[True]*n
        while work:
            k=work.pop()
            inwork[k]=False
            o=0
            if not cut[k]:
                for t in succ[k]: o|=lin[t]
            lout[k]=o
            ni=use[k]|(o&~dfn[k])
            if ni!=lin[k]:
                lin[k]=ni
                for p in pred[k]:
                    if not inwork[p]: inwork[p]=True; work.append(p)
        s.lin=lin; s.lout=lout; s.use=use
        s.dfn=[0]*n
        for k,a in enumerate(order):
            u,d=D.flag_use_def(ins[a]); s.dfn[k]=d
        if s.verbose: print('  liveness %.1fs'%(time.time()-t0))
        # constant propagation (guest values) at leaders
        s.constprop(pred,succ,idx)
        if s.verbose: print('  constprop done %.1fs'%(time.time()-t0))
    def pcv(s,i): return i.addr+(4 if i.mode=='T' else 8)
    def kstep(s,i,k):
        """update const dict k (guest reg -> value) for instruction i (returns nothing; mutates k)"""
        op=i.op
        if op=='dp':
            if i.opc in(TST,TEQ,CMP,CMN): return
            v=s.kfold(i,k)
            if v is not None and i.cond==14 and i.rd!=15: k[i.rd]=v[0]
            else: k.pop(i.rd,None)
        elif op=='mem':
            if i.ld:
                v=None
                if i.rn==15 and i.imm is not None and i.sz==4 and i.cond==14:
                    pc=s.pcv(i)&~3 if i.mode=='T' else s.pcv(i)
                    ea=(pc+(i.imm if i.up else -i.imm)) if i.pre else pc
                    v=s.img.rd32(ea&~3) if ea&3==0 else None
                    if (ea&~3) in s.vol: v=None
                if v is not None: k[i.rd]=v
                else: k.pop(i.rd,None)
            if (i.wb or not i.pre) and i.rn!=15:
                b=k.get(i.rn)
                if b is not None and i.imm is not None and i.cond==14: k[i.rn]=(b+(i.imm if i.up else -i.imm))&0xffffffff
                else: k.pop(i.rn,None)
        elif op=='mul': k.pop(i.rd,None)
        elif op=='mull': k.pop(i.rd,None); k.pop(i.rdhi,None)
        elif op=='ldm':
            if i.ld:
                for r in range(16):
                    if i.regs>>r&1: k.pop(r,None)
            if i.wb: k.pop(i.rn,None)
        elif op in('mrs','swp'): k.pop(i.rd,None)
        elif op=='bl':
            for r in (0,1,2,3,12,14): k.pop(r,None)
    def kget(s,i,r,k):
        if r==15: return s.pcv(i)
        return k.get(r)
    def kfold(s,i,k):
        """if dp instruction has fully known inputs and no carry-in need: returns (result,) else None"""
        opc=i.opc
        if opc in(ADC,SBC,RSC): return None
        a=None
        if opc not in(MOV,MVN):
            a=s.kget(i,i.rn,k)
            if a is None: return None
        if i.rm is None:
            if i.imm is None: return None
            b=i.imm
        else:
            v=s.kget(i,i.rm,k)
            if v is None: return None
            if i.sh==RRX: return None
            if i.shreg is not None:
                sv=s.kget(i,i.shreg,k)
                if sv is None: return None
                amt=sv&0xff
            else: amt=i.shamt
            if i.sh==LSL and i.shreg is None and amt==0: b=v
            else: b,_=S.shift32(v,i.sh,amt,0)
        r=S.alu(opc,a if a is not None else 0,b,0)[0]
        return (r,)
    def constprop(s,pred,succ,idx):
        ins=s.ins; order=s.order; n=len(order)
        leader=[False]*n
        for a in s.labels: leader[idx[a]]=True
        for k in range(n):
            i=ins[order[k]]
            if not falls(i) or i.cond!=14 and False:
                if k+1<n: leader[k+1]=True
            if k==0: leader[0]=True
        for a in s.ent:
            if a in idx: leader[idx[a]]=True
        kin={}
        entry_unknown=set(idx[a] for a in s.ent if a in idx)
        for k in entry_unknown: kin[k]={}
        work=list(entry_unknown)
        # every leader with unknown preds gets visited by propagation; unreachable leaders left None (-> {})
        for k in range(n):
            if leader[k] and k not in kin and not pred[k]: kin[k]={}; work.append(k)
        def join(a,b):
            return {r:v for r,v in a.items() if b.get(r)==v}
        inq=set(work)
        while work:
            k=work.pop(); inq.discard(k)
            cur=dict(kin[k]); j=k
            while True:
                i=ins[order[j]]
                s.kstep(i,cur)
                nxt=None
                # edges
                if i.op=='b' and i.target in idx:
                    t=idx[i.target]
                    if t in kin:
                        nj=join(kin[t],cur)
                        if nj!=kin[t]: kin[t]=nj; 
                        else: nj=None
                    else: kin[t]=dict(cur); nj=kin[t]
                    if nj is not None and t not in inq: inq.add(t); work.append(t)
                if not falls(i) or j+1>=n or order[j+1]!=order[j]+i.size: break
                if leader[j+1]:
                    t=j+1
                    if t in kin:
                        nj=join(kin[t],cur)
                        if nj!=kin[t]: kin[t]=nj
                        else: nj=None
                    else: kin[t]=dict(cur); nj=kin[t]
                    if nj is not None and t not in inq: inq.add(t); work.append(t)
                    break
                j+=1
        s.kin={order[k]:v for k,v in kin.items()}
        s.leader={order[k] for k in range(n) if leader[k]}
    # ------------------------------------------------------------------ lazy flag decisions
    def lazy_cap(s,i):
        """for a flag-defining instruction: dict bit -> set of guest regs that must stay intact for a lazy source, or None if explicit-only.
        also returns ('kind') info"""
        d={}
        if i.op=='dp' and i.s and i.cond==14:
            opc=i.opc
            plain=(i.rm is None and i.imm is not None) or (i.rm is not None and i.shreg is None and i.sh==LSL and i.shamt==0)
            has_rd=opc not in(TST,TEQ,CMP,CMN)
            ops=set()
            if i.rm is not None and i.rm!=15: ops.add(i.rm)
            if opc in(SUB,ADD,CMP,CMN,RSB) and plain:
                if i.rn!=15: ops.add(i.rn)
                alias=has_rd and i.rd in ops
                rdset={i.rd} if has_rd else set()
                if has_rd:
                    d[NF]=rdset; d[ZF]=rdset
                else: d[NF]=set(ops); d[ZF]=set(ops)
                if alias or (opc==RSB and i.rm is None and i.imm!=0) or i.rn==15 or i.rm==15 or (opc==RSB and i.rm is not None and False):
                    d[CF]=None; d[VF]=None
                else:
                    d[CF]=ops|rdset; d[VF]=ops|rdset
            elif opc in(AND,EOR,ORR,BIC,MOV,MVN) :
                d[NF]={i.rd}; d[ZF]={i.rd}
                if i.rd==15: d[NF]=None; d[ZF]=None
            elif opc in(TST,) and plain and i.rn!=15 and i.rm!=15:
                o={i.rn}|ops; d[NF]=o; d[ZF]=o
            elif opc in(ADC,SBC,RSC) and i.rd!=15: d[NF]={i.rd}; d[ZF]={i.rd}
        elif i.op=='mul' and i.s and i.cond==14: d[NF]={i.rd}; d[ZF]={i.rd}
        return d
    def decide(s):
        """per instruction: set of flag bits that the producer must make explicit ($4-$7)"""
        ins=s.ins; order=s.order; idx=s.idx; s.expl={}
        cnt=collections.Counter()
        for k,a in enumerate(order):
            i=ins[a]
            dm=s.dfn[k] if i.cond==14 else 0
            # conditionally executed flag setters define bits partially
            if i.cond!=14:
                u,d=D.flag_use_def(i)
                dm=d
                live=d&s.lout[k]
                if live: s.expl[a]=live; cnt['cond_producer']+=1
                continue
            live=dm&s.lout[k]
            if not live: continue
            cap=s.lazy_cap(i)
            ex=0
            for b in bits(live):
                O=cap.get(b)
                if O is None: ex|=b; continue
                if not s.walk_ok(k,a,i,b,O): ex|=b
            if ex: s.expl[a]=ex
            cnt['prod']+=1
        s.st['explicit_prod']=sum(1 for v in s.expl.values())
        s.st['lazy_bits']=0
    def walk_ok(s,k,a,P,b,O):
        ins=s.ins; order=s.order; idx=s.idx; lin=s.lin; lout=s.lout
        j=k+1
        n=len(order)
        while True:
            if j>=n or order[j]!=order[j-1]+ins[order[j-1]].size: return False
            aj=order[j]; I=ins[aj]
            if aj in s.labels or aj in s.leader and False:
                return not (lin[j]&b)
            if not (lin[j]&b): return True
            if I.cond!=14:
                u,d=D.flag_use_def(I)
                if d&b: return False
            if I.op=='b':
                t=idx.get(I.target)
                if t is None or (lin[t]&b): return False
                if I.cond==14: return True
            if not falls(I): return True
            if not (lout[j]&b): return True
            if gwrites(I)&O: return False
            j+=1
    # ------------------------------------------------------------------ code generation helpers
    def e(s,*w): s.A.e(*w)
    def tmp(s):
        if not s.tp: raise RuntimeError('out of temps at %x'%s.cur.addr)
        return s.tp.pop(0)
    def mapc(s,v):
        """map a known guest constant to what a register must hold (host-pointer model)"""
        v&=0xffffffff
        h=s.cfg.host(v)
        return v if h is None else h
    def li(s,reg,v,guest=True):
        """load a guest constant into reg, applying region mapping"""
        if guest: v=s.mapc(v)
        s.e(*M.li(reg,v))
    def reg_of(s,o,pool=True):
        """ensure operand ('i',v)/('r',m) is in a register"""
        if o[0]=='r': return o[1]
        if o[1]==0: return 0
        t=s.tmp(); s.li(t,o[1],guest=False); return t
    def G(s,r,i=None):
        return GM[r]
    def aopd(s,i,r,k):
        """operand descriptor of guest register r at instruction i (pc -> constant; known constants stay in register)"""
        if r==15: return ('i',s.pcv(i))
        return ('r',GM[r])
    def addimm(s,rd,ra,v):
        """rd = ra + v (v 32-bit signed or unsigned)"""
        v&=0xffffffff
        if v>=0x80000000: v-=1<<32
        if -32768<=v<=32767:
            if v==0 and rd==ra: return
            s.e(addiu(rd,ra,v)) if v!=0 else s.e(addu(rd,ra,0))
        else:
            t=s.tmp(); s.e(*M.li(t,v&0xffffffff)); s.e(addu(rd,ra,t))
    # ---- condition handling
    def getbit(s,b):
        """return a mips reg holding flag bit b (0/1); scratch temps used on the way are released"""
        src=s.fl.get(b)
        if src is None: return FREG[b]
        pool=list(s.tp)
        t=s._getbit(b,src)
        s.tp=[r for r in pool if r!=t]
        return t
    def _getbit(s,b,src):
        t=s.tmp(); k=src.kind
        if k=='k':
            s.e(*M.li(t,src.a[b])) ; return t
        a=src.a; br=s.reg_of(src.b) if src.b is not None else None
        res=src.res
        if b==ZF:
            if k=='res': s.e(sltiu(t,src.res,1))
            elif k=='sub':
                if res is not None: s.e(sltiu(t,res,1))
                else: s.e(xor(t,a,br),sltiu(t,t,1))
            elif k=='add':
                if res is None: s.e(addu(t,a,br)); s.e(sltiu(t,t,1))
                else: s.e(sltiu(t,res,1))
            elif k=='and': s.e(and_(t,a,br),sltiu(t,t,1))
            elif k=='xor': s.e(xor(t,a,br),sltiu(t,t,1))
        elif b==NF:
            if k=='res': s.e(srl(t,src.res,31))
            elif k in('sub','add'):
                if res is not None: s.e(srl(t,res,31))
                else: s.e((subu if k=='sub' else addu)(t,a,br),srl(t,t,31))
            elif k=='and': s.e(and_(t,a,br),srl(t,t,31))
            elif k=='xor': s.e(xor(t,a,br),srl(t,t,31))
        elif b==CF:
            if k=='sub': s.e(sltu(t,a,br),xori(t,t,1))
            elif k=='add':
                if res is None: r=s.tmp(); s.e(addu(r,a,br)); s.e(sltu(t,r,a))
                else: s.e(sltu(t,res,a))
            else: raise RuntimeError('C from %s'%k)
        elif b==VF:
            if k=='sub':
                x=s.tmp(); y=s.tmp()
                s.e(xor(x,a,br))
                if res is None: s.e(subu(y,a,br)); r=y
                else: r=res
                s.e(xor(y,a,r),and_(t,x,y),srl(t,t,31))
            elif k=='add':
                x=s.tmp(); y=s.tmp()
                if res is None: s.e(addu(y,a,br)); r=y
                else: r=res
                s.e(xor(x,a,r)); y2=s.tmp(); s.e(xor(y2,br,r),and_(t,x,y2),srl(t,t,31))
            else: raise RuntimeError('V from %s'%k)
        return t
    def cc_jump(s,cc,lab,neg=False):
        """emit: if cond(cc) (xor neg) goto lab, flags per current lazy state"""
        if cc==14:
            if not neg: s.A.br(beq(0,0),lab)
            return
        if neg: cc^=1
        need=bits(D.CONDUSE[cc])
        srcs=[s.fl.get(b) for b in need]
        br=s.A.br
        # all constants -> static
        if all(x is not None and x.kind=='k' for x in srcs):
            vals={b:srcs[k].a[b] for k,b in enumerate(need)}
            n,z,c,v=[vals.get(x,0) for x in (NF,ZF,CF,VF)]
            t=[z==1,z==0,c==1,c==0,n==1,n==0,v==1,v==0,(c==1 and z==0),(c==0 or z==1),n==v,n!=v,(z==0 and n==v),(z==1 or n!=v)][cc]
            if t: br(beq(0,0),lab)
            return
        S0=srcs[0] if srcs and all(x is srcs[0] for x in srcs) else None
        if S0 is not None and S0.kind in('sub','add','res','and'):
            a=S0.a; k=S0.kind; res=S0.res
            def bsrc(): return s.reg_of(S0.b)
            if k=='res' and cc in(0,1,4,5):
                r=S0.res
                br({0:beq(r,0),1:bne(r,0),4:bltz(r),5:bgez(r)}[cc],lab); return
            if k=='and' and cc in(0,1,4,5):
                t=s.tmp(); s.e(and_(t,a,bsrc()))
                br({0:beq(t,0),1:bne(t,0),4:bltz(t),5:bgez(t)}[cc],lab); return
            if k=='sub':
                b=S0.b
                if cc in(0,1):
                    if res is not None: br((beq if cc==0 else bne)(res,0),lab)
                    elif b[0]=='i' and b[1]==0: br((beq if cc==0 else bne)(a,0),lab)
                    else: br((beq if cc==0 else bne)(a,bsrc()),lab)
                    return
                if cc in(2,3,10,11):
                    un=cc in(2,3)
                    t=s.tmp()
                    sv=(b[1]-(1<<32) if b[1]>=1<<31 else b[1]) if b[0]=='i' else None
                    if sv is not None and -0x8000<=sv<=0x7fff: s.e((sltiu if un else slti)(t,a,sv&0xffff))
                    else: s.e((sltu if un else slt)(t,a,bsrc()))
                    br((bne if cc in(3,11) else beq)(t,0),lab); return
                if cc in(8,9,12,13):
                    un=cc in(8,9); t=s.tmp()
                    s.e((sltu if un else slt)(t,bsrc(),a))
                    br((bne if cc in(8,12) else beq)(t,0),lab); return
                if cc in(4,5):
                    if res is not None: br((bltz if cc==4 else bgez)(res),lab)
                    else:
                        t=s.tmp(); s.e(subu(t,a,bsrc())); br((bltz if cc==4 else bgez)(t),lab)
                    return
            if k=='add':
                if res is not None or cc in(0,1,4,5,2,3):
                    if res is None:
                        res=s.tmp(); s.e(addu(res,a,bsrc()))
                    if cc in(0,1): br((beq if cc==0 else bne)(res,0),lab); return
                    if cc in(4,5): br((bltz if cc==4 else bgez)(res),lab); return
                    if cc in(2,3):
                        t=s.tmp(); s.e(sltu(t,res,a)); br((bne if cc==2 else beq)(t,0),lab); return
        # general path: materialise needed bits in registers
        r={b:s.getbit(b) for b in need}
        if cc in(0,1): br((bne if cc==0 else beq)(r[ZF],0),lab)
        elif cc in(2,3): br((bne if cc==2 else beq)(r[CF],0),lab)
        elif cc in(4,5): br((bne if cc==4 else beq)(r[NF],0),lab)
        elif cc in(6,7): br((bne if cc==6 else beq)(r[VF],0),lab)
        elif cc in(8,9):
            t=s.tmp(); s.e(sltu(t,r[ZF],r[CF])); br((bne if cc==8 else beq)(t,0),lab)   # Z<C : C=1,Z=0
        elif cc in(10,11):
            t=s.tmp(); s.e(xor(t,r[NF],r[VF])); br((beq if cc==10 else bne)(t,0),lab)
        else:
            t=s.tmp(); s.e(xor(t,r[NF],r[VF]),or_(t,t,r[ZF])); br((beq if cc==12 else bne)(t,0),lab)
    # ---- operand 2
    def op2(s,i,hint=None):
        """returns operand descriptor for the shifter operand (emitting shift code into temps/hint) """
        if i.rm is None:
            return ('i',i.imm&0xffffffff)
        rm=i.rm
        if rm==15:
            v=s.pcv(i)+(4 if (i.shreg is not None and i.mode=='A') else 0)
            if i.sh==LSL and i.shreg is None and i.shamt==0: return ('i',v)
            if i.shreg is None and i.sh!=RRX:
                r,_=S.shift32(v,i.sh,i.shamt,0); return ('i',r)
            t=s.tmp(); s.li(t,v); rmm=t
        else: rmm=GM[rm]
        if i.shreg is None:
            n=i.shamt; sh=i.sh
            if sh==LSL and n==0: return ('r',rmm)
            d=hint if hint is not None else s.tmp()
            if sh==LSL: s.e(sll(d,rmm,n))
            elif sh==LSR:
                if n>=32: s.e(addu(d,0,0))
                else: s.e(srl(d,rmm,n))
            elif sh==ASR: s.e(sra(d,rmm,min(n,31)))
            elif sh==ROR:
                t=s.tmp(); s.e(srl(t,rmm,n),sll(d,rmm,32-n),or_(d,d,t))
            elif sh==RRX:
                c=s.getbit(CF); t=s.tmp(); s.e(srl(d,rmm,1),sll(t,c,31),or_(d,d,t))
            return ('r',d)
        # register-controlled shift
        rs=GM[i.shreg] if i.shreg!=15 else None
        if rs is None: rs=s.tmp(); s.li(rs,s.pcv(i)+4)
        d=hint if (hint is not None and hint!=rs and hint!=rmm) else s.tmp()
        t=s.tmp(); u=s.tmp()
        if i.sh in(LSL,LSR):
            s.e(andi(t,rs,0xff),sltiu(u,t,32),(sllv if i.sh==LSL else srlv)(d,rmm,t),subu(u,0,u),and_(d,d,u))
        elif i.sh==ASR:
            s.e(andi(t,rs,0xff),sltiu(u,t,32),addiu(u,u,-1),andi(u,u,31),or_(t,t,u),srav(d,rmm,t))
        else:
            s.e(andi(t,rs,31),subu(u,0,t),sllv(u,rmm,u),srlv(d,rmm,t),or_(d,d,u))
        return ('r',d)
    def shifter_carry(s,i,dst=FC):
        pool=list(s.tp)
        try: s._shifter_carry(i,dst)
        finally: s.tp=pool
    def _shifter_carry(s,i,dst=FC):
        """emit code computing the shifter carry-out of op2 into dst (only when it is defined: caller checks)"""
        if i.rm is None:
            s.e(*M.li(dst,(i.imm>>31)&1)); return
        rmm=GM[i.rm] if i.rm!=15 else None
        if rmm is None: rmm=s.tmp(); s.li(rmm,s.pcv(i))
        if i.shreg is None:
            n=i.shamt; sh=i.sh
            if sh==LSL:
                if n==0: return
                s.e(srl(dst,rmm,32-n),andi(dst,dst,1))
            elif sh in(LSR,ASR):
                nn=min(n,32)
                if nn==32: s.e(srl(dst,rmm,31))
                else: s.e(srl(dst,rmm,nn-1),andi(dst,dst,1))
            elif sh==ROR: s.e(srl(dst,rmm,n-1),andi(dst,dst,1))
            elif sh==RRX: s.e(andi(dst,rmm,1))
            return
        # register-controlled: carry unchanged when amount==0
        rs=GM[i.shreg]
        old=s.getbit(CF)
        if old!=dst: s.e(addu(dst,old,0))
        t=s.tmp(); u=s.tmp()
        done=s.newlab()
        s.e(andi(t,rs,0xff)); s.A.br(beq(t,0),done)
        if i.sh==LSL:
            nrm=s.newlab(); z=s.newlab()
            s.e(sltiu(u,t,32)); s.A.br(bne(u,0),nrm)
            s.e(xori(u,t,32)); s.A.br(bne(u,0),z)
            s.e(andi(dst,rmm,1)); s.A.br(beq(0,0),done)
            s.A.label(z); s.e(addu(dst,0,0)); s.A.br(beq(0,0),done)
            s.A.label(nrm); s.e(subu(u,0,t),srlv(u,rmm,u),andi(dst,u,1))
        elif i.sh==LSR:
            nrm=s.newlab(); z=s.newlab()
            s.e(sltiu(u,t,32)); s.A.br(bne(u,0),nrm)
            s.e(xori(u,t,32)); s.A.br(bne(u,0),z)
            s.e(srl(dst,rmm,31)); s.A.br(beq(0,0),done)
            s.A.label(z); s.e(addu(dst,0,0)); s.A.br(beq(0,0),done)
            s.A.label(nrm); s.e(addiu(u,t,-1),srlv(u,rmm,u),andi(dst,u,1))
        elif i.sh==ASR:
            nrm=s.newlab()
            s.e(sltiu(u,t,32)); s.A.br(bne(u,0),nrm)
            s.e(srl(dst,rmm,31)); s.A.br(beq(0,0),done)
            s.A.label(nrm); s.e(addiu(u,t,-1),srlv(u,rmm,u),andi(dst,u,1))
        else:
            s.e(andi(t,t,31)); 
            nz=s.newlab()
            s.A.br(bne(t,0),nz); s.e(srl(dst,rmm,31)); s.A.br(beq(0,0),done)
            s.A.label(nz); s.e(addiu(u,t,-1),srlv(u,rmm,u),andi(dst,u,1))
        s.A.label(done)
    def fn_of(s,a):
        j=bisect.bisect_right(s.funcs,a)-1
        if j<0: return None
        f=s.funcs[j]; return s.grp.get(f,f)
    def iscold(s,a): return bool(s.cold) and s.fn_of(a) in s.cold
    def xlab(s,tgt):
        """label for a direct branch/call target: direct when it is translated in the hot blob or in the same function; else RT_MISS (overlay loader) with $25 = guest target"""
        if tgt in s.ins and not (s.iscold(tgt) and s.fn_of(tgt)!=s.fn_of(s.cur.addr)): return ('g',tgt),False
        return 'RT_MISS',True
    def newlab(s):
        s.nl+=1; return ('l',s.nl)
    # ---- ALU
    def alu_emit(s,opc,dst,a,bo,cin=None):
        """emit dst = a OP bo (a: mreg; bo operand); for compares dst is a scratch"""
        if opc in(AND,TST):
            if bo[0]=='i' and bo[1]<=0xffff: s.e(andi(dst,a,bo[1]))
            else: s.e(and_(dst,a,s.reg_of(bo)))
        elif opc in(EOR,TEQ):
            if bo[0]=='i' and bo[1]<=0xffff: s.e(xori(dst,a,bo[1]))
            else: s.e(xor(dst,a,s.reg_of(bo)))
        elif opc==ORR:
            if bo[0]=='i' and bo[1]<=0xffff: s.e(ori(dst,a,bo[1]))
            else: s.e(or_(dst,a,s.reg_of(bo)))
        elif opc==BIC:
            if bo[0]=='i':
                m=(~bo[1])&0xffffffff
                if m<=0xffff: s.e(andi(dst,a,m))
                else: t=s.tmp(); s.li(t,m,guest=False); s.e(and_(dst,a,t))
            else: t=s.tmp(); s.e(nor(t,bo[1],0),and_(dst,a,t))
        elif opc in(ADD,CMN):
            if bo[0]=='i': s.addimm(dst,a,bo[1])
            else: s.e(addu(dst,a,bo[1]))
        elif opc in(SUB,CMP):
            if bo[0]=='i': s.addimm(dst,a,-bo[1])
            else: s.e(subu(dst,a,bo[1]))
        elif opc==RSB:
            if bo[0]=='i':
                if bo[1]==0: s.e(subu(dst,0,a))
                else: t=s.tmp(); s.li(t,bo[1],guest=False); s.e(subu(dst,t,a))
            else: s.e(subu(dst,bo[1],a))
        elif opc==ADC:
            t=s.tmp(); b=s.reg_of(bo); s.e(addu(t,a,b),addu(dst,t,cin))
        elif opc==SBC:
            t=s.tmp(); b=s.reg_of(bo); s.e(subu(t,a,b),addu(t,t,cin),addiu(dst,t,-1))
        elif opc==RSC:
            t=s.tmp(); b=s.reg_of(bo); s.e(subu(t,b,a),addu(t,t,cin),addiu(dst,t,-1))
        elif opc==MOV:
            if bo[0]=='i': s.li(dst,bo[1],guest=False)
            elif bo[1]!=dst: s.e(addu(dst,bo[1],0))
        elif opc==MVN:
            if bo[0]=='i': s.li(dst,(~bo[1])&0xffffffff,guest=False)
            else: s.e(nor(dst,bo[1],0))
    def emit_expl(s,m,kind,a,bo,res,cin=None):
        pool=list(s.tp)
        try: s._emit_expl(m,kind,a,bo,res,cin)
        finally: s.tp=pool
    def _emit_expl(s,m,kind,a,bo,res,cin=None):
        """materialise flag bits m (mask) into $4-$7. kind: 'sub','add','adc','sbc','res'. a is mreg, bo operand, res mreg of result"""
        for b in bits(m): s.fl.pop(b,None)
        if m&NF: s.e(srl(FN,res,31))
        if m&ZF: s.e(sltiu(FZ,res,1))
        if m&(CF|VF) and kind!='res':
            b=s.reg_of(bo); x=s.tmp(); y=s.tmp()
            if kind=='sub':
                if m&CF: s.e(sltu(x,a,b),xori(FC,x,1))
                if m&VF: s.e(xor(x,a,b),xor(y,a,res),and_(x,x,y),srl(FV,x,31))
            elif kind=='add':
                if m&CF: s.e(sltu(FC,res,a))
                if m&VF: s.e(xor(x,a,res),xor(y,b,res),and_(x,x,y),srl(FV,x,31))
            elif kind in('adc','sbc'):
                if m&CF: s.e(sltu(x,res,a),xor(y,res,a),sltiu(y,y,1),and_(y,y,cin),or_(FC,x,y))
                if m&VF:
                    if kind=='adc': s.e(xor(x,a,res),xor(y,b,res),and_(x,x,y),srl(FV,x,31))
                    else: s.e(xor(x,a,b),xor(y,a,res),and_(x,x,y),srl(FV,x,31))
    def e_dp(s,i):
        opc=i.opc; cmpop=opc in(TST,TEQ,CMP,CMN)
        u,defm=D.flag_use_def(i)
        kidx=s.idx[i.addr]
        live=(defm&s.lout[kidx]) if i.s else 0
        expl=s.expl.get(i.addr,0) if i.s else 0
        rd=i.rd
        if rd==15 and not cmpop:
            # computed jump: compute value into temp and jump
            t=s.tmp(); s.dp_core(i,t,live,expl,defm); s.dynjump(t,i); return
        if not cmpop and rd==14:
            # lr := constant code address -> host label (return address trick)
            kv=s.kfold(i,s.k) if i.cond==14 else None
            if kv is not None and (kv[0]&~1) in s.ins and not i.s and s.xlab(kv[0]&~1)[1]==False:
                s.A.la(31,('g',kv[0]&~1)); s.st['lr_la']+=1; return
        if (not cmpop and rd!=15 and i.rn==15 and i.rm is None and i.imm is not None and not i.s and opc in(ADD,SUB)):
            # adr-style  rd = pc +/- imm  (also conditionally executed): a known address constant -> map like a literal
            pcv=s.pcv(i)&~3 if i.mode=='T' else s.pcv(i)
            s.li(GM[rd],(pcv+(i.imm if opc==ADD else -i.imm))&0xffffffff); s.st['adr']+=1; return
        s.dp_core(i,None if cmpop else GM[rd],live,expl,defm)
    def dp_core(s,i,dst,live,expl,defm):
        opc=i.opc; cmpop=opc in(TST,TEQ,CMP,CMN)
        # constant folding
        if i.cond==14:
            kf=None
            if i.rm is None or True:
                kf=s.fold_full(i)
            if kf is not None:
                res,N,Z,C,V=kf
                if not cmpop: s.li(dst,res) 
                vals={NF:N,ZF:Z,CF:C,VF:V}
                for b in bits(live):
                    if vals[b] is None: continue
                    if b&expl: s.e(*M.li(FREG[b],vals[b])); s.fl.pop(b,None)
                    else: s.fl[b]=Src('k',a=vals)
                s.st['folded']+=1
                return
        arith=opc in ARITH
        need_c=opc in(ADC,SBC,RSC)
        # carry-in
        cin=None
        if need_c:
            cin=s.getbit(CF)
        a=None
        if opc not in(MOV,MVN):
            ao=s.aopd(i,i.rn,s.k)
            a=s.reg_of(ao)
        # shifter carry for logical S ops (always explicit if live)
        shc_def = (not arith) and i.s and (live&CF)
        hint=dst if (opc==MOV and dst is not None and not shc_def) else None
        bo=s.op2(i,hint)
        if shc_def:
            s.shifter_carry(i)    # writes FC after op2 consumed the old carry, before the result is written
            s.fl.pop(CF,None)
        # destination register for the result
        exm=expl&(CF|VF) if arith else 0
        res=dst
        if cmpop:
            if live&(NF|ZF|CF|VF) and expl:
                res=s.tmp()
            else: res=None
        elif exm and (dst in (a, bo[1] if bo[0]=='r' else -1)) :
            res=s.tmp()
        if res is not None:
            s.alu_emit(opc,res,a,bo,cin)
        elif opc in(TST,TEQ,CMP,CMN) and False: pass
        # flags
        if i.s and live:
            # explicit
            if expl:
                if arith:
                    kind={SUB:'sub',CMP:'sub',ADD:'add',CMN:'add',ADC:'adc',SBC:'sbc',RSB:'sub',RSC:'sbc'}[opc]
                    aa,bb=(a,bo) if opc not in(RSB,RSC) else (s.reg_of(bo),('r',a))
                    s.emit_expl(expl&(NF|ZF|CF|VF),kind,aa,bb,res,cin)
                else:
                    s.emit_expl(expl&(NF|ZF),'res',None,None,res)
            lazy=live&~expl
            if lazy:
                if opc in(SUB,CMP,ADD,CMN,RSB) :
                    cap=s.lazy_cap(i)
                    kind='sub' if opc in(SUB,CMP,RSB) else 'add'
                    if opc==RSB:
                        aa=0 if (bo[0]=='i') else bo[1]; bb=('r',a)
                    else: aa=a; bb=bo
                    full=Src(kind,aa,bb,res=dst if not cmpop else None)
                    for b in bits(lazy):
                        if b in(NF,ZF) and cap.get(CF) is None and not cmpop: s.fl[b]=Src('res',res=dst)
                        else: s.fl[b]=full
                elif opc==TST: 
                    for b in bits(lazy): s.fl[b]=Src('and',a=a,b=bo)
                else:
                    for b in bits(lazy): s.fl[b]=Src('res',res=dst)
        if res is not None and dst is not None and res!=dst and not cmpop:
            s.e(addu(dst,res,0))
        # unsafe patterns
        if opc==MOV and i.rm is not None and i.sh==LSR and i.shreg is None and i.shamt>=24: s.unsafe['lsr>=24 (region extract?)']+=1
        if opc==AND and i.rm is None and i.imm is not None and i.imm>=0xff000000: s.unsafe['and hi-byte mask']+=1
    def fold_full(s,i):
        """all-inputs-known evaluation incl. flags; returns (res,N,Z,C,V) with None for undefined, or None"""
        k=s.k; opc=i.opc
        if opc in(ADC,SBC,RSC): return None
        a=0
        if opc not in(MOV,MVN):
            a=s.kget(i,i.rn,k)
            if a is None: return None
        shc=None
        if i.rm is None:
            b=i.imm&0xffffffff
            if i.mode=='A' and i.shamt: shc=b>>31
        else:
            v=s.kget(i,i.rm,k)
            if v is None or i.sh==RRX: return None
            if i.shreg is not None:
                sv=s.kget(i,i.shreg,k)
                if sv is None: return None
                amt=sv&0xff
                b,sc=S.shift32(v,i.sh,amt,0)
                shc=sc if amt else None
            else:
                if i.sh==LSL and i.shamt==0: b=v
                else:
                    b,shc=S.shift32(v,i.sh,i.shamt,0)
        r,N,Z,C,V=S.alu(opc,a,b,0)
        if C is None: C=shc
        return (r,N,Z,C,V)
    # ---- jumps
    def dynjump(s,reg,i,direct=False):
        if reg==31: s.e(jr(31),0); return
        if direct: s.e(jr(reg),0); return
        if reg!=25: s.e(addu(25,reg,0))
        s.A.j('RT_BX')
    # ---- memory
    def e_mem(s,i):
        s.tp=[r for r in s.tp if r!=24]
        sz=i.sz; ld=i.ld; rd=i.rd; rn=i.rn
        if rn==15 and i.imm is not None and ld:
            pc=s.pcv(i)&~3 if i.mode=='T' else s.pcv(i)
            ea=(pc+(i.imm if i.up else -i.imm)) if i.pre else pc
            if sz==4: v=s.img.rd32(ea&~3)
            elif sz==2: v=s.img.rd16(ea&~1)
            else: v=(s.img.rd32(ea&~3)>>(8*(ea&3)))&0xff
            if v is None: raise RuntimeError('literal unreadable %x'%ea)
            if sz==2 and i.sg: v=v-65536 if v&0x8000 else v
            if sz==1 and i.sg: v=v-256 if v&0x80 else v
            v&=0xffffffff
            if (ea&~3) in s.vol and sz==4:
                tb=s.tmp(); s.tpl_addr(tb,i,ea&~3); s.e(lw(GM[rd],tb,0)); s.st['lit_volatile']+=1; return
            s.st['lit']+=1
            if rd==15:
                t=s.tmp(); s.li(t,v); s.dynjump(t,i); return
            if rd==14 and sz==4 and (v&~1) in s.ins and s.xlab(v&~1)[1]==False:
                s.A.la(31,('g',v&~1)); s.st['lr_la']+=1; return
            s.li(GM[rd],v); return
        # base / address
        if rn==15:
            b=s.tmp(); s.tpl_addr(b,i,s.pcv(i)); 
        else: b=GM[rn]
        sgn=1 if i.up else -1
        wbk=(i.wb or not i.pre)
        if rd==15 and ld: dst=s.tmp()
        elif rd==15: dst=s.tmp(); s.li(dst,s.pcv(i)+4)
        else: dst=GM[rd]
        kb=s.k.get(rn); early_wb=False
        if i.rm is None:
            off=sgn*i.imm
            if i.pre:
                if -32768<=off<=32767: ab,ao=b,off
                else:
                    t=s.tmp(); s.addimm(t,b,off); ab,ao=t,0
                after=(lambda: s.addimm(b,b,off)) if i.wb else None
            else:
                ab,ao=b,0
                after=lambda: s.addimm(b,b,off)
        else:
            ix=s.op2_index(i)
            t=s.tmp()
            s.e((addu if i.up else subu)(t,b,ix))
            if i.pre:
                ab,ao=t,0
                after=(lambda: s.e(addu(b,t,0))) if i.wb else None
            else:
                ab,ao=b,0
                after=lambda: s.e(addu(b,t,0))
            # stage 4 fix: on the slow path the helper call clobbers the temp t ($v0 = loaded value, and the index register may be rd), so the base writeback of a
            # register-offset access is done right after the effective address has been copied to $24, before the helper call (not for a store whose rd is the base)
            early_wb=(after is not None) and not (rd==rn and not ld) and not (ld and rd==rn)
        # classification stats
        if rn==13: s.st['mem_sp']+=1
        elif kb is not None and s.cfg.host(kb) is not None: s.st['mem_known_region']+=1; s.st['io_site']+= 1 if 0x04000000<=kb<0x05000000 else 0
        elif kb is not None and kb>>24>=8: s.st['mem_rom_const']+=1
        else: s.st['mem_dyn']+=1
        cls='direct'
        if s.cfg.mode=='P' and rn!=13:
            if kb is not None:
                h=s.cfg.host(kb)
                if h is None or 0x04000000<=kb<0x05000000: cls='slow'
            elif rn==15: cls='direct'
            else: cls='guard'
        if cls!='direct':
            s.st['mem_'+cls]+=1
            s.nl+=1; sl=('slow',s.nl); dn=('done',s.nl)
            if ld: kind={(1,0):0,(1,1):1,(2,0):2,(2,1):3,(4,0):4}[(sz,i.sg)]
            else: kind=sz
            # effective address -> $24
            if ao==0: s.e(addu(24,ab,0))
            else: s.e(addiu(24,ab,ao))
            if early_wb: s.e(addu(b,t,0)); after=None       # (fast path continues with the access through $24; base already updated)
            if cls=='guard':
                s.e(srl(1,24,19),xori(1,1,Cfg.PLAIN[0]>>19)); s.A.br(bne(1,0),sl)
            else: s.A.j(sl)
            ab,ao=24,0
            s.slow.append((sl,dn,ld,dst,kind))
        if ld:
            op={(4,0):lw,(2,0):lhu,(2,1):lh,(1,0):lbu,(1,1):lb}[(sz,i.sg)]
            s.e(op(dst,ab,ao))
        else:
            op={4:sw,2:sh,1:sb}[sz]
            s.e(op(dst,ab,ao))
        if cls!='direct': s.A.label(dn)
        if after is not None and not (ld and rd==rn): after()
        if rd==15 and ld: s.dynjump(dst,i)
    def tpl_addr(s,reg,i,ea):
        """address `ea` (guest, pc-relative) as seen by instruction i; inside a RAM-code template it is relative to the RAM copy"""
        for ti,(tsrc,tn,tcp) in enumerate(disc.TEMPLATES):
            if tsrc<=i.addr<tsrc+tn:
                s.A.la(reg,'ALIAS%d'%ti); s.e(lw(reg,reg,0)); s.addimm(reg,reg,ea-tsrc); return
        s.li(reg,ea)
    def op2_index(s,i):
        """register offset of a mem op -> mreg (shifted)"""
        class X: pass
        x=X(); x.rm=i.rm; x.shreg=None; x.sh=i.sh; x.shamt=i.shamt; x.mode=i.mode; x.addr=i.addr; x.imm=None
        x.cond=14
        r=s.op2(x)
        return s.reg_of(r)
    def e_swp(s,i):
        t=s.tmp(); b=GM[i.rn]; m=GM[i.rm]
        if i.sz==4: s.e(lw(t,b,0),sw(m,b,0))
        else: s.e(lbu(t,b,0),sb(m,b,0))
        s.e(addu(GM[i.rd],t,0))
    def e_ldm(s,i):
        regs=[r for r in range(16) if i.regs>>r&1]; n=len(regs)
        rn=i.rn; b=GM[rn]
        if n==0: return
        if i.up: off0=4 if i.pre else 0
        else: off0=-4*n if i.pre else -4*n+4
        delta=4*n if i.up else -4*n
        wb=i.wb
        if s.cfg.mode=='P' and rn!=13 and 15 not in regs:
            s.st['ldm_guard']+=1
            s.nl+=1; sl=('slowm',s.nl); dn=('donem',s.nl)
            s.e(srl(1,b,19),xori(1,1,Cfg.PLAIN[0]>>19)); s.A.br(bne(1,0),sl)
            def stub(regs=regs,b=b,off0=off0,delta=delta,wb=wb,ld=i.ld,rn=rn,dn=dn):
                seq=[r for r in regs if r!=rn]+([rn] if rn in regs else []) if ld else list(regs)
                for k,r in enumerate(regs):
                    pass
                for r in seq:
                    k=regs.index(r); off=off0+4*k
                    if -32768<=off<=32767: s.e(addiu(24,b,off))
                    else: s.e(*M.li(24,off&0xffffffff)); s.e(addu(24,24,b))
                    s.nl+=1; rl=('retm',s.nl)
                    if ld: s.e(*M.li(2,4)); s.A.la(28,rl); s.A.j('RT_MEMRD'); s.A.label(rl); s.e(addu(GM[r],2,0))
                    else:
                        if r==rn and wb and regs.index(r)>0:
                            s.e(*M.li(3,delta&0xffffffff)); s.e(addu(3,3,b))
                        else: s.e(addu(3,GM[r],0))
                        s.e(*M.li(2,4)); s.A.la(28,rl); s.A.j('RT_MEMWR'); s.A.label(rl)
                if wb and not (ld and rn in regs):
                    t=delta
                    if -32768<=t<=32767: s.e(addiu(b,b,t))
                    else: s.e(*M.li(24,t&0xffffffff)); s.e(addu(b,b,24))
                s.A.j(dn)
            s.slow.append(('fn',sl,stub))
            fast_dn=dn
        else: fast_dn=None
        s.pend_dn=fast_dn
        if i.ld:
            if rn in regs: wb=False
            order=[r for r in regs if r!=rn and r!=15]
            for k,r in enumerate(regs):
                if r in(rn,15): continue
                s.e(lw(GM[r],b,off0+4*k))
            if rn in regs: s.e(lw(b if False else GM[rn],b,off0+4*regs.index(rn)))
            if 15 in regs:
                k=regs.index(15); s.e(lw(25,b,off0+4*k))
            if wb: s.addimm(b,b,delta)
            if 15 in regs:
                s.st['ret_ldm']+=1; s.dynjump(25,i,direct=True)
        else:
            newb=None
            for k,r in enumerate(regs):
                if r==15:
                    t=s.tmp(); s.li(t,s.pcv(i)+4); s.e(sw(t,b,off0+4*k))
                elif r==rn and wb and k>0:
                    t=s.tmp(); s.addimm(t,b,delta); s.e(sw(t,b,off0+4*k))
                else: s.e(sw(GM[r],b,off0+4*k))
            if wb: s.addimm(b,b,delta)
    def e_mul(s,i):
        rm=GM[i.rm]; rs=GM[i.rs]; rd=GM[i.rd]
        live=0
        if i.s:
            live=s.lout[s.idx[i.addr]]&(NF|ZF)
        if i.rn is not None:
            t=s.tmp(); s.e(mult(rm,rs),mflo(t),addu(rd,t,GM[i.rn]))
        else: s.e(mult(rm,rs),mflo(rd))
        if live:
            if s.expl.get(i.addr,0): s.emit_expl(s.expl[i.addr]&(NF|ZF),'res',None,None,rd)
            for b in bits(live&~s.expl.get(i.addr,0)): s.fl[b]=Src('res',res=rd)
    def e_mull(s,i):
        rm=GM[i.rm]; rs=GM[i.rs]; lo=GM[i.rd]; hi=GM[i.rdhi]
        s.e((multu if i.uns else mult)(rm,rs))
        if i.acc:
            tl=s.tmp(); th=s.tmp(); sm=s.tmp(); c=s.tmp()
            s.e(mflo(tl),mfhi(th),addu(sm,tl,lo),sltu(c,sm,tl),addu(th,th,hi),addu(hi,th,c),addu(lo,sm,0))
        else: s.e(mflo(lo),mfhi(hi))
        if i.s and (s.lout[s.idx[i.addr]]&(NF|ZF)):
            t=s.tmp(); s.e(srl(FN,hi,31),or_(t,hi,lo),sltiu(FZ,t,1))
    # ---- everything
    def emit(s,i):
        op=i.op
        if op=='dp': s.e_dp(i)
        elif op=='mem': s.e_mem(i)
        elif op=='ldm':
            s.pend_dn=None; s.e_ldm(i)
            if s.pend_dn: s.A.label(s.pend_dn); s.pend_dn=None
        elif op=='mul': s.e_mul(i)
        elif op=='mull': s.e_mull(i)
        elif op=='swp': s.e_swp(i)
        elif op=='b':
            lab,ms=s.xlab(i.target)
            if ms: s.miss_t.add(i.target)
            if i.cond==14:
                if ms: s.e(*M.li(25,i.target))
                s.A.j(lab); s.st['jump']+=1
            else:
                if ms:
                    sl=s.newlab(); tg=i.target
                    s.cc_jump(i.cond,sl); s.slow.append(('fn',sl,lambda tg=tg:(s.e(*M.li(25,tg)),s.A.j('RT_MISS'))))
                else: s.cc_jump(i.cond,lab)
                s.st['cbranch']+=1
        elif op=='bl':
            lab,ms=s.xlab(i.target)
            if ms: s.miss_t.add(i.target); s.e(*M.li(25,i.target))
            s.A.jal(lab); s.st['call']+=1
        elif op=='bx':
            if i.rm==15 and i.target in s.ins:       # Thumb "bx pc" veneer into ARM code: the target is the next instruction (stage 4: also when it is another (cold) function: RT_MISS, as for a call)
                lab,ms=s.xlab(i.target); s.st['bx_pc']+=1
                if ms: s.miss_t.add(i.target); s.e(*M.li(25,i.target)); s.A.j('RT_MISS')
                else: s.A.j(lab)
                return
            s.dynjump(GM[i.rm] if i.rm!=15 else 25,i); s.st['bx_'+('lr' if i.rm==14 else 'reg')]+=1
        elif op=='stub':
            s.e(*M.li(25,i.imm)); s.A.j('RT_STUB'); s.st['stub']+=1
        elif op=='swi':
            n_=i.imm if i.mode=='T' else (i.imm>>16)&0xff if i.imm and i.imm>0xff else i.imm
            if n_==5 and 0x100 in s.ins:
                # VBlankIntrWait: call the shared ARM stub at guest 0x100 with r12 = host return address (lr preserved)
                s.nl+=1; lab=('l',s.nl); s.nl+=1; l2=('l',s.nl); s.A.la(28,l2); s.A.j('RT_VBL'); s.A.label(l2); s.A.la(15,lab); s.A.j(('g',0x100)); s.A.label(lab); s.st['swi5']+=1
            else:
                s.e(*M.li(25,i.imm)); s.A.jal('RT_SWI'); s.st['swi']+=1
        elif op=='mrs':
            rd=26 if i.rd is None else GM[i.rd]; s.e(*M.li(rd,0x1f))
            if not i.psr:
                for b,sh_ in((NF,31),(ZF,30),(CF,29),(VF,28)):
                    pool=list(s.tp); r=s.getbit(b); t=s.tmp(); s.e(sll(t,r,sh_),or_(rd,rd,t)); s.tp=pool
        elif op=='msr':
            if not i.psr and (i.regs&8):
                if i.rm is not None: v=GM[i.rm]
                else: v=s.tmp(); s.li(v,i.imm,guest=False)
                s.e(srl(FN,v,31),srl(FZ,v,30),andi(FZ,FZ,1),srl(FC,v,29),andi(FC,FC,1),srl(FV,v,28),andi(FV,FV,1)); s.fl.clear()
        else: raise RuntimeError('cannot translate %s'%i)
    def run(s):
        s.analyse(); s.decide()
        order=s.order; ins=s.ins; A=s.A
        s.nl=0; s.fl={}; s.k={}; s.slow=[]
        s.runtime()
        t0=time.time()
        s.words_by_op=collections.Counter(); s.insn_by_op=collections.Counter()
        hot=[a for a in order if not s.iscold(a)]; cold=[a for a in order if s.iscold(a)]
        rk=getattr(s,'cold_rank',None)
        if rk: cold.sort(key=lambda a: rk.get(s.grp.get(s.fn_of(a),s.fn_of(a)),9))     # stage 4: groups of the demo scenario first (stable: address order inside a rank)
        if rk and os.environ.get('COLD_ONLY'): cold=[a for a in cold if rk.get(s.grp.get(s.fn_of(a),s.fn_of(a)),9)<=int(os.environ.get('COLD_MAXRANK','0'))]      # PS1 demo disc: emit only the scenario's groups (the translation of everything else is decided as in the full build, so the code is identical)
        def flush():
            for ent in s.slow:
                if ent[0]=='fn':
                    A.label(ent[1]); ent[2](); continue
                sl,dn,ld,dst,kind=ent
                A.label(sl)
                s.nl+=1; rl=('ret',s.nl)
                if ld:
                    A.e(*M.li(2,kind)); A.la(28,rl); A.j('RT_MEMRD'); A.label(rl); A.e(addu(dst,2,0)); A.j(dn)
                else:
                    A.e(addu(3,dst,0)); A.e(*M.li(2,kind)); A.la(28,rl); A.j('RT_MEMWR'); A.label(rl); A.j(dn)
            s.slow=[]
        def group(addrs,perfn):
            prev=None
            for n_,a in enumerate(addrs):
                i=ins[a]; s.cur=i
                if perfn and prev is not None and s.fn_of(a)!=s.fn_of(prev.addr):
                    flush(); A.label(('fend',s.fn_of(prev.addr)))
                if perfn and (prev is None or s.fn_of(a)!=s.fn_of(prev.addr)): A.label(('gap',s.fn_of(a)))
                A.label(('g',a))
                for ti,(tsrc,tn,tcp) in enumerate(disc.TEMPLATES):
                    if a==tcp:     # copy routine: remember where a RAM-code template was copied to
                        s.e(*M.li(1,tsrc)); skip=s.newlab(); A.brnd(bne(16,1),skip); A.e(0)
                        A.la(2,'ALIAS%d'%ti); A.e(sw(17,2,0)); A.label(skip)
                if a in s.leader or prev is None or prev.addr+prev.size!=a or not falls(prev):
                    s.k=dict(s.kin.get(a,{})); s.fl={}
                s.tp=list(TEMPS)
                n0=len(A.it)
                if i.cond!=14 and i.op not in('b',):
                    skip=s.newlab()
                    s.cc_jump(i.cond,skip,neg=True)
                    s.emit(i)
                    A.label(skip)
                    s.st['cond_exec']+=1
                else:
                    s.emit(i)
                s.kstep(i,s.k)
                prev=i
                s.words_by_op[i.op]+=len(A.it)-n0; s.insn_by_op[i.op]+=1
            if perfn and prev is not None: flush(); A.label(('fend',s.fn_of(prev.addr)))
        group(hot,False); flush()
        A.label('END')
        s.emit_hash()
        A.label('COLD_START')
        group(cold,True); flush()
        A.label('COLD_END')
        if s.verbose: print('  emitted %d items %.1fs'%(len(A.it),time.time()-t0))
    def emit_hash(s):
        A=s.A
        for ti in range(len(disc.TEMPLATES)): A.label('ALIAS%d'%ti); A.it.append(0)
        A.label('HASH')
        A.it.extend([0]*(2*(s.nslots+64)))
        A.label('HEND')
    # ---- runtime
    def runtime(s):
        A=s.A
        ne=len([a for a in s.ent if a in s.ins and not s.iscold(a)]); s.nslots=1
        while s.nslots<2*ne: s.nslots*=2
        A.label('RT_START')
        A.label('RT_SWI'); A.e(jr(31),0)
        A.label('RT_MISS')
        A.e(addu(24,25,0)); A.e(*M.li(25,s.cfg.HELP+8)); A.e(lw(25,25,0)); A.la(28,'rt_miss_ret'); A.j('RT_CC')
        A.label('rt_miss_ret'); A.e(jr(2),0)      # h_miss returned the host entry of the (now loaded) overlay function: tail-jump, $31 intact
        A.label('RT_VBL'); A.e(*M.li(25,s.cfg.HELP+12)); A.e(lw(25,25,0)); A.j('RT_CC')
        # RT_MEMRD: $24 = EA, $2 = kind (0 u8,1 s8,2 u16,3 s16,4 u32), $28 = link, result $2.  Fast path: ROM window (0x08/0x0a/0x0c) with a resident page.
        A.label('RT_MEMRD'); A.j('RT_MEMRD_SLOW')   # fast ROM path disabled: unvalidated on PS1
        A.e(srl(25,24,24),andi(1,25,0xf9),xori(1,1,8)); A.brnd(bne(1,0),'RT_MEMRD_SLOW'); A.e(0)
        A.e(sltiu(1,25,14)); A.brnd(beq(1,0),'RT_MEMRD_SLOW'); A.e(0)
        A.e(srl(1,24,12),andi(1,1,s.cfg.ROMPG_N-1),sll(1,1,2)); A.e(*M.li(25,s.cfg.ROMPG)); A.e(addu(1,1,25),lw(25,1,0))
        A.brnd(beq(25,0),'RT_MEMRD_SLOW'); A.e(0)
        A.e(andi(1,24,0xfff),addu(25,25,1))
        A.e(addiu(1,2,-4)); A.brnd(beq(1,0),'rt_mr_w'); A.e(0)
        A.e(addiu(1,2,-2)); A.brnd(beq(1,0),'rt_mr_hu'); A.e(0)
        A.e(addiu(1,2,-3)); A.brnd(beq(1,0),'rt_mr_h'); A.e(0)
        A.brnd(beq(2,0),'rt_mr_bu'); A.e(0)
        A.e(lb(2,25,0),jr(28),0)
        A.label('rt_mr_bu'); A.e(lbu(2,25,0),jr(28),0)
        A.label('rt_mr_w'); A.e(andi(1,24,3)); A.brnd(bne(1,0),'RT_MEMRD_SLOW'); A.e(0); A.e(lw(2,25,0),jr(28),0)
        A.label('rt_mr_hu'); A.e(andi(1,24,1)); A.brnd(bne(1,0),'RT_MEMRD_SLOW'); A.e(0); A.e(lhu(2,25,0),jr(28),0)
        A.label('rt_mr_h'); A.e(andi(1,24,1)); A.brnd(bne(1,0),'RT_MEMRD_SLOW'); A.e(0); A.e(lh(2,25,0),jr(28),0)
        A.label('RT_MEMRD_SLOW'); A.e(*M.li(25,s.cfg.HELP)); A.e(lw(25,25,0)); A.j('RT_CC')
        A.label('RT_MEMWR'); A.e(*M.li(25,s.cfg.HELP+4)); A.e(lw(25,25,0)); A.j('RT_CC')
        # RT_CC: call a C helper from translated code. $25 = C function, $24,$2,$3 = a0,a1,a2, $28 = link. Saves caller-saved guest regs
        # (flags $4-$7, r8-r12 $11-$15, lr $31) on a private stack; r0-r7 and sp are callee-saved in the C ABI. Result in $2.
        A.label('RT_CC')
        A.e(*M.li(29,0x801fff90))
        A.e(sw(4,29,16),sw(5,29,20),sw(6,29,24),sw(7,29,28),sw(11,29,32),sw(12,29,36),sw(13,29,40),sw(14,29,44),sw(15,29,48),sw(28,29,52),sw(31,29,56))
        A.e(addu(4,24,0),addu(5,2,0),addu(6,3,0),jalr(25),0)
        A.e(lw(4,29,16),lw(5,29,20),lw(6,29,24),lw(7,29,28),lw(11,29,32),lw(12,29,36),lw(13,29,40),lw(14,29,44),lw(15,29,48),lw(28,29,52),lw(31,29,56))
        A.e(jr(28),0)
        # RT_STUB: pruned function. $25 = stub id. Appends (id,r0..r3) to the draw-list ring at Cfg.DL, returns r0=0.
        A.label('RT_STUB')
        A.e(*M.li(1,s.cfg.DL)); A.e(lw(2,1,0)); A.e(sll(3,2,5),andi(3,3,0x1fe0),addu(3,3,1))
        A.e(sw(25,3,0x20),sw(16,3,0x24),sw(17,3,0x28),sw(18,3,0x2c),sw(19,3,0x30))
        A.e(addiu(2,2,1),sw(2,1,0),addu(16,0,0))
        A.e(addiu(2,25,-1)); A.brnd(bne(2,0),'rt_stub_ret'); A.e(0)
        # id 1 = present: toggle DISPCNT frame-select, then VBlankIntrWait through the shared stub (r12 = return address)
        ioh=s.cfg.host(0x04000000)
        A.e(*M.li(24,ioh)); A.e(*M.li(2,2)); A.la(28,'rt_st_r1'); A.j('RT_MEMRD'); A.label('rt_st_r1')
        A.e(xori(3,2,0x10)); A.e(*M.li(24,ioh)); A.e(*M.li(2,2)); A.la(28,'rt_st_r2'); A.j('RT_MEMWR'); A.label('rt_st_r2')
        A.e(addu(15,31,0)); A.la(28,'rt_st_vb'); A.j('RT_VBL'); A.label('rt_st_vb'); A.j(('g',0x100))
        A.label('rt_stub_ret'); A.e(jr(31),0)
        A.label('RT_BX')
        A.brnd(bltz(25),'rt_host'); A.e(0)
        A.label('rt_hash')
        A.e(srl(1,25,1)); A.e(sll(24,1,1)); A.e(srl(2,1,11),xor(1,1,2),andi(1,1,s.nslots-1),sll(1,1,3))
        A.la(2,'HASH'); A.e(addu(1,1,2))
        A.label('rt_loop')
        A.e(lw(2,1,0))
        A.brnd(beq(2,24),'rt_found'); A.e(0)
        A.brnd(beq(2,0),'rt_miss'); A.e(0)
        A.e(addiu(1,1,8)); A.j('rt_loop')
        A.label('rt_found'); A.e(lw(25,1,4)); A.e(jr(25),0)
        A.label('rt_host')
        # host address inside the IWRAM window (a code pointer that was mapped as data): back to the guest address
        A.e(*M.li(1,s.cfg.reg[1][2])); A.e(subu(2,25,1)); A.e(srl(3,2,15))
        A.brnd(bne(3,0),'rt_direct'); A.e(0)
        for ti,(tsrc,tn,tcp) in enumerate(disc.TEMPLATES):   # RAM-code copy -> translated ROM template
            A.la(1,'ALIAS%d'%ti); A.e(lw(1,1,0)); A.e(subu(1,25,1)); A.e(sltiu(3,1,tn))
            nx='rt_na%d'%ti; A.brnd(beq(3,0),nx); A.e(0)
            A.e(*M.li(2,tsrc)); A.e(addu(25,1,2)); A.j('rt_hash')
            A.label(nx)
        A.e(lui(1,0x0300)); A.e(addu(25,2,1)); A.j('rt_hash')
        A.label('rt_direct'); A.e(jr(25),0)
        A.label('rt_miss'); A.e(addu(25,24,0)); A.j('RT_MISS')
    def finish(s,outdir=None):
        A=s.A
        # hash table data
        keys=sorted(a for a in s.ent if a in s.ins and not s.iscold(a))
        it,nh=M.hazard_pass(A.it)
        s.st['hazard_nops']=nh
        words,lab=M.link(it,s.cfg.BASE)
        gl=os.environ.get('COLD_GAP')          # TEST-ONLY (sim): "lo,hi" host range the cold code must not occupy (guest windows): code that would cross lo restarts at hi
        if gl:
            lo,hi=[int(x,16) for x in gl.split(',')]
            gaps={}
            for k,v in sorted(lab.items(),key=lambda kv:kv[1]):
                if isinstance(k,tuple) and k[0]=='gap' and v>=lo-0x20000 and ('fend',k[1]) in lab and lab[('fend',k[1])]>lo: gaps[k]=hi; break
            if gaps: words,lab=M.link(it,s.cfg.BASE,gaps=gaps); s.st['gap_at']=hex(lab[list(gaps)[0]])
        hb=(lab['HASH']-s.cfg.BASE)//4
        tab=[[0,0] for _ in range(s.nslots+64)]
        for key in keys:
            x=key>>1; h=(x^(x>>11))&(s.nslots-1)
            while tab[h][0]!=0: h+=1
            assert h<s.nslots+64
            tab[h]=[(key>>1)<<1,lab[('g',key)]]
        for k,(a,b) in enumerate(tab): words[hb+2*k]=a; words[hb+2*k+1]=b
        s.words=words; s.lab=lab; s.keys=keys
        bad=M.check_hazards(words[:hb])+[x+(lab['COLD_START']-s.cfg.BASE)//4 if isinstance(x,int) else x for x in M.check_hazards(words[(lab['COLD_START']-s.cfg.BASE)//4:])]
        s.st['hazard_violations']=len(bad)
        return words,lab
def build(rom_path,iw_path,outdir,mode='B',cache=None,verbose=True,pruned=False,tag=None,resident=None,cold=None):
    rom=open(rom_path,'rb').read(); iw=open(iw_path,'rb').read()
    if cache and os.path.exists(cache):
        P=pickle.load(open(cache,'rb')); P.img=disc.Img(rom,iw,[(0x100,__import__('prune').SWI_STUB)] if pruned else None)
    else:
        if pruned:
            import prune
            P=disc.discover(rom,iw,verbose,stubs=prune.stub_dict(),templates=[],extra=[(0x100,prune.SWI_STUB)],seeds=[(0x100,'A')])
        else: P=disc.discover(rom,iw,verbose)
        if cache:
            img=P.img; P.img=None; pickle.dump(P,open(cache,'wb')); P.img=img
    if resident:
        import bisect
        res,funcs=pickle.load(open(resident,'rb'))
        cs=set()
        if cold: cs,_f=pickle.load(open(cold,'rb')); cs=set(cs)-set(res)
        # functions are heuristic units: code can fall through from one into the next (and a call can fall into the return point).
        # merge such neighbours into groups that are always placed together (hot or cold).
        fo=lambda a:funcs[bisect.bisect_right(funcs,a)-1]
        par={f:f for f in set(funcs)|set(res)|set(cs)}
        def find(x):
            while par[x]!=x: par[x]=par[par[x]]; x=par[x]
            return x
        for a,i in P.ins.items():
            nx=a+i.size
            if nx in P.ins and falls(i) and fo(nx)!=fo(a):
                x,y=find(fo(a)),find(fo(nx))
                if x!=y: par[max(x,y)]=min(x,y)
        grp={f:find(f) for f in par}
        hotg={grp[f] for f in res}; cg={grp[f] for f in cs}-hotg
        P.ins={a:i for a,i in P.ins.items() if grp[fo(a)] in hotg|cg}
        P.cold=cg; P.funcs=funcs; P.grp=grp
        if os.environ.get('COLD_RANK'):
            S0=pickle.load(open(os.environ['COLD_RANK'],'rb')); P.cold_rank={grp[fo(f)]:0 for f in S0 if fo(f) in grp}
            if os.environ.get('COLD_RANK2'):      # stage 7 title-boot disc: a second tier (functions only the menus/boot run) behind the level's own groups
                S1=pickle.load(open(os.environ['COLD_RANK2'],'rb'))
                for f in S1:
                    if fo(f) in grp and grp[fo(f)] not in P.cold_rank: P.cold_rank[grp[fo(f)]]=1      # entries may be call targets inside a unit (0x08077d94): rank the unit that contains them
        if verbose: print('resident filter: %d insns kept (%d hot groups, %d cold groups)'%(len(P.ins),len(hotg),len(cg)))
    cfg=Cfg(mode)
    T=Tr(P,cfg,verbose)
    T.run()
    words,lab=T.finish()
    os.makedirs(outdir,exist_ok=True)
    tg=tag or mode
    ci=(lab['COLD_START']-T.cfg.BASE)//4; ce=(lab['COLD_END']-T.cfg.BASE)//4
    open(os.path.join(outdir,'payback_%s.bin'%tg),'wb').write(b''.join(struct.pack('<I',w) for w in words[:ci]))
    open(os.path.join(outdir,'cold_%s.bin'%tg),'wb').write(b''.join(struct.pack('<I',w) for w in words[ci:ce]))
    # overlay table: guest entry -> host entry + host span of the containing function (incl. its out-of-line stubs)
    rows=set()
    for a in set(T.cold and [f for f in T.cold if f in T.ins] or [])|{a for a in T.ent if a in T.ins and T.iscold(a)}|{x for x in T.miss_t if x in T.ins and T.iscold(x)}:
        if ('g',a) not in lab: continue       # not emitted (COLD_ONLY)
        f=T.fn_of(a); rows.add((a&~1,lab[('g',a)],lab[('g',f)] if ('g',f) in lab else lab[('g',a)],lab[('fend',f)]))
    if os.environ.get('COLD_FULLTAB'):
        # stage 4 fix: with COLD_ONLY the call targets are only collected from the emitted code, so a function entered through a pointer or from a code group that was not emitted
        # (e.g. 0x08077d94) had no row and the disc panicked "not in cold set".  Take every row of the full build's table (the F2 translation is identical for the emitted prefix).
        d=open(os.environ['COLD_FULLTAB'],'rb').read(); n=struct.unpack_from('<I',d,0)[0]; known={r[0] for r in rows}
        for i in range(n):
            g,h,hs,he=struct.unpack_from('<IIII',d,4+16*i)
            if g in known or ('g',g) not in lab: continue
            if lab[('g',g)]!=h: raise RuntimeError('full table row %x host differs'%g)
            rows.add((g,h,hs,he))
    rows=sorted(rows)
    open(os.path.join(outdir,'coldtab_%s.bin'%tg),'wb').write(struct.pack('<I',len(rows))+b''.join(struct.pack('<IIII',*r) for r in rows))
    T.cold_info=dict(start=lab['COLD_START'],end=lab['COLD_END'],rows=len(rows))
    # guest -> host map (sorted)
    gmap=sorted((k[1],v) for k,v in lab.items() if isinstance(k,tuple) and k[0]=='g')
    open(os.path.join(outdir,'payback_%s.map'%(tag or mode)),'w').write(''.join('%08x %08x\n'%(a,h) for a,h in gmap))
    rt={k:v for k,v in lab.items() if isinstance(k,str)}
    pickle.dump({'rt':rt,'cold':T.cold_info,'entries':T.keys,'stats':dict(T.st),'unsafe':dict(T.unsafe)},open(os.path.join(outdir,'meta_%s.pkl'%(tag or mode)),'wb'))
    return T
if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('rom'); ap.add_argument('iw'); ap.add_argument('out')
    ap.add_argument('--map',default='B'); ap.add_argument('--cache'); ap.add_argument('--pruned',action='store_true'); ap.add_argument('--tag'); ap.add_argument('--resident'); ap.add_argument('--cold')
    a=ap.parse_args()
    T=build(a.rom,a.iw,a.out,a.map,a.cache,pruned=a.pruned,tag=a.tag,resident=a.resident,cold=a.cold)
    print('words',len(T.words),'bytes',4*len(T.words),'insns',len(T.ins),'cold',T.cold_info)
    print(dict(T.st)); print(dict(T.unsafe))
