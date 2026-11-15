#!/usr/bin/env python3
"""MIPS-I (R3000) encoders, a small label assembler with fixups, the load-delay/HI-LO hazard pass, hazard checker and a
disassembler for the subset we emit (used to write the .s file and cross-checked against GNU as)."""
import struct
def R(op,rs,rt,rd,sh,fn): return (op<<26)|(rs<<21)|(rt<<16)|(rd<<11)|(sh<<6)|fn
def Ii(op,rs,rt,imm): return (op<<26)|(rs<<21)|(rt<<16)|(imm&0xffff)
def addu(d,a,b): return R(0,a,b,d,0,0x21)
def subu(d,a,b): return R(0,a,b,d,0,0x23)
def and_(d,a,b): return R(0,a,b,d,0,0x24)
def or_(d,a,b): return R(0,a,b,d,0,0x25)
def xor(d,a,b): return R(0,a,b,d,0,0x26)
def nor(d,a,b): return R(0,a,b,d,0,0x27)
def slt(d,a,b): return R(0,a,b,d,0,0x2a)
def sltu(d,a,b): return R(0,a,b,d,0,0x2b)
def sll(d,t,s): return R(0,0,t,d,s,0)
def srl(d,t,s): return R(0,0,t,d,s,2)
def sra(d,t,s): return R(0,0,t,d,s,3)
def sllv(d,t,s): return R(0,s,t,d,0,4)
def srlv(d,t,s): return R(0,s,t,d,0,6)
def srav(d,t,s): return R(0,s,t,d,0,7)
def mult(a,b): return R(0,a,b,0,0,0x18)
def multu(a,b): return R(0,a,b,0,0,0x19)
def mflo(d): return R(0,0,0,d,0,0x12)
def mfhi(d): return R(0,0,0,d,0,0x10)
def addiu(t,s,i): return Ii(9,s,t,i)
def andi(t,s,i): return Ii(0xc,s,t,i)
def ori(t,s,i): return Ii(0xd,s,t,i)
def xori(t,s,i): return Ii(0xe,s,t,i)
def slti(t,s,i): return Ii(0xa,s,t,i)
def sltiu(t,s,i): return Ii(0xb,s,t,i)
def lui(t,i): return Ii(0xf,0,t,i)
def lw(t,b,o): return Ii(0x23,b,t,o)
def lh(t,b,o): return Ii(0x21,b,t,o)
def lhu(t,b,o): return Ii(0x25,b,t,o)
def lb(t,b,o): return Ii(0x20,b,t,o)
def lbu(t,b,o): return Ii(0x24,b,t,o)
def sw(t,b,o): return Ii(0x2b,b,t,o)
def sh(t,b,o): return Ii(0x29,b,t,o)
def sb(t,b,o): return Ii(0x28,b,t,o)
def beq(a,b): return Ii(4,a,b,0)
def bne(a,b): return Ii(5,a,b,0)
def blez(a): return Ii(6,a,0,0)
def bgtz(a): return Ii(7,a,0,0)
def bltz(a): return Ii(1,a,0,0)
def bgez(a): return Ii(1,a,1,0)
def jr(a): return R(0,a,0,0,0,8)
def jalr(a,d=31): return R(0,a,0,d,0,9)
def j_(): return 0x08000000
def jal_(): return 0x0c000000
def brk(code=0): return (code<<6)|0xd
NOP=0
def move(d,s): return addu(d,s,0)
def li(d,v):
    v&=0xffffffff
    if v<0x10000: return [ori(d,0,v)]
    if v>=0xffff8000: return [addiu(d,0,v&0xffff)]
    if v&0xffff==0: return [lui(d,v>>16)]
    return [lui(d,v>>16),ori(d,d,v&0xffff)]
