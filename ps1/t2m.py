#!/usr/bin/env python3
"""Thumb-1 -> MIPS-I (R3000) static translator front/back end, prototype.
Guest regs: r0-r7 -> $16-$23, r8-r12 -> $11-$15, sp -> $30, lr -> $28 (host return address inside translated code).
Temps: $1 $2 $3 $8 $9 $10 $24 $25.  Runtime helpers are called with jal and keep all guest regs.
Flags are lazy: a cmp/cmn/tst or result-setting op followed by a conditional branch is fused into slt/sltu/beq/bne;
anything else that needs the flags falls to a 'flags helper' (counted)."""
import struct, collections
from capstone import *
from capstone.arm import *
T=Cs(CS_ARCH_ARM,CS_MODE_THUMB); T.detail=True
R={ARM_REG_R0:16,ARM_REG_R1:17,ARM_REG_R2:18,ARM_REG_R3:19,ARM_REG_R4:20,ARM_REG_R5:21,ARM_REG_R6:22,ARM_REG_R7:23,
   ARM_REG_R8:11,ARM_REG_R9:12,ARM_REG_R10:13,ARM_REG_R11:14,ARM_REG_R12:15,ARM_REG_SP:30,ARM_REG_LR:28}
for _n,_v in (('SB',12),('SL',13),('FP',14),('IP',15)): R[getattr(__import__('capstone.arm',fromlist=['x']),'ARM_REG_'+_n)]=_v
ZERO,AT,V0,V1,T0,T1,T2,T8,T9=0,1,2,3,8,9,10,24,25
def rtype(op,rs,rt,rd,sh=0,fn=0): return (op<<26)|(rs<<21)|(rt<<16)|(rd<<11)|(sh<<6)|fn
def itype(op,rs,rt,imm): return (op<<26)|(rs<<21)|(rt<<16)|(imm&0xffff)
def addu(d,a,b): return rtype(0,a,b,d,0,0x21)
def subu(d,a,b): return rtype(0,a,b,d,0,0x23)
def and_(d,a,b): return rtype(0,a,b,d,0,0x24)
def or_(d,a,b): return rtype(0,a,b,d,0,0x25)
def xor(d,a,b): return rtype(0,a,b,d,0,0x26)
def nor(d,a,b): return rtype(0,a,b,d,0,0x27)
def slt(d,a,b): return rtype(0,a,b,d,0,0x2a)
def sltu(d,a,b): return rtype(0,a,b,d,0,0x2b)
def sll(d,t,s): return rtype(0,0,t,d,s,0)
def srl(d,t,s): return rtype(0,0,t,d,s,2)
def sra(d,t,s): return rtype(0,0,t,d,s,3)
def sllv(d,t,s): return rtype(0,s,t,d,0,4)
def srlv(d,t,s): return rtype(0,s,t,d,0,6)
def srav(d,t,s): return rtype(0,s,t,d,0,7)
def mult(a,b): return rtype(0,a,b,0,0,0x18)
def mflo(d): return rtype(0,0,0,d,0,0x12)
def mfhi(d): return rtype(0,0,0,d,0,0x10)
def addiu(t,s,i): return itype(9,s,t,i)
def andi(t,s,i): return itype(0xc,s,t,i)
def ori(t,s,i): return itype(0xd,s,t,i)
def xori(t,s,i): return itype(0xe,s,t,i)
def slti(t,s,i): return itype(0xa,s,t,i)
def sltiu(t,s,i): return itype(0xb,s,t,i)
def lui(t,i): return itype(0xf,0,t,i)
def lw(t,b,o): return itype(0x23,b,t,o)
def lh(t,b,o): return itype(0x21,b,t,o)
def lhu(t,b,o): return itype(0x25,b,t,o)
def lb(t,b,o): return itype(0x20,b,t,o)
def lbu(t,b,o): return itype(0x24,b,t,o)
def sw(t,b,o): return itype(0x2b,b,t,o)
def sh(t,b,o): return itype(0x29,b,t,o)
def sb(t,b,o): return itype(0x28,b,t,o)
def beq(a,b,off): return itype(4,a,b,off)
def bne(a,b,off): return itype(5,a,b,off)
def blez(a,off): return itype(6,a,0,off)
def bgtz(a,off): return itype(7,a,0,off)
def bltz(a,off): return itype(1,a,0,off)
def bgez(a,off): return itype(1,a,1,off)
def jr(a): return rtype(0,a,0,0,0,8)
def jalr(a,d=31): return rtype(0,a,0,d,0,9)
NOP=0
def li(d,v):
    v&=0xffffffff
    if v<0x8000: return [ori(d,0,v)]
    if v>=0xffff8000: return [addiu(d,0,v&0xffff)]
    if v&0xffff==0: return [lui(d,v>>16)]
    return [lui(d,v>>16),ori(d,d,v&0xffff)]
