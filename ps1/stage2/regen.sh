#!/bin/sh
# regenerate discovery for the current STUBS, resident set from coverage files (args), rebuild blob
cd "$(dirname "$0")"
python3 - <<'P'
import sys
sys.path.insert(0,'.')
import pickle,disc,prune
rom=open("../../../roms/Payback (Europe) (En,Fr,De,Es,It).gba",'rb').read(); iw=open('out/iw.bin','rb').read()
P=disc.discover(rom,iw,False,stubs=prune.stub_dict(),templates=[],extra=[(0x100,prune.SWI_STUB)],seeds=[(0x100,'A')])
P.img=None; pickle.dump(P,open('out/prog_pr.pkl','wb'))
P
python3 mkresident.py out/prog_pr.pkl out/resident.pkl "$@"
./rebuild.sh
