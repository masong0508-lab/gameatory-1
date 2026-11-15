#!/bin/sh
# usage: build.sh [stream]  (from stage2/ps1rt) -> ../out/$NAME.exe/.iso (PCSXR) and ../out/${NAME}_sim.exe (ps1sim, -DCDSIM).
# needs out/boot.bin out/pr/payback_P.* out/pr/rompages_P.pkl ; optional out/pr/cold_P.bin (overlay code, on disc as COLD.BIN)
set -e; cd "$(dirname "$0")"
ROM="../../../../roms/Payback (Europe) (En,Fr,De,Es,It).gba"
[ "$1" = stream ] && export STREAM=1
PRD=${PRD:-pr}; NAME=${NAME:-payback}; BLD=${BLD:-bld}; BOOT=${BOOT:-boot.bin}
mkdir -p ../out/$BLD ../out/${BLD}_sim
F="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic -O2 -Wno-unused-command-line-argument -ffreestanding -G0 -mno-gpopt -mllvm -disable-mips-delay-filler"   # the clang MIPS-I branch-delay filler breaks load-delay slots (found with hwtest: -O2 corrupted the save bitmap)
[ "$SCRIPT" = 1 ] && F="-DSCRIPTPAD $F"   # scripted keys instead of the real pad (regression / unattended demo discs)
mkexe(){ # $1 = bld dir, $2 = extra cflags, $3 = exe out
  python3 ../mkps1.py "$ROM" ../out/$PRD P ../out/$BOOT ../out/$PRD/rompages_P.pkl $1 >/dev/null
  clang $F $2 -c rt.c -o $1/rt.o 2>&1 | grep -E 'error' || true
  clang $F -c crt0.s -o $1/crt0.o 2>&1 | grep error || true
  clang $F -c $1/syms.c -o $1/syms.o
  clang $F -c $1/blobs.s -o $1/blobs.o
  ld.lld -T ps1.ld $1/crt0.o $1/rt.o $1/syms.o $1/blobs.o -o $1/payback.elf
  llvm-objcopy -O binary $1/payback.elf $1/payback.bin
  python3 - $1 $3 <<'P'
import struct,sys
d=open(sys.argv[1]+'/payback.bin','rb').read(); d+=b'\0'*((-len(d))%2048)
h=bytearray(0x800); h[0:8]=b'PS-X EXE'
struct.pack_into('<IIIIIIIIIIII',h,0x10,0x80010000,0,0x80010000,len(d),0,0,0,0,0x801fd000,0,0,0)
open(sys.argv[2],'wb').write(bytes(h)+d)
print('exe size',len(h)+len(d))
P
}
mkiso(){
  rm -rf ../out/iso_$NAME; mkdir ../out/iso_$NAME; cp ../out/$NAME.exe ../out/iso_$NAME/PSX.EXE; cp "$ROM" ../out/iso_$NAME/ROM.BIN
  [ -f ../out/$PRD/cold_P.bin ] && cp ../out/$PRD/cold_P.bin ../out/iso_$NAME/COLD.BIN
  printf 'BOOT = cdrom:\\PSX.EXE;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFF00\r\n' > ../out/iso_$NAME/SYSTEM.CNF
  genisoimage -quiet -V PAYBACKPS1 -sysid PLAYSTATION -o ../out/$NAME.iso ../out/iso_$NAME
}
lbas(){ isoinfo -l -i ../out/$NAME.iso | python3 -c "
import sys,re,os
d={}
for l in sys.stdin:
    m=re.search(r'\[\s*(\d+)\s+\d+\]\s+(\S+)',l)
    if m: d[m.group(2).split(';')[0]]=int(m.group(1))
cp=0
if os.path.exists('../out/$PRD/cold_P.bin'): cp=(os.path.getsize('../out/$PRD/cold_P.bin')+4095)//4096
print('%d,%d,%d'%(d['ROM.BIN'],d.get('COLD.BIN',0),cp))"; }
unset LBAS; mkexe ../out/$BLD "" ../out/$NAME.exe; mkiso; L=$(lbas)
export LBAS=$L; mkexe ../out/$BLD "" ../out/$NAME.exe; mkiso; L2=$(lbas)
[ "$L" = "$L2" ] || { echo "LBA moved $L -> $L2"; exit 1; }
echo "disc LBAs rom,cold,coldpages = $L"
mkexe ../out/${BLD}_sim "-DCDSIM" ../out/${NAME}_sim.exe >/dev/null
cp ../../hello/gpuPeopsMesaGL.cfg ../out/
ls -l ../out/$NAME.exe ../out/$NAME.iso
