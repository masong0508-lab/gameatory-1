#!/usr/bin/env python3
"""Instruction-level differential fuzz: random ARM / exhaustive-ish Thumb instruction snippets run on unicorn-ARM (original) and
unicorn-MIPS (translated by t2m), comparing r0-r14, NZCV (read back through a synthetic MRS the translator must honour) and memory."""
import sys,random,struct,collections,time
sys.path.insert(0,'.')
import armdec as D
from armdec import *
import disc,t2m,mips
from unicorn import *
from unicorn.arm_const import *
from unicorn.mips_const import *
TB=0x08700000; SLOT=0x40; EW=0x02000000
GMs=t2m.GM
def used_regs(i):
    u=set()
    for f in('rd','rn','rm','rs','rdhi','shreg'):
        v=getattr(i,f,None)
        if v is not None: u.add(v)
    if i.op in('ldm',): u|={r for r in range(16) if i.regs>>r&1}|{i.rn}
    return u
class Bench:
    def __init__(s,cfg,K):
        s.cfg=cfg; s.K=K
    def build(s,snips):
        """snips: list of (mode, bytes). returns program & translation"""
        rom=bytearray(0x800000); 
        s.slots=[]
        img_extra=bytearray(SLOT*len(snips))
        for n,(mode,code,litwords) in enumerate(snips):
            o=n*SLOT
            img_extra[o:o+len(code)]=code
            tsz=2 if mode=='T' else 4
            ph=o+len(code)
            # placeholder (nop) and bx lr
            if mode=='T':
                img_extra[ph:ph+2]=struct.pack('<H',0x46c0); img_extra[ph+2:ph+4]=struct.pack('<H',0x4770)
            else:
                img_extra[ph:ph+4]=struct.pack('<I',0xe1a00000); img_extra[ph+4:ph+8]=struct.pack('<I',0xe12fff1e)
            for k,w in enumerate(litwords): img_extra[o+0x20+4*k:o+0x24+4*k]=struct.pack('<I',w)
            s.slots.append((TB+o,mode,ph+TB,ph+TB+tsz))
        s.extra=bytes(img_extra)
        img=disc.Img(bytes(0x1000),bytes(0x8000),[(TB,s.extra)])
        P=disc.Prog(img)
        seeds=[(a,m) for a,m,_,_ in s.slots]
        P.run(seeds)
        for a,m,ph,bx in s.slots:
            P.entries.add(a)
            sz=2 if m=='T' else 4
            P.ins[ph]=I(addr=ph,size=sz,mode=m,op='mrs',rd=None,psr=0)
        s.P=P
        return P
class Result: pass
def run_arm(u,slot,mode,regs,mem,until,fl=0):
    u.reg_write(UC_ARM_REG_CPSR,0x1f|(0x20 if mode=='T' else 0)|(fl<<28))
    for k in range(13): u.reg_write(UC_ARM_REG_R0+k,regs[k])
    u.reg_write(UC_ARM_REG_SP,regs[13]); u.reg_write(UC_ARM_REG_LR,regs[14])
    u.mem_write(EW,mem)
    u.emu_start(slot|(1 if mode=='T' else 0),until)
    r=[u.reg_read(UC_ARM_REG_R0+k) for k in range(13)]+[u.reg_read(UC_ARM_REG_SP),u.reg_read(UC_ARM_REG_LR)]
    cp=u.reg_read(UC_ARM_REG_CPSR)
    return r,cp>>28,bytes(u.mem_read(EW,len(mem)))+bytes(u.mem_read(0x03007e00,0x200))
