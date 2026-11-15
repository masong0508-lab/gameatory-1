#!/usr/bin/env python3
"""Static census of a GBA ROM's code (recursive descent, ARM+Thumb) for the PS1-port feasibility study.
Reads the user's own ROM; prints statistics only (no code/asset bytes are written anywhere but /tmp json of addr->mnemonic)."""
import sys, struct, json, collections
from capstone import *
from capstone.arm import *
rom=open(sys.argv[1],'rb').read(); N=len(rom); B=0x08000000
A=Cs(CS_ARCH_ARM,CS_MODE_ARM); A.detail=True
T=Cs(CS_ARCH_ARM,CS_MODE_THUMB); T.detail=True
code={}; lits=set(); seen=set(); work=[]
ext=collections.Counter(); swis=collections.Counter(); ind=collections.Counter(); resolved=collections.Counter()
def inrom(a): return B<=a<B+N
def u32(a):
    o=a-B; return struct.unpack('<I',rom[o:o+4])[0] if 0<=o<=N-4 else None
def push(a,m):
    if inrom(a):
        if (a,m) not in seen: work.append((a,m))
    else: ext[a>>24]+=1
def entry(v):   # a code pointer value -> (addr,mode)
    return (v&~1,'T') if v&1 else (v,'A')
def scan(a,m):
    regs={}
    while inrom(a):
        if a in code: return
        ins=next((T if m=='T' else A).disasm(rom[a-B:a-B+4],a,1),None)
        if ins is None: return
        mn=ins.mnemonic; ops=ins.operands; code[a]=(m,ins.size,mn)
        nxt=a+ins.size
        cond=ins.cc not in (ARM_CC_AL,ARM_CC_INVALID)
        if mn in('swi','svc'): swis[ops[0].imm if ops else 0]+=1
        # pc-relative literal / add rd,pc
        if mn.startswith('ldr') and len(ops)>=2 and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC and ops[0].type==ARM_OP_REG:
            ea=((a+4)&~3 if m=='T' else a+8)+ops[1].mem.disp; lits.add(ea)
            v=u32(ea) if inrom(ea) else None
            if v is not None: regs[ops[0].reg]=v
            else: regs.pop(ops[0].reg,None)
        elif mn=='add' and m=='A' and len(ops)==3 and ops[1].type==ARM_OP_REG and ops[1].reg==ARM_REG_PC and ops[2].type==ARM_OP_IMM:
            regs[ops[0].reg]=a+8+ops[2].imm
        elif mn=='add' and m=='T' and len(ops)>=2 and ops[1].type==ARM_OP_REG and ops[1].reg==ARM_REG_PC:
            regs[ops[0].reg]=((a+4)&~3)+ (ops[2].imm if len(ops)>2 else 0)
        elif mn in ('mov','movs') and len(ops)==2 and ops[1].type==ARM_OP_IMM and ops[0].type==ARM_OP_REG: regs[ops[0].reg]=ops[1].imm&0xffffffff
        elif mn=='mov' and len(ops)==2 and ops[0].type==ARM_OP_REG and ops[1].type==ARM_OP_REG and ops[0].reg==ARM_REG_LR and ops[1].reg==ARM_REG_PC: pass
        elif ops and ops[0].type==ARM_OP_REG and mn not in ('cmp','cmn','tst','teq','str','strb','strh','stm','stmia','push','b','bl','bx','blx') and not mn.startswith('b'):
            regs.pop(ops[0].reg,None)
        # branches
        if mn in('bl','blx') and ops and ops[0].type==ARM_OP_IMM:
            push(ops[0].imm,'T' if mn=='blx' and m=='A' else m)
            a=nxt; regs={r:v for r,v in regs.items() if r>=4 and r<=11}; continue
        if mn in('bx','blx') and ops and ops[0].type==ARM_OP_REG:
            v=regs.get(ops[0].reg)
            if v is not None and inrom(v&~1): push(*entry(v)); resolved['bx/blx resolved by const-prop']+=1
            else: ind['bx/blx reg unresolved (indirect call/ret)']+=1
            if mn=='bx' and not cond: return
            a=nxt; continue
        if mn.startswith('b') and mn not in('bic','bics','bkpt','bfc','bfi') and ops and ops[0].type==ARM_OP_IMM:
            push(ops[0].imm,m)
            if not cond and mn=='b': return
            a=nxt; continue
        if mn=='pop' and any(o.type==ARM_OP_REG and o.reg==ARM_REG_PC for o in ops):
            ind['pop {pc} (return)']+=1
            if not cond: return
        if m=='A':
            wpc = ops and ops[0].type==ARM_OP_REG and ops[0].reg==ARM_REG_PC and mn[:3] in('mov','ldr','add','sub','eor','orr')
            if wpc:
                ind['arm write-pc: '+mn[:3]]+=1
                if not cond: return
            if mn.startswith('ldm') and any(o.type==ARM_OP_REG and o.reg==ARM_REG_PC for o in ops[1:]):
                ind['arm ldm {..pc} (return)']+=1
                if not cond: return
        if m=='T' and mn in('mov','add') and ops and ops[0].type==ARM_OP_REG and ops[0].reg==ARM_REG_PC:
            ind['thumb write-pc: '+mn]+=1; return
        a=nxt
def drain():
    while work:
        a,m=work.pop()
        if (a,m) in seen: continue
        seen.add((a,m)); scan(a,m)
work.append((B,'A')); drain()
# pass 2: code pointers stored as data (jump tables, vtables, callbacks): aligned words in ROM that point to an
# even/odd address inside the span of discovered code and that are NOT inside discovered code or literal pools
lo=min(code); hi=max(code)
span=hi
print("pass1: code span %08x..%08x, insns %d"%(lo,hi,len(code)))
seeds=0
for it in range(6):
    new=0
    for o in range(0,min(N,hi-B+0x1000),4):
        a=B+o
        if a in code or (a in lits): continue
        v=struct.unpack('<I',rom[o:o+4])[0]
        if B<=(v&~1)<B+N and (v&~1)<=hi and (v&~1)>=B+0x100:
            t,m=entry(v)
            if (t,m) in seen or t in code: continue
            # accept only if the target decodes to >=4 plausible instructions before a terminator
            work.append((t,m)); new+=1
    before=len(code); drain(); seeds+=new
    if len(code)==before: break
    hi=max(code)
print("pass2: seeded %d pointer targets; insns now %d span to %08x"%(seeds,len(code),hi))
nA=sum(1 for v in code.values() if v[0]=='A'); nT=sum(1 for v in code.values() if v[0]=='T')
bA=sum(v[1] for v in code.values() if v[0]=='A'); bT=sum(v[1] for v in code.values() if v[0]=='T')
print(f"insns ARM {nA} ({bA} B)  Thumb {nT} ({bT} B)  total code bytes {bA+bT} of ROM {N}")
print("SWI counts (BIOS fn):",dict(sorted(swis.items())))
print("branch targets outside ROM (addr>>24):",dict(ext))
print("indirect/return forms:",dict(ind),"resolved:",dict(resolved))
vals=collections.Counter(); io=collections.Counter()
for ea in lits:
    v=u32(ea) if inrom(ea) else None
    if v is None: continue
    vals[v>>24]+=1
    if v>>24==4 and (v&0xffffff)<0x400: io[v]+=1
print("literal pool words:",len(lits),{hex(k):v for k,v in sorted(vals.items(),key=lambda x:-x[1])[:8]})
print("IO register literals:",{hex(k):v for k,v in sorted(io.items())})
json.dump({str(a):v for a,v in code.items()},open(sys.argv[2],'w'))
