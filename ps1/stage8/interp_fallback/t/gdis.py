import sys
from capstone import *
rom=open("/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/roms/Payback (Europe) (En,Fr,De,Es,It).gba",'rb').read()
a=int(sys.argv[1],16); n=int(sys.argv[2],16); thumb=(sys.argv[3]!='a') if len(sys.argv)>3 else True
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB if thumb else CS_MODE_ARM)
for i in md.disasm(rom[a-0x08000000:a-0x08000000+n],a): print('%08x %-8s %s'%(i.address,i.mnemonic,i.op_str))