def main(nthumb=0,narm=3000,seed=1,mode='B'):
    random.seed(seed)
    cfg=t2m.Cfg(mode)
    BUF=0x2800
    ua=Uc(UC_ARCH_ARM,UC_MODE_ARM); ua.mem_map(0x08000000,0x800000,UC_PROT_ALL); ua.mem_map(EW,0x40000); ua.mem_map(0x03000000,0x8000)
    def host(v):
        h=cfg.host(v); return v if h is None else h
    def rnd32():
        t=random.random()
        if t<0.25: return random.randrange(0,16)
        if t<0.4: return random.choice([0,1,0x7fffffff,0x80000000,0xffffffff,0xfffffffe,0x80000001,0xff,0x100,0xffff,0x10000])
        if t<0.55: return random.randrange(0,0x100000000)&random.choice([0xff,0xffff,0xffffffff])
        return random.randrange(0,0x100000000)
    def filt_mem(i):
        if i.op=='swp': return True
        if i.rn==15: return True
        if i.rm is not None:
            if i.sh!=LSL: return False
            if i.shamt>4: return False
        else:
            if i.imm>0x500: return False
            if i.sz==4 and i.imm%4: return False
            if i.sz==2 and i.imm%2: return False
        return True
    stats=collections.Counter(); fails=[]
    def gen_arm():
        while True:
            w=random.randrange(0,1<<32)
            if random.random()<0.55: w=(w&0x0fffffff)|(14<<28)
            else: w=(w&0x0fffffff)|(random.randrange(0,14)<<28)
            cl=(w>>25)&7
            if cl in(0,1,2,3,4):
                pass
            else: continue
            if cl==4:
                # ldm/stm: keep list small, base not pc
                w=(w&0xfff0ffff)|(random.randrange(0,13)<<16); 
                rl=w&0xffff
                w=(w&0xffff0000)|(rl&0x1fff if random.random()<.8 else rl)
            i=D.arm(w,TB)
            if i.op in('undef','msr','mrs','swi','b','bl','bx'): continue
            if i.op=='dp' and i.rd==15 and i.opc not in(TST,TEQ,CMP,CMN): continue
            if i.op=='mem' and i.rd==15: continue
            if i.op=='ldm' and (i.regs>>15)&1: continue
            if i.op=='mem' and (i.rn==15 and i.rm is not None): continue
            if i.op=='mem' and i.rn==15 and (not i.ld or not i.pre or i.wb): continue
            if i.op=='mem' and i.rn==15 and not (i.up and 0x18<=i.imm<=0x34 and i.imm%4==0): continue
            if i.op in('mul','mull','swp') and 15 in used_regs(i): continue
            if i.op=='mul' and i.rd==i.rm: continue   # ARM: unpredictable
            if i.op=='mull' and (i.rd==i.rdhi or i.rd==i.rm or i.rdhi==i.rm): continue
            if i.op=='swp' and False: continue
            if i.op=='ldm' and i.rn==15: continue
            if i.op=='dp' and i.mode=='A' and (i.rn==15 or i.rm==15 or i.shreg==15) and i.shreg is not None: continue
            if i.op=='mem' and i.wb and i.rd==i.rn and i.ld: continue
            if i.op=='mem' and (not i.pre) and i.rd==i.rn: continue
            if i.op=='ldm' and i.wb and (i.regs>>i.rn)&1 and i.ld: continue
            if i.op=='ldm' and (i.regs>>i.rn)&1 and i.wb and not i.ld: continue   # base-in-list stm: unpredictable ordering
            if i.op=='mem' and i.rm is not None and i.rm==i.rn and (i.wb or not i.pre): continue
            if i.op=='mem' and i.rm is not None and i.rm==i.rd and (i.wb or not i.pre): continue
            if i.op=='swp' and i.rm==i.rd and False: continue
            if i.op=='dp' and i.opc in(TST,TEQ,CMP,CMN) and not i.s: continue
            if i.op=='ldm' and i.s: continue
            if i.op in('mem','swp') and not filt_mem(i): continue
            if i.op in('mem','swp') and i.rm==15: continue
            return w,i
    def gen_thumb():
        while True:
            h=random.randrange(1,65536)
            top=h>>13
            if top==7: continue
            if top==6 and (h>>12)&1: continue   # b cond / swi
            if (h>>11)==0x1c: continue
            i=D.thumb(h,TB)
            if i.op in('undef','b','bl','bx','swi'): continue
            if i.op=='dp' and i.rd==15 and i.opc not in(TST,TEQ,CMP,CMN): continue
            if i.op=='dp' and i.rn==15 and i.opc==MOV: pass
            if i.op=='ldm' and (i.regs>>15)&1: continue
            if i.op=='ldm' and i.rn==13 and False: continue
            if i.op=='mem' and i.rd==15: continue
            if i.op=='mem' and i.rn==15 and not (0x1c<=i.imm<=0x38): continue
            if i.op=='ldm' and i.wb and i.rn<8 and (i.regs>>i.rn)&1: continue
            if i.op=='mul' and False: continue
            if i.op in('mem','swp') and not filt_mem(i): continue
            return h,i
    N=narm+nthumb; B=Bench(cfg,0)
    K=200
    done=0; t0=time.time()
    um=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
    while done<N:
        snips=[]; info=[]
        for n in range(min(K,N-done)):
            if done+n<narm:
                w,i=gen_arm(); code=struct.pack('<I',w); mode='A'
            else:
                h,i=gen_thumb(); code=struct.pack('<H',h)+(b'\0\0' if False else b''); mode='T'
            lits=[random.choice([rnd32(),0x02000000+random.randrange(0,0x800)&~3,0x03000000+random.randrange(0,0x400)&~3]) for _ in range(8)]
            snips.append((mode,code,lits)); info.append(i)
        P=B.build(snips)
        T=t2m.Tr(P,cfg,False); T.run(); words,lab=T.finish()
        blob=b''.join(struct.pack('<I',w) for w in words)
        # fresh unicorn-mips for blob
        um=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
        sz=(len(blob)+0xfff)&~0xfff
        um.mem_map(cfg.BASE&0x1fffffff,sz); um.mem_write(cfg.BASE&0x1fffffff,blob)
        um.mem_map(0x08000000,0x800000,UC_PROT_READ|UC_PROT_WRITE); um.mem_write(TB,B.extra)
        for n_,b,s_ in((1,cfg.host(0x02000000),0x40000),(2,cfg.host(0x03000000),0x8000)):
            um.mem_map(b&0x1fffffff if b>=0x80000000 else b,s_)
        ua.mem_write(TB,B.extra)
        for n,(slot,mode,ph,bx) in enumerate(B.slots):
            i=info[n]
            regs=[rnd32() for _ in range(15)]
            if i.op in('mem','swp','ldm'):
                if i.rn!=15:
                    regs[i.rn]=(0x03007e00+0x100+4*random.randrange(0,16)) if i.rn==13 else EW+0x1000+4*random.randrange(0,256)
                if i.op=='mem' and i.rm is not None:
                    regs[i.rm]=4*random.randrange(0,32) if i.rm!=i.rn else regs[i.rm]
                    if i.rm==i.rn: continue
                if i.op=='swp': regs[i.rm]=rnd32()
            if not (i.op in('mem','swp','ldm') and i.rn==13): regs[13]=rnd32()
            if i.op in('mem','swp','ldm') and i.rn!=13 and False: pass
            if i.op=='mem' and i.rd==13 and i.ld==0: pass
            mem=bytearray(random.randrange(256) if random.random()<0.5 else 0 for _ in range(BUF))
            for o in range(0,BUF,4):
                if random.random()<0.0: struct.pack_into('<I',mem,o,EW+random.randrange(0,BUF)&~3)
            # ensure the IWRAM stack area has content too
            stk=bytes(random.randrange(256) for _ in range(0x200))
            ua.mem_write(0x03007e00,stk)
            try:
                fl0=random.randrange(16); ra,fa,ma=run_arm(ua,slot,mode,regs,bytes(mem),ph,fl0)
            except UcError as e:
                stats['arm_fault']+=1; continue
            # MIPS
            um.reg_write(UC_MIPS_REG_PC,0)
            um.mem_write(cfg.host(EW)&0x1fffffff if cfg.host(EW)>=0x80000000 else cfg.host(EW),bytes(mem))
            hh=cfg.host(0x03007e00); um.mem_write(hh&0x1fffffff if hh>=0x80000000 else hh,stk)
            hm=[]
            for k in range(15):
                v=regs[k]; hv=cfg.host(v) if (EW<=v<=EW+0x40000 or 0x03000000<=v<=0x03008000) else None
                hm.append(hv if hv is not None else v)
            # initial host mem: pointer words in buffer are mapped
            mm=bytearray(mem)
            for o in range(0,BUF,4):
                v=struct.unpack_from('<I',mm,o)[0]
                if EW<=v<=EW+0x40000: struct.pack_into('<I',mm,o,cfg.host(v))
            um.mem_write(cfg.host(EW)&0x1fffffff if cfg.host(EW)>=0x80000000 else cfg.host(EW),bytes(mm))
            for k in range(15): um.reg_write(UC_MIPS_REG_0+t2m.GM[k],hm[k])
            for k,bt in zip(range(4,8),(3,2,1,0)): um.reg_write(UC_MIPS_REG_0+k,(fl0>>bt)&1)
            um.reg_write(UC_MIPS_REG_0+31,0x81ff0000 if k else 0) if False else None
            entry=lab[('g',slot)]; endl=lab[('g',bx)]
            try:
                um.emu_start(entry,endl)
            except UcError as e:
                stats['mips_fault']+=1; fails.append(('fault',str(e),i,regs)); 
                if len(fails)<3: print('MIPS FAULT',e,i)
                continue
            rm=[um.reg_read(UC_MIPS_REG_0+t2m.GM[k]) for k in range(15)]
            # flags via the synthetic mrs: the translator wrote them into guest reg 'rd'? mrs rd=None -> use $2
            # run mrs: IR rd None -> GM[None] fails; handled by T? (see below)
            stats['ran']+=1
            def unm(v):
                for g,n_,hb in cfg.reg:
                    if hb-0x100000<=v<=hb+n_+0x100000: return (g+v-hb)&0xffffffff
                return v
            def same(a,b):
                if a==b: return True
                for g,n_,hb in cfg.reg:
                    if g-0x100000<=a<=g+n_+0x100000 and ((hb+a-g)&0xffffffff)==b: return True
                return False
            rmn=rm
            bad=[k for k in range(15) if not same(ra[k],rm[k])]
            mem_m=bytes(um.mem_read(cfg.host(EW)&0x1fffffff if cfg.host(EW)>=0x80000000 else cfg.host(EW),BUF))
            hh=cfg.host(0x03007e00); mem_m+=bytes(um.mem_read(hh&0x1fffffff if hh>=0x80000000 else hh,0x200))
            wm=struct.unpack('<%dI'%((BUF+0x200)//4),mem_m)
            wa=struct.unpack('<%dI'%((BUF+0x200)//4),ma)
            memdiff=[(k*4,hex(a),hex(b)) for k,(a,b) in enumerate(zip(wa,wm)) if not same(a,b)]; memok=not memdiff
            # flags: the translator's mrs wrote flags into $v0 (reg 2) for the synthetic probe
            fm=um.reg_read(UC_MIPS_REG_0+26)>>28
            flagok=(fm==fa) or (i.op=='dp' and not i.s and i.cond==14) or not (i.s or i.cond!=14 or i.op in('dp','mul','mull'))
            if bad or not memok or (fm!=fa and (i.s)):
                stats['mismatch']+=1
                stats['mm:'+i.op]+=1
                if len(fails)<12: fails.append((snips[n][1].hex(),snips[n][0],i.op,bad,memdiff[:3],fm,fa,fl0,[hex(r) for r in regs[:15]],[hex(r) for r in ra],[hex(r) for r in rmn]))
        done+=len(snips)
    print('ran',stats['ran'],'mismatch',stats['mismatch'],dict(stats),'%.1fs'%(time.time()-t0))
    for f in fails[:12]: print(f)
    return stats
if __name__=='__main__':
    main(int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3]),sys.argv[4] if len(sys.argv)>4 else 'B')
