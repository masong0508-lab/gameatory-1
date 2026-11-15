import sys,json,collections,struct
sys.path.insert(0,'.')
from t2m import *
rom=open(sys.argv[1],'rb').read(); B=0x08000000
code=json.load(open('/tmp/code.json'))
th=sorted(int(a) for a,v in code.items() if v[0]=='T')
# branch targets
targets=set()
dec={}
for a in th:
    ins=next(T.disasm(rom[a-B:a-B+4],a,1)); dec[a]=ins
    if ins.mnemonic.startswith('b') and ins.operands and ins.operands[0].type==ARM_OP_IMM and ins.mnemonic not in('bic','bics','bl'): targets.add(ins.operands[0].imm)
    if ins.mnemonic=='bl' and ins.operands: targets.add(ins.operands[0].imm)
tr=Tr(rom); hist=collections.Counter(); per=collections.Counter(); total=0
prev=None
for i,a in enumerate(th):
    ins=dec[a]
    if a in targets or (prev is not None and prev+dec[prev].size!=a): tr.known={}; tr.flag=None
    nxt=dec.get(a+ins.size)
    nb= nxt is not None and nxt.mnemonic.startswith('b') and nxt.mnemonic not in('bic','bics','bl','bx')
    n0=len(tr.out)
    try: tr.ins(ins,nb)
    except KeyError: tr.e(0x0d,0); tr.stats['unsupp:pc/hi-reg form']+=1; tr.stats['unsupp']+=1
    n=len(tr.out)-n0
    hist[min(n,6)]+=1; per[ins.mnemonic]+=n; total+=n; prev=a
N=len(th)
print("Thumb insns %d -> MIPS words %d (x%.2f), bytes %d KiB"%(N,total,total/N,total*4//1024))
print("1:1 %.1f%%  2:1 %.1f%%  3:1 %.1f%%  4:1 %.1f%%  5:1 %.1f%%  6+:1 %.1f%%  (0 words %.1f%%)"%tuple(100*hist[k]/N for k in (1,2,3,4,5,6,0))[:7] if False else "")
print("words per Thumb insn histogram:",{k:f"{100*hist[k]/N:.1f}%" for k in sorted(hist)})
s=tr.stats; print({k:v for k,v in s.items() if not k.startswith('unsupp:')})
print("unsupported mnemonics:",{k[7:]:v for k,v in s.items() if k.startswith('unsupp:')})
mem=s['mem_known']+s['mem_sp']+s['mem_dyn']
print("mem accesses (non-literal) %d: base const-known EWRAM/IWRAM %.0f%%, sp-relative %.0f%%, dynamic %.0f%%"%(mem,100*s['mem_known']/mem,100*s['mem_sp']/mem,100*s['mem_dyn']/mem))
print("MIPS words by Thumb mnemonic (top):",per.most_common(12))
