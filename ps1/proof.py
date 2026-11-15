#!/usr/bin/env python3
"""Proof: translate two real Payback Thumb functions (strlen @0x08077d34, strcmp-like @0x08077d78) from the user's ROM to MIPS-I,
run the original Thumb on unicorn-ARM and the translation on unicorn-MIPS32LE (R3000 integer subset, no load-delay reliance),
compare results and the byte image of RAM on random inputs."""
import sys,random,struct
sys.path.insert(0,'.')
from t2m import *
from unicorn import *
from unicorn.arm_const import *
from unicorn.mips_const import *
rom=open(sys.argv[1],'rb').read(); B=0x08000000
def translate(start,end):
    tr=Tr(rom); tr.retregs=set(); tr.saved_lr=True
    insns=[]; a=start
    while a<end:
        i=next(T.disasm(rom[a-B:a-B+4],a,1)); insns.append(i); a+=i.size
    tg={int(i.operands[0].imm) for i in insns if i.mnemonic.startswith('b') and i.mnemonic not in('bic','bics','bl','bx')}
    for k,i in enumerate(insns):
        if i.address in tg: tr.known={}; tr.flag=None
        tr.map[i.address]=len(tr.out)
        nxt=insns[k+1] if k+1<len(insns) else None
        nb=nxt is not None and nxt.mnemonic.startswith('b') and nxt.mnemonic not in('bic','bics','bl','bx')
        tr.ins(i,nb)
    out=tr.out
    for idx,t in tr.fix:
        off=tr.map[t]-(idx+1); out[idx]=(out[idx]&0xffff0000)|(off&0xffff)
    assert tr.stats['unsupp']==0, tr.stats
    return out,len(insns),tr.stats
def run_arm(start,args,mem):
    u=Uc(UC_ARCH_ARM,UC_MODE_THUMB); u.mem_map(B,0x800000); u.mem_write(B,rom); u.mem_map(0x0a000000,0x1000)
    u.mem_map(0x02000000,0x40000); u.mem_map(0x03000000,0x8000); u.mem_write(0x02000000,mem)
    for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1),args): u.reg_write(r,v)
    u.reg_write(UC_ARM_REG_SP,0x03007f00); u.reg_write(UC_ARM_REG_LR,0x0a000001)
    cnt=[0]; u.hook_add(UC_HOOK_CODE,lambda *a:cnt.__setitem__(0,cnt[0]+1))
    u.emu_start(start|1,0x0a000000)
    return u.reg_read(UC_ARM_REG_R0),bytes(u.mem_read(0x02000000,0x40000)),cnt[0]
def run_mips(code,args,mem):
    u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
    CODE=0x80010000; u.mem_map(0x10000,0x10000); u.mem_map(0x100000,0x40000); u.mem_map(0x140000,0x8000)
    u.mem_write(0x10000,b''.join(struct.pack('<I',w) for w in code)+b'\0'*8)
    u.mem_write(0x100000,mem)
    for r,v in zip((16,17),args): u.reg_write(UC_MIPS_REG_0+r,v)   # r0,r1 -> $16,$17
    u.reg_write(UC_MIPS_REG_0+30,0x80147f00)
    SENT=CODE+0x8000
    u.reg_write(UC_MIPS_REG_0+28,SENT)
    cnt=[0]; u.hook_add(UC_HOOK_CODE,lambda *a:cnt.__setitem__(0,cnt[0]+1))
    u.emu_start(CODE,SENT)
    return u.reg_read(UC_MIPS_REG_0+16),bytes(u.mem_read(0x100000,0x40000)),cnt[0]
random.seed(7); ok=True
for name,start,end in (("strlen",0x08077d34,0x08077d50),("strcmp-like",0x08077d78,0x08077d94)):
    code,n,st=translate(start,end)
    print(f"{name} @{start:08x}: {n} Thumb insns -> {len(code)} MIPS words ({len(code)/n:.2f}x); stats {dict(st)}")
    sa=sm=0; N=300
    for t in range(N):
        mem=bytearray(0x40000)
        L=random.choice([0,1,2,5,17,40]); s1=bytes(random.randrange(1,256) for _ in range(L))+b'\0'
        s2=bytearray(s1)
        if random.random()<.6 and L: s2[random.randrange(L)]=random.randrange(1,256)
        mem[0x1000:0x1000+len(s1)]=s1; mem[0x2000:0x2000+len(s2)+1]=bytes(s2)+b'\0'
        args=(0x02001000,0x02002000)
        ra,ma,ca=run_arm(start,args,bytes(mem)); rm,mm,cm=run_mips(code,args,bytes(mem))
        if name=="strlen": exp=len(s1)-1
        if ra!=rm or ma!=mm: ok=False; print("MISMATCH",t,hex(ra),hex(rm)); break
        sa+=ca; sm+=cm
    else: print(f"  {N} random cases: results and RAM identical; avg executed ARM insns {sa/N:.1f}, MIPS insns {sm/N:.1f} (x{sm/sa:.2f})")
print("PASS" if ok else "FAIL")
