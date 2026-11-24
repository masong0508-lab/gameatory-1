#!/usr/bin/env python3
"""Code discovery (recursive descent over ROM Thumb/ARM and the IWRAM ARM image) using armdec IR."""
import struct,sys,collections
import armdec as D
from armdec import *
ROMB=0x08000000
IWCODE_END=0x03006cc4
class Img:
    """static view of guest memory for translation: ROM + IWRAM code image (+ optional extra regions for tests)"""
    def __init__(s,rom,iw,extra=None):
        s.rom=rom; s.iw=iw; s.extra=extra or []
    def rd16(s,a):
        for b,d in s.extra:
            if b<=a<b+len(d): return struct.unpack_from('<H',d,a-b)[0]
        if a>>24==8:
            o=a-ROMB; return struct.unpack_from('<H',s.rom,o)[0] if o+2<=len(s.rom) else None
        if a>>24==3:
            o=a&0x7fff; return struct.unpack_from('<H',s.iw,o)[0]
        return None
    def rd32(s,a):
        for b,d in s.extra:
            if b<=a<b+len(d): return struct.unpack_from('<I',d,a-b)[0]
        if a>>24==8:
            o=a-ROMB; return struct.unpack_from('<I',s.rom,o)[0] if o+4<=len(s.rom) else None
        if a>>24==3:
            o=a&0x7fff; return struct.unpack_from('<I',s.iw,o)[0]
        return None
    def dec(s,a,mode):
        if mode=='T':
            h=s.rd16(a)
            if h is None: return None
            h2=s.rd16(a+2) if (h>>11)==0x1e else None
            return thumb(h,a,h2)
        w=s.rd32(a)
        if w is None: return None
        return arm(w,a)
EXTRA_RANGES=[]
# Milestone B (merged Star-FlyBack ROM): PB_DATA_SPANS="lo-hi,lo-hi" (hex) are guest ROM ranges that discovery treats as data: the mod's own code
# (run by the interpreter) and guest routines that must stay interpreted (the overlay loader, interp_glue.h ip_hle).  A call into them is
# translated as a call through RT_MISS.  Unset (every original-game build): no change.
DATA_SPANS=[tuple(int(x,16) for x in p.split('-')) for p in __import__('os').environ.get('PB_DATA_SPANS','').split(',') if p]
def inrange(a):
    if DATA_SPANS and any(lo<=a<hi for lo,hi in DATA_SPANS): return False
    if ROMB<=a<ROMB+0x800000 or 0x03000000<=a<IWCODE_END: return True
    return any(lo<=a<hi for lo,hi in EXTRA_RANGES)