# guest memory layout of the proof harness / the real port (host = base + (guest&mask))
REG_BASE={2:0x80100000, 3:0x80140000}      # EWRAM 256K, IWRAM 32K (the GBA mirrors them; masks are applied statically)
REG_MASK={2:0x3ffff, 3:0x7fff}
class Tr:
    def __init__(s,rom,base=0x08000000,helpers=None):
        s.rom=rom; s.B=base; s.out=[]; s.lab={}; s.fix=[]; s.stats=collections.Counter(); s.helpers=helpers or {}
        s.known={}; s.flag=None; s.map={}
    def e(s,*w): s.out.extend(w)
    def here(s): return len(s.out)
    def reg(s,r): return R[r]
    def region_of(s,v): return (v>>24)&0xf
    def mem(s,ins,ld,size,signed):
        ops=ins.operands; rd=R[ops[0].reg]; m=ops[1].mem
        base=m.base; off=m.disp; idx=m.index if m.index!=0 else None
        if base==ARM_REG_PC:
            ea=((ins.address+4)&~3)+off; v=struct.unpack('<I',s.rom[ea-s.B:ea-s.B+4])[0]
            s.e(*li(rd,v)); s.known[rd]=v; s.stats['lit']+=1; return
        bv=s.known.get(R[base]) if idx is None else None
        if idx is None and base!=ARM_REG_SP and bv is not None and s.region_of(bv) in REG_BASE:
            reg=s.region_of(bv); ea=(bv+off)&REG_MASK[reg]; host=REG_BASE[reg]+ea
            hi=(host+0x8000)>>16; lo=host-(hi<<16)
            s.e(lui(T0,hi & 0xffff)); b=T0; o=lo; s.stats['mem_known']+=1
        elif base==ARM_REG_SP:
            # sp-relative: sp (r13) is a guest address in IWRAM/EWRAM; keep a pre-translated host copy in $30 so no extra cost
            b=R[ARM_REG_SP]; o=off; s.stats['mem_sp']+=1
        else:
            # unknown region: inline region dispatch (counted as 6) -> host addr in T0 (assumes EWRAM/IWRAM; else helper)
            s.stats['mem_dyn']+=1
            ra=R[base]
            if idx is not None:
                s.e(addu(T1,ra,R[idx])); ra=T1
            if off: s.e(addiu(T1,ra,off)); ra=T1
            # host = ((g & 0x3ffff) | (g>>24 & 1) <<18) + 0x80100000  ->  EWRAM at +0, IWRAM at +0x40000
            s.e(srl(T2,ra,24)); s.e(andi(T2,T2,1)); s.e(sll(T2,T2,18)); s.e(sll(T0,ra,14)); s.e(srl(T0,T0,14)); s.e(or_(T0,T0,T2))
            s.e(lui(T2,0x8010)); s.e(addu(T0,T0,T2)); b=T0; o=0
        if ld:
            op={ (4,False):lw,(2,False):lhu,(2,True):lh,(1,False):lbu,(1,True):lb }[(size,signed)]
            s.e(op(rd,b,o)); s.known.pop(rd,None)
        else:
            op={4:sw,2:sh,1:sb}[size]; s.e(op(rd,b,o))
    def cond_branch(s,cc,tgt,ins):
        f=s.flag
        L=('L',tgt)
        # returns branch words with delay-slot nop; label fixup on the branch word index
        def br(w,*pre):
            s.e(*pre); s.fix.append((s.here(),tgt)); s.e(w,NOP)
        if f is None: s.stats['flags_unknown']+=1; s.e(0x0000000d); s.stats['unsupp']+=1; return
        kind=f[0]
        if kind=='cmp':
            _,a,b=f   # compare a with b (b = reg or ('i',imm))
            if isinstance(b,tuple): bi=b[1]
            tests={ARM_CC_EQ:('eq',),ARM_CC_NE:('ne',)}
            if cc in (ARM_CC_EQ,ARM_CC_NE):
                if isinstance(b,tuple):
                    if bi==0: br((beq if cc==ARM_CC_EQ else bne)(a,0,0))
                    else: s.e(*li(T0,bi)); br((beq if cc==ARM_CC_EQ else bne)(a,T0,0))
                else: br((beq if cc==ARM_CC_EQ else bne)(a,b,0))
                return
            un=cc in (ARM_CC_HS,ARM_CC_LO,ARM_CC_HI,ARM_CC_LS)
            sl=sltu if un else slt; sli=sltiu if un else slti
            # a<b ; a>=b ; b<a ; b>=a
            if cc in (ARM_CC_LT,ARM_CC_LO,ARM_CC_GE,ARM_CC_HS):
                if isinstance(b,tuple): pre=[sli(T0,a,bi)] if bi<0x8000 else [*li(T1,bi),sl(T0,a,T1)]
                else: pre=[sl(T0,a,b)]
                br((bne if cc in(ARM_CC_LT,ARM_CC_LO) else beq)(T0,0,0),*pre)
            else:  # GT,LE,HI,LS : b<a
                if isinstance(b,tuple): pre=[*li(T1,bi),sl(T0,T1,a)]
                else: pre=[sl(T0,b,a)]
                br((bne if cc in(ARM_CC_GT,ARM_CC_HI) else beq)(T0,0,0),*pre)
            return
        if kind=='res':   # flags from a result register (movs/adds/subs/ands/lsls..): Z,N valid; C,V approximated
            _,r,arith=f
            m={ARM_CC_EQ:beq(r,0,0),ARM_CC_NE:bne(r,0,0),ARM_CC_MI:bltz(r,0),ARM_CC_PL:bgez(r,0),
               ARM_CC_LT:bltz(r,0),ARM_CC_GE:bgez(r,0),ARM_CC_GT:bgtz(r,0),ARM_CC_LE:blez(r,0)}
            if cc in m and not (arith and cc in (ARM_CC_LT,ARM_CC_GE,ARM_CC_GT,ARM_CC_LE) and False):
                s.stats['res_branch']+=1; br(m[cc]); return
        s.stats['flags_helper']+=1; s.e(0x0000000d,NOP); s.stats['unsupp']+=1   # break: C/V-dependent branch
    def ins(s,ins,nxt_is_bcc):
        mn=ins.mnemonic; ops=ins.operands; a=ins.address; st=s.stats
        def r(i): return R[ops[i].reg]
        def imm(i): return ops[i].imm
        base=mn.rstrip('s') if mn not in('movs','muls','adds','subs','ands','orrs','eors','lsls','lsrs','asrs','rsbs','bics','mvns','adcs','sbcs','rors') else mn[:-1]
        setf = mn in('movs','muls','adds','subs','ands','orrs','eors','lsls','lsrs','asrs','rsbs','bics','mvns','adcs','sbcs','rors')
        res=None
        if mn=='nop' or (mn=='mov' and len(ops)==2 and ops[0].reg==ops[1].reg): st['nop']+=1; return
        if mn in('movs','mov') and ops[1].type==ARM_OP_IMM:
            s.e(*li(r(0),imm(1))); s.known[r(0)]=imm(1)&0xffffffff; res=r(0)
        elif mn in('movs','mov') and ops[1].type==ARM_OP_REG and ops[1].reg==ARM_REG_PC:
            s.e(*li(r(0),a+4)); s.known[r(0)]=a+4; return
        elif mn in('movs','mov') and ops[1].type==ARM_OP_REG:
            s.e(addu(r(0),0,r(1))); 
            if r(1) in s.known: s.known[r(0)]=s.known[r(1)]
            else: s.known.pop(r(0),None)
            res=r(0)
        elif mn in('adds','add','subs','sub'):
            sub=mn.startswith('sub')
            rd=r(0)
            if len(ops)==3: rn=r(1); o=ops[2]
            else: rn=rd; o=ops[1]
            if o.type==ARM_OP_IMM:
                v=-o.imm if sub else o.imm
                if ops[1].type==ARM_OP_REG and ops[1].reg==ARM_REG_PC:
                    s.e(*li(rd,((a+4)&~3)+o.imm)); s.known[rd]=((a+4)&~3)+o.imm; return
                if ops[1].type==ARM_OP_REG and ops[1].reg==ARM_REG_SP and len(ops)==3:
                    s.e(addiu(rd,R[ARM_REG_SP],v)); s.known.pop(rd,None); return
                if -0x8000<=v<0x8000: s.e(addiu(rd,rn,v))
                else: s.e(*li(T0,v)); s.e(addu(rd,rn,T0))
                k=s.known.get(rn); 
                if k is not None: s.known[rd]=(k+v)&0xffffffff
                else: s.known.pop(rd,None)
            else:
                s.e((subu if sub else addu)(rd,rn,R[o.reg])); s.known.pop(rd,None)
            res=rd
        elif mn in('cmp','cmn'):
            if mn=='cmp':
                b=('i',ops[1].imm) if ops[1].type==ARM_OP_IMM else R[ops[1].reg]
                s.flag=('cmp',r(0),b)
                if not nxt_is_bcc: s.stats['flags_materialize']+=1
            else: s.flag=None
            return
        elif mn=='tst':
            s.e(and_(T0,r(0),r(1))); s.flag=('res',T0,False); return
        elif mn in('ands','orrs','eors','bics'):
            rd=r(0); rm=r(1) if len(ops)==2 else r(2)
            if mn=='ands': s.e(and_(rd,rd,rm))
            elif mn=='orrs': s.e(or_(rd,rd,rm))
            elif mn=='eors': s.e(xor(rd,rd,rm))
            else: s.e(nor(T0,rm,0),and_(rd,rd,T0))
            s.known.pop(rd,None); res=rd
        elif mn=='mvns': s.e(nor(r(0),r(1),0)); s.known.pop(r(0),None); res=r(0)
        elif mn=='rsbs': s.e(subu(r(0),0,r(1))); s.known.pop(r(0),None); res=r(0)
        elif mn=='muls': s.e(mult(r(0),r(1)),mflo(r(0))); s.known.pop(r(0),None); res=r(0)
        elif mn in('lsls','lsrs','asrs'):
            rd=r(0)
            if len(ops)==3 and ops[2].type==ARM_OP_IMM:
                n=ops[2].imm; rs=r(1)
                if mn=='lsls': s.e(sll(rd,rs,n))
                elif mn=='lsrs': s.e(srl(rd,rs,n) if 0<n<32 else addu(rd,0,0))
                else: s.e(sra(rd,rs,min(n,31)))
                k=s.known.get(rs)
                if k is not None and mn=='lsls': s.known[rd]=(k<<n)&0xffffffff
                else: s.known.pop(rd,None)
            else:   # register shift: ARM uses low byte of rm; >=32 gives 0 (lsl/lsr) / sign (asr)
                rm=r(1) if len(ops)==2 else r(2); rs=rd if len(ops)==2 else r(1)
                s.e(andi(T0,rm,0xff),sltiu(T1,T0,32))
                if mn=='asrs': s.e(srav(rd,rs,T0))   # approximation: shift>=32 handled by helper in real port
                else:
                    s.e(sllv(rd,rs,T0) if mn=='lsls' else srlv(rd,rs,T0)); s.e(subu(T1,0,T1),and_(rd,rd,T1))
                s.known.pop(rd,None)
            res=rd
        elif mn in('ldr','ldrb','ldrh','ldrsb','ldrsh','str','strb','strh'):
            size={'ldr':4,'str':4,'ldrb':1,'strb':1,'ldrh':2,'strh':2,'ldrsb':1,'ldrsh':2}[mn]
            s.mem(ins,mn.startswith('ld'),size,mn in('ldrsb','ldrsh')); return
        elif mn in('push','pop'):
            regs=[o for o in ops if o.type==ARM_OP_REG]; n=len(regs)
            sp=R[ARM_REG_SP]
            if mn=='push':
                s.e(addiu(sp,sp,-4*n))
                for i,o in enumerate(regs): s.e(sw(R[o.reg],sp,4*i))
            else:
                pcpop=any(o.reg==ARM_REG_PC for o in regs)
                for i,o in enumerate(regs):
                    if o.reg==ARM_REG_PC: s.e(lw(T0,sp,4*i))
                    elif getattr(s,'saved_lr',False): s.e(lw(R[o.reg],sp,4*i)); s.retregs=getattr(s,'retregs',set())|{o.reg}
                    else: s.e(lw(R[o.reg],sp,4*i))
                s.e(addiu(sp,sp,4*n))
                if pcpop: s.e(jr(T0),NOP); st['ret']+=1
            s.known={}; return
        elif mn=='bx':
            if ops[0].reg==ARM_REG_LR: s.e(jr(R[ARM_REG_LR]),NOP); st['ret']+=1
            elif getattr(s,'retregs',None) and ops[0].reg in s.retregs: s.e(jr(R[ops[0].reg]),NOP); st['ret']+=1
            else: s.e(0x0000000d,NOP); st['bx_indirect']+=1; st['unsupp']+=1
            return
        elif mn=='bl':
            s.fix.append((s.here(),('call',ops[0].imm))); s.e(0x0c000000,NOP)
            s.known={k:v for k,v in s.known.items() if k in(R[ARM_REG_R8],)} ; st['call']+=1; return
        elif mn=='b':
            s.fix.append((s.here(),ops[0].imm)); s.e(beq(0,0,0),NOP); return
        elif mn.startswith('b') and ops and ops[0].type==ARM_OP_IMM:
            s.cond_branch(ins.cc,ops[0].imm,ins); return
        elif mn in('sxtb','sxth','uxtb','uxth'):
            if mn=='uxtb': s.e(andi(r(0),r(1),0xff))
            elif mn=='uxth': s.e(andi(r(0),r(1),0xffff))
            elif mn=='sxtb': s.e(sll(r(0),r(1),24),sra(r(0),r(0),24))
            else: s.e(sll(r(0),r(1),16),sra(r(0),r(0),16))
            s.known.pop(r(0),None); return
        else:
            s.e(0x0000000d); st['unsupp']+=1; st['unsupp:'+mn]+=1; return
        if setf and res is not None:
            s.flag=('res',res,mn in('adds','subs','rsbs','muls'))
