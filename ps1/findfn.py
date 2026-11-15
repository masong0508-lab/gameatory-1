import sys,json
sys.path.insert(0,'.')
from t2m import *
rom=open(sys.argv[1],'rb').read(); B=0x08000000
code=json.load(open('/tmp/code.json'))
starts=set()
for a,v in code.items():
    a=int(a)
    if v[0]=='T' and v[2]=='bl':
        ins=next(T.disasm(rom[a-B:a-B+4],a,1)); starts.add(ins.operands[0].imm)
res=[]
for s0 in sorted(starts):
    far=0; a=s0; L=[]; ok=True; back=False; mem=0
    while len(L)<60:
        if str(a) not in code: ok=False;break
        ins=next(T.disasm(rom[a-B:a-B+4],a,1)); L.append(ins); mn=ins.mnemonic
        if mn=='bl' or mn.startswith(('ldm','stm','svc','mrc','mcr')): ok=False;break
        if mn.startswith('b') and mn not in('bic','bics','bx') and ins.operands[0].type==ARM_OP_IMM and ins.operands[0].imm<a: back=True
        if mn.startswith('b') and mn not in('bic','bics','bx','bl') and ins.operands[0].type==ARM_OP_IMM: far=max(far,ins.operands[0].imm)
        if (mn=='bx' or (mn=='pop' and any(o.reg==ARM_REG_PC for o in ins.operands))) and far<=a: break
        a+=ins.size
    else: ok=False
    if ok and back and 12<=len(L)<=45 and True: res.append((s0,len(L)))
print(res[:15])