def isarmreg(r): return r is not None
class Prog:
    def __init__(s,img):
        s.img=img; s.ins={}; s.entries=set(); s.lits=set(); s.targets=set(); s.indirect=[]; s.unres=[]
        s.callt=set(); s.jt=set(); s.tables={}; s.bad=0; s.stubs={}
    def run(s,seeds,verbose=False):
        work=list(seeds); seen=set()
        while work:
            a,m=work.pop()
            if (a,m) in seen: continue
            seen.add((a,m))
            if a in s.stubs: s.entries.add(a); continue
            s.scan(a,m,work)
    def scan(s,a,m,work):
        regs={}
        img=s.img
        while inrange(a):
            if a in s.ins or a in s.stubs:
                # reached known code (assume same mode)
                return
            i=img.dec(a,m)
            if i is None: s.bad+=1; return
            if i.op=='undef': s.bad+=1; return
            if i.raw==0 and m=='T': s.bad+=1; return
            s.ins[a]=i
            nxt=a+i.size
            al=(i.cond==14)
            op=i.op
            # literal tracking
            if op=='mem' and i.rn==15 and i.ld and i.imm is not None:
                pc=s.pcval(i)&~3 if m=='T' else s.pcval(i)
                ea=pc+(i.imm if i.up else -i.imm)
                if not i.pre: ea=pc
                s.lits.add(ea&~3); 
                v=img.rd32(ea&~3)
                if v is not None and i.sz==4: regs[i.rd]=v
                else: regs.pop(i.rd,None)
            elif op=='mem' and i.ld and i.sz==4 and i.rm is not None and i.rn!=15 and i.rd!=15 and any(isinstance(regs.get(x),int) and inrange(regs[x]) for x in(i.rn,i.rm)):
                regs[i.rd]=('TAB',[regs[x] for x in(i.rn,i.rm) if isinstance(regs.get(x),int) and inrange(regs[x])][-1],0)
            elif op=='dp' and i.rn==15 and i.opc in(D.ADD,D.SUB) and i.imm is not None and i.rd!=15:
                regs[i.rd]=(s.pcval(i)&~3 if m=='T' else s.pcval(i))+(i.imm if i.opc==D.ADD else -i.imm)
            elif op=='dp' and i.opc==D.CMP and i.imm is not None and i.rm is None:
                regs['cmpN']=i.imm
            elif op=='dp' and i.opc in(D.MOV,) and i.rm is None and i.imm is not None and i.rd!=15:
                regs[i.rd]=i.imm
            elif op=='dp' and i.opc==D.MOV and i.rm==15 and i.shamt==0 and i.shreg is None:
                regs[i.rd]=s.pcval(i)
            elif op=='dp' and i.opc==D.MOV and i.rm is not None and i.sh==D.LSL and i.shamt and isinstance(regs.get(i.rm),int) and i.shreg is None:
                regs[i.rd]=(regs[i.rm]<<i.shamt)&0xffffffff
            elif op=='dp' and i.opc in (D.ADD,) and i.rm is None and i.imm is not None and isinstance(regs.get(i.rn),int) and i.rd not in(15,):
                regs[i.rd]=(regs[i.rn]+i.imm)&0xffffffff
            else:
                for r in s.writes(i): regs.pop(r,None)
            if op=='bl':
                work.append((i.target,m)); s.callt.add(i.target); s.entries.add(i.target)
                regs={}
                a=nxt; continue
            if op=='b':
                s.targets.add(i.target); work.append((i.target,m))
                if al: return
                a=nxt; continue
            if op=='bx':
                v=s.pcval(i) if i.rm==15 else regs.get(i.rm)
                if i.rm==15: i.target=v&~1
                if isinstance(v,int) and inrange(v&~1):
                    mm='T' if v&1 else 'A'; work.append((v&~1,mm)); s.entries.add(v&~1); s.targets.add(v&~1)
                else: s.indirect.append(a)
                pv=s.ins.get(a-4)
                if al and not (m=='A' and pv is not None and pv.op=='dp' and pv.opc==D.MOV and pv.rd==14 and pv.rm==15 and pv.shamt==0): return    # mov lr,pc; bx rX = call
                a=nxt; continue
            wpc=False
            if op=='dp' and i.rd==15 and i.opc not in(D.TST,D.TEQ,D.CMP,D.CMN): wpc=True
            if op=='mem' and i.ld and i.rd==15: wpc=True
            if op=='ldm' and i.ld and (i.regs>>15)&1: wpc=True
            if wpc:
                s.indirect.append(a)
                tb=None
                if op=='dp' and i.opc==D.MOV and i.rm is not None and isinstance(regs.get(i.rm),tuple): tb=regs[i.rm][1]
                if op=='mem' and i.rn==15 and i.rm is not None and m=='A':     # ldr pc,[pc,rm,lsl #2] : table at addr+8
                    tb=a+8
                if tb is not None:
                    n=0; t=tb; lim=regs['cmpN']+1 if isinstance(regs.get('cmpN'),int) and regs['cmpN']<256 else 40
                    if m=='A': lim=64
                    while n<lim:
                        w=img.rd32(t)
                        if w is None or not inrange(w&~1) or (w&~1)==0 or abs((w&~1)-a)>0x20000: break
                        if m=='A' and w&3: break
                        if m=='T' and w>>24!=8: break
                        work.append((w&~1,m)); s.targets.add(w&~1); s.entries.add(w&~1); s.jt.add(w&~1); s.lits.add(t); n+=1; t+=4
                    s.tables[a]=(tb,n)
                if al: return
            a=nxt
    def pcval(s,i): return i.addr+(4 if i.mode=='T' else 8)
    def writes(s,i):
        if i.op=='dp':
            return [] if i.opc in(D.TST,D.TEQ,D.CMP,D.CMN) else [i.rd]
        if i.op=='mem': return ([i.rd] if i.ld else [])+([i.rn] if i.wb or not i.pre else [])
        if i.op in('mul',): return [i.rd]
        if i.op=='mull': return [i.rd,i.rdhi]
        if i.op=='ldm': return [r for r in range(16) if (i.regs>>r)&1 and i.ld]+([i.rn] if i.wb else [])
        if i.op=='mrs' or i.op=='swp': return [i.rd]
        return []

