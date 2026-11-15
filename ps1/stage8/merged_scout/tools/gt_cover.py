import sys,os,pickle,bisect,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import elfsyms
elf=sys.argv[1]; P=pickle.load(open(sys.argv[2],'rb'))
fs,secs,ms=elfsyms.load(elf)
base,size=secs['.text']; m=sorted(ms['.text']); m.append((base+size,'e'))
kind=bytearray(size)   # 1 code 2 data
for (a,t),(b,_) in zip(m,m[1:]):
    for x in range(a,b): kind[x-base]=1 if t in 'at' else 2
cc=cd=0; insn_code=insn_data=0
cov=bytearray(size)
for a,i in P.ins.items():
    if base<=a<base+size:
        k=kind[a-base]
        if k==1: insn_code+=1
        else: insn_data+=1
        for j in range(i.size): cov[a-base+j]=1
code=sum(1 for k in kind if k==1); unc=sum(1 for x in range(size) if kind[x]==1 and not cov[x])
print('ground truth code bytes %d (Thumb+ARM, mapping syms); decoded %d insns inside them, %d insns decoded inside DATA (false positives); uncovered code bytes %d (%.1f%%)'%(code,insn_code,insn_data,unc,100.0*unc/code))