RN=['zero','at','v0','v1','a0','a1','a2','a3','t0','t1','t2','t3','t4','t5','t6','t7','s0','s1','s2','s3','s4','s5','s6','s7','t8','t9','k0','k1','gp','sp','fp','ra']
LOADS=(0x20,0x21,0x23,0x24,0x25,0x22,0x26)
def reads_writes(w):
    """(reads set, writes set, kind) for the subset; kind in 'load','branch','jump','hilo','mulop','other'"""
    op=w>>26; rs=(w>>21)&31; rt=(w>>16)&31; rd=(w>>11)&31; fn=w&63
    if op==0:
        if fn in(0,2,3): return {rt},{rd},'other'
        if fn in(4,6,7): return {rs,rt},{rd},'other'
        if fn==8: return {rs},set(),'jump'
        if fn==9: return {rs},{rd},'jump'
        if fn in(0x10,0x12): return set(),{rd},'mf'
        if fn in(0x11,0x13): return {rs},set(),'mt'
        if fn in(0x18,0x19,0x1a,0x1b): return {rs,rt},set(),'mulop'
        if fn==0xd or fn==0xc: return set(),set(),'other'
        return {rs,rt},{rd},'other'
    if op==1: return {rs},set(),'branch'
    if op in(2,3): return set(),({31} if op==3 else set()),'jump'
    if op in(4,5): return {rs,rt},set(),'branch'
    if op in(6,7): return {rs},set(),'branch'
    if op in LOADS: return {rs},{rt},'load'
    if op in(0x28,0x29,0x2b,0x2a,0x2e): return {rs,rt},set(),'store'
    if op==0xf: return set(),{rt},'other'
    return {rs},{rt},'other'
class Asm:
    """list of items: int words, ('L',name) labels, (kind,word,label) fixups: kind B (branch rel16), J (j/jal abs26), HI/LO (lui/ori of label address)"""
    def __init__(s): s.it=[]
    def e(s,*w): s.it.extend(w)
    def label(s,n): s.it.append(('L',n))
    def br(s,w,lab): s.it.append(('B',w,lab)); s.it.append(0)
    def brnd(s,w,lab): s.it.append(('B',w,lab))      # no delay slot filler (caller supplies)
    def j(s,lab): s.it.append(('J',j_(),lab)); s.it.append(0)
    def jal(s,lab): s.it.append(('J',jal_(),lab)); s.it.append(0)
    def la(s,reg,lab): s.it.append(('HI',lui(reg,0),lab)); s.it.append(('LO',ori(reg,reg,0),lab))
def hazard_pass(it):
    """insert nops so no instruction reads or writes the destination of the immediately preceding load, and keep >=2 slots
    between mflo/mfhi and a following mult/div. Works on the item list (labels are markers). Returns new list and count."""
    out=[]; n=0
    pl=None   # (dest reg, pending slots) of previous load
    lastmf=99
    for x in it:
        if isinstance(x,tuple) and x[0]=='L': out.append(x); continue
        w=x if isinstance(x,int) else x[1]
        r,wr,k=reads_writes(w)
        if pl is not None and pl!=0 and (pl in r or pl in wr):
            out.append(0); n+=1
        pl=None
        if k=='mulop' and lastmf<2:
            for _ in range(2-lastmf): out.append(0); n+=1
            lastmf=2
        out.append(x)
        if k=='load': pl=list(wr)[0]
        lastmf = 0 if k=='mf' else lastmf+1
        if (isinstance(x,tuple) and x[0] in('B','J')) or k in('branch','jump'): pass
    return out,n
def link(it,base,labels_extra=None):
    """resolve labels -> bytes. returns (words, labelmap name->address)"""
    pos={}; idx=0
    for x in it:
        if isinstance(x,tuple) and x[0]=='L': pos[x[1]]=idx
        else: idx+=1
    words=[0]*idx; i=0
    for x in it:
        if isinstance(x,tuple) and x[0]=='L': continue
        if isinstance(x,int): words[i]=x&0xffffffff
        else:
            k,w,lab=x
            if lab not in pos: raise KeyError('undefined label %r at word %d'%(lab,i))
            t=pos[lab]
            if k=='B':
                off=t-(i+1)
                if not -32768<=off<32768: raise ValueError('branch out of range label %r off %d'%(lab,off))
                w=(w&0xffff0000)|(off&0xffff)
            elif k=='J': w=w|(((base+4*t)>>2)&0x3ffffff)
            elif k=='HI':
                a=base+4*t; w=(w&0xffff0000)|((a>>16)&0xffff)
            elif k=='LO':
                a=base+4*t; w=(w&0xffff0000)|(a&0xffff)
            words[i]=w&0xffffffff
        i+=1
    return words,{k:base+4*v for k,v in pos.items()}