# RAM-resident code templates: (rom source, bytes copied, copy routine entry whose r0=src,r1=dst).  The template is translated at its
# ROM address; the runtime maps calls into the RAM copy back to it (see t2m runtime ALIAS).
TEMPLATES=[(0x0806c294,0x400,0x0807c808)]
def discover(rom,iw,verbose=True,stubs=None,templates=None,extra=None,seeds=None):
    """full discovery: ROM roots, pointer-table seeds, jump tables, orphan functions, IWRAM image seeds and sweeps.
    Returns Prog. Orphans: push{lr} prologues in the ROM code span that nothing references."""
    global TEMPLATES
    if templates is not None: TEMPLATES=templates
    img=Img(rom,iw,extra)
    for b,d in (extra or []): EXTRA_RANGES.append((b,b+len(d)))
    P=Prog(img); P.stubs=dict(stubs or {})
    P.run([(ROMB,'A')]+[(t,'A') for t,_,_ in TEMPLATES]+list(seeds or []))
    for t,_,_ in TEMPLATES: P.entries.add(t)
    for a_,m_ in (seeds or []): P.entries.add(a_)
    n0=len(P.ins)
    # IWRAM seeds: literals and aligned ROM words pointing into the IWRAM code image
    seeds=set()
    for ea in list(P.lits):
        v=img.rd32(ea)
        if v is not None and 0x03000000<=v<IWCODE_END and (v&3==0 or v&1): seeds.add(v)
    for o in range(0,0x7ca00,4):
        v=struct.unpack_from('<I',rom,o)[0]
        if 0x03000000<=v<IWCODE_END and (v&3==0 or v&1): seeds.add(v)
    P.run([(v&~1,'T' if v&1 else 'A') for v in seeds])
    for v in seeds: P.entries.add(v&~1)
    # ROM pointer-like data words (thumb bit set) into known code that are not instruction starts
    cov=set()
    def covered():
        c=set()
        for a,i in P.ins.items(): c.update(range(a,a+i.size))
        return c
    cov=covered()
    P.orph=[]
    cands=[]
    for o in range(0,0x7c9e0,2):
        a=ROMB+o
        if a in cov: continue
        h=struct.unpack_from('<H',rom,o)[0]
        if (h&0xff00)==0xb500 and (a&1)==0 and not any((a&~3)==l for l in P.lits): cands.append(a)
    before=len(P.ins)
    P.run([(a,'T') for a in cands])
    P.orph=[a for a in cands if a in P.ins]
    for a in P.orph: P.entries.add(a)
    # data pointers into the code span (switch tables of unresolved dispatchers, callback tables, even=ARM entries)
    def absorb(Q):
        for k,v in Q.ins.items(): P.ins.setdefault(k,v)
        P.lits|=Q.lits; P.targets|=Q.targets; P.entries|=Q.entries; P.callt|=Q.callt; P.indirect+=Q.indirect; P.jt|=Q.jt; P.tables.update(Q.tables)
    P.dptr=set()
    import numpy as np
    words=np.frombuffer(rom[:len(rom)//4*4],dtype='<u4')
    vv=words&~np.uint32(1)
    cand_idx=np.nonzero((vv>=ROMB+0x100)&(vv<ROMB+0x7c9e0))[0]
    cb=bytearray(max(0x800000,len(rom)))      # Milestone B: the 16 MiB merged ROM's words are scanned too
    for a,i in P.ins.items():
        if a>>24==8: cb[a-ROMB:a-ROMB+i.size]=b'\1'*i.size
    ib=bytearray(cb)
    for l in P.lits:
        if l>>24==8 and l-ROMB+4<=len(cb): cb[l-ROMB:l-ROMB+4]=b'\1\1\1\1'
    for rnd in range(8):
        got=0
        for ix in cand_idx:
            o=int(ix)*4
            if ib[o] or ib[o+2]: continue
            v=int(words[ix]); t=v&~1
            tt=t-ROMB
            if t in P.ins or cb[tt] or cb[tt+1]: continue
            w=struct.unpack_from('<I',rom,tt)[0]
            arm_sig=(t&3==0 and (w&0xffff0000)==0xe92d0000 and w&0x4000)
            if v&1==0 and not arm_sig and (t&1): continue
            Q=Prog(img); Q.stubs=P.stubs; Q.lits=set(P.lits); Q.run([(t,'A' if (v&1==0 and arm_sig) else 'T')])
            if Q.bad==0 and len(Q.ins)>=3 and not any(a2 in P.ins and P.ins[a2].size!=q.size for a2,q in Q.ins.items()):
                absorb(Q); P.entries.add(t); P.dptr.add(t); got+=1
                for a,i in Q.ins.items():
                    if a>>24==8: cb[a-ROMB:a-ROMB+i.size]=b'\1'*i.size; ib[a-ROMB:a-ROMB+i.size]=b'\1'*i.size
                for l in Q.lits:
                    if l>>24==8 and l-ROMB+4<=len(cb): cb[l-ROMB:l-ROMB+4]=b'\1\1\1\1'
        if not got: break
    # IWRAM sweeps: an undecoded nonzero word that directly follows a terminating instruction / literal / zero word starts a function
    def term(i): return i.cond==14 and (i.op in('b','bx') or (i.op=='dp' and i.rd==15) or (i.op=='ldm' and i.ld and i.regs>>15&1) or (i.op=='mem' and i.ld and i.rd==15))
    for rnd in range(4):
        added=0
        for a in range(0x03000000,IWCODE_END,4):
            if a in P.ins or a in P.lits or a in P.jt: continue
            w=struct.unpack_from('<I',iw,a&0x7fff)[0]
            if w==0: continue
            p=a-4
            if not (p<0x03000000 or p in P.lits or p in P.jt or (p in P.ins and term(P.ins[p])) or struct.unpack_from('<I',iw,p&0x7fff)[0]==0): continue
            Q=Prog(P.img); Q.stubs=P.stubs; Q.lits=set(P.lits); Q.run([(a,'A')])
            ok=len(Q.ins)>=1 and all(not (q.op=='dp' and q.rd==15 and q.opc not in(D.TST,D.TEQ,D.CMP,D.CMN)) or q.addr in Q.tables for q in Q.ins.values()) and all(q.op not in('msr','mrs','swp') for q in Q.ins.values())
            ok=ok and all(not(q.op=='mem' and q.rd==15 and q.ld) or q.addr in Q.tables for q in Q.ins.values())
            ok=ok and all(a2 not in P.ins for a2 in Q.ins if a2!=a and False)
            if ok:
                for k,v in Q.ins.items(): P.ins.setdefault(k,v)
                P.lits|=Q.lits; P.entries.add(a); P.targets|=Q.targets; P.entries|=Q.entries; P.callt|=Q.callt; P.indirect+=Q.indirect; P.jt|=Q.jt; P.tables.update(Q.tables)
                added+=1
        if not added: break
    for a_,(nm,sid) in P.stubs.items():
        md='T' if a_>>24==8 else 'A'
        P.ins.pop(a_,None); P.entries.add(a_)
        P.ins[a_]=D.I(addr=a_,size=2 if md=='T' else 4,mode=md,op='stub',imm=sid,raw=0)
    if verbose: print('discovered: rom/seeds %d insns, +orphans %d, total %d'%(n0,len(P.ins)-before,len(P.ins)))
    return P
