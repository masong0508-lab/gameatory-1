import sys,struct,json,collections
from capstone import *
from capstone.arm import *
rom=open(sys.argv[1],'rb').read(); B=0x08000000
code=json.load(open('/tmp/code.json'))
mix=collections.Counter(v[2] for v in code.values())
tot=sum(mix.values())
print("Thumb mnemonic mix (top 28):")
print(", ".join(f"{k} {100*v/tot:.1f}%" for k,v in mix.most_common(28)))
# IWRAM blobs (ARM): linear decode
A=Cs(CS_ARCH_ARM,CS_MODE_ARM); A.detail=True
blobs=[(0x087d9bf4,0xc2c),(0x087da83c,0x087e077c-0x087da83c),(0x087da820,0x1c)]
cnt=collections.Counter(); n=0; bad=0; swi=collections.Counter()
for base,ln in blobs:
    o=base-B
    for off in range(0,ln,4):
        w=rom[o+off:o+off+4]; ins=next(A.disasm(w,base+off,1),None)
        if ins is None: bad+=1; continue
        n+=1; cnt[ins.mnemonic]+=1
        if ins.mnemonic in('swi','svc'): swi[ins.operands[0].imm if ins.operands else 0]+=1
print("IWRAM image: %d words, %d decode as ARM, %d undecodable(data); top:"%(sum(l//4 for _,l in blobs),n,bad), cnt.most_common(14), "swi",dict(swi))
# Thumb code (dis) in IWRAM image? count bx lr / push patterns not needed