def check_hazards(words):
    """verify no load-delay hazards in a linked word list; returns list of indices of violating instruction"""
    bad=[]
    pl=None
    for i,w in enumerate(words):
        r,wr,k=reads_writes(w)
        if pl and (pl in r or pl in wr): bad.append(i)
        pl=list(wr)[0] if k=='load' and list(wr)[0]!=0 else None
    return bad
# ---- disassembler (our subset)
def dis(w,pc=0,sym=None):
    op=w>>26; rs=(w>>21)&31; rt=(w>>16)&31; rd=(w>>11)&31; sa=(w>>6)&31; fn=w&63; imm=w&0xffff; simm=imm-0x10000 if imm&0x8000 else imm
    r=lambda x:'$'+RN[x]
    if w==0: return 'nop'
    if op==0:
        t={0x21:'addu',0x23:'subu',0x24:'and',0x25:'or',0x26:'xor',0x27:'nor',0x2a:'slt',0x2b:'sltu'}
        if fn in t: return '%s %s,%s,%s'%(t[fn],r(rd),r(rs),r(rt))
        if fn in(0,2,3): return '%s %s,%s,%d'%({0:'sll',2:'srl',3:'sra'}[fn],r(rd),r(rt),sa)
        if fn in(4,6,7): return '%s %s,%s,%s'%({4:'sllv',6:'srlv',7:'srav'}[fn],r(rd),r(rt),r(rs))
        if fn in(0x18,0x19): return '%s %s,%s'%({0x18:'mult',0x19:'multu'}[fn],r(rs),r(rt))
        if fn==0x12: return 'mflo '+r(rd)
        if fn==0x10: return 'mfhi '+r(rd)
        if fn==8: return 'jr '+r(rs)
        if fn==9: return 'jalr %s,%s'%(r(rd),r(rs))
        if fn==0xd: return 'break 0x%x'%((w>>6)&0xfffff)
    if op in(0x9,0xa,0xb): return '%s %s,%s,%d'%({9:'addiu',0xa:'slti',0xb:'sltiu'}[op],r(rt),r(rs),simm)
    if op in(0xc,0xd,0xe): return '%s %s,%s,0x%x'%({0xc:'andi',0xd:'ori',0xe:'xori'}[op],r(rt),r(rs),imm)
    if op==0xf: return 'lui %s,0x%x'%(r(rt),imm)
    ls={0x20:'lb',0x21:'lh',0x23:'lw',0x24:'lbu',0x25:'lhu',0x28:'sb',0x29:'sh',0x2b:'sw'}
    if op in ls: return '%s %s,%d(%s)'%(ls[op],r(rt),simm,r(rs))
    tgt=pc+4+simm*4
    nm=(sym(tgt) if sym else '0x%x'%tgt)
    if op==4: return 'beq %s,%s,%s'%(r(rs),r(rt),nm)
    if op==5: return 'bne %s,%s,%s'%(r(rs),r(rt),nm)
    if op==6: return 'blez %s,%s'%(r(rs),nm)
    if op==7: return 'bgtz %s,%s'%(r(rs),nm)
    if op==1: return '%s %s,%s'%('bgez' if rt==1 else 'bltz',r(rs),nm)
    if op in(2,3):
        t=((pc+4)&0xf0000000)|((w&0x3ffffff)<<2)
        return '%s %s'%('j' if op==2 else 'jal',sym(t) if sym else '0x%x'%t)
    return '.word 0x%08x'%w
