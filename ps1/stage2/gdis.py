import sys,struct
from capstone import *
rom=open('/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
iw=open('out/iw.bin','rb').read()
def get(a,n):
    if a>>24==8: return rom[a-0x08000000:a-0x08000000+n]
    return iw[a&0x7fff:(a&0x7fff)+n]
def dis(a,n,thumb):
    md=Cs(CS_ARCH_ARM,CS_MODE_THUMB if thumb else CS_MODE_ARM)
    for i in md.disasm(get(a,n),a): print('%08x  %s %s'%(i.address,i.mnemonic,i.op_str))
if __name__=='__main__': dis(int(sys.argv[1],16),int(sys.argv[2],0),sys.argv[3]=='t')
