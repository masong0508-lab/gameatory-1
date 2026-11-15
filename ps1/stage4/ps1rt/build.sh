#!/bin/sh
# usage: [NAME=x] [AUTO=1] [CFL=..] build.sh   (from stage3/ps1rt) -> ../out/$NAME.exe/.iso   stage 2 runtime + stage 2b renderer, one disc
# needs out/boot.bin out/pr/* out/SF3W.BIN out/SF3A.BIN (tools/mksf3.py) ; ROM stays local
set -e; cd "$(dirname "$0")"
ROM="../../../../roms/Payback (Europe) (En,Fr,De,Es,It).gba"
PRD=${PRD:-pr}; NAME=${NAME:-s3}; BLD=${BLD:-bld}; BOOT=${BOOT:-boot.bin}; AUTO=${AUTO:-0}
mkdir -p ../out/$BLD
F="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic -O2 -Wno-unused-command-line-argument -ffreestanding -G0 -mno-gpopt -mllvm -disable-mips-delay-filler"
[ "$AUTO" = 1 ] && F="-DAUTOKEYS $F"
[ "$DEMO" = 1 ] && F="-DSF3_DEMO $F"
[ "$SNAP" = 1 ] && F="-DSF3_SNAP $F" && export NSNAP=${NSNAP:-14}
SFF="-DSF_NOLIBC --target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic -O2 -ffreestanding -G0 -mno-gpopt -fomit-frame-pointer -mno-check-zero-division -Wno-unused-command-line-argument -Wno-unused-function -I../sf -mllvm -disable-mips-delay-filler $CFL"
mkexe(){
  python3 ../mkps1.py "$ROM" ../out/$PRD P ../out/$BOOT ../out/$PRD/rompages_P.pkl ../out/$BLD >/dev/null
  clang $F $CFL -c rt.c -o ../out/$BLD/rt.o 2>&1 | grep -E 'error' || true
  clang $F -c crt0.s -o ../out/$BLD/crt0.o 2>&1 | grep error || true
  clang $F -c ../out/$BLD/syms.c -o ../out/$BLD/syms.o
  clang $F -c ../out/$BLD/blobs.s -o ../out/$BLD/blobs.o
  clang $SFF -c ../sf/sf3.c -o ../out/$BLD/sf3.o 2>&1 | grep -E 'error' -A3 || true
  llvm-objcopy --prefix-alloc-sections=.sf ../out/$BLD/sf3.o
  clang $F -I../out -c ../sf/sfdata.s -o ../out/$BLD/sfdata.o
  ld.lld -T ${LD:-ps1.ld} ../out/$BLD/crt0.o ../out/$BLD/rt.o ../out/$BLD/syms.o ../out/$BLD/blobs.o ../out/$BLD/sf3.o ../out/$BLD/sfdata.o -o ../out/$BLD/payback.elf
  llvm-objcopy -O binary ../out/$BLD/payback.elf ../out/$BLD/payback.bin
  python3 - ../out/$BLD ../out/$NAME.exe <<'P'
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
  cp ../out/SF3W.BIN ../out/SF3A.BIN ../out/iso_$NAME/
  [ -f ../out/${SNAPFILE:-NONE} ] && cp ../out/$SNAPFILE ../out/iso_$NAME/SNAPST.BIN || true
  [ "$SNAP" = 1 ] && cp ../out/SNAP.BIN ../out/iso_$NAME/ || true
  printf 'BOOT = cdrom:\\PSX.EXE;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFF00\r\n' > ../out/iso_$NAME/SYSTEM.CNF
  genisoimage -quiet -V PAYBACKSF3 -sysid PLAYSTATION -o ../out/$NAME.iso ../out/iso_$NAME
}
lbas(){ isoinfo -l -i ../out/$NAME.iso | python3 -c "
import sys,re,os
d={}
for l in sys.stdin:
    m=re.search(r'\[\s*(\d+)\s+\d+\]\s+(\S+)',l)
    if m: d[m.group(2).split(';')[0]]=int(m.group(1))
cp=0
if os.path.exists('../out/$PRD/cold_P.bin'): cp=(os.path.getsize('../out/$PRD/cold_P.bin')+4095)//4096
print('%d,%d,%d,%d,%d,%d,%d'%(d['ROM.BIN'],d.get('COLD.BIN',0),cp,d['SF3W.BIN'],d['SF3A.BIN'],d.get('SNAP.BIN',0),d.get('SNAPST.BIN',0)))"; }
unset LBAS; mkexe; mkiso; L=$(lbas)
export LBAS=$L; mkexe; mkiso; L2=$(lbas)
[ "$L" = "$L2" ] || { echo "LBA moved $L -> $L2"; exit 1; }
echo "disc LBAs rom,cold,coldpages,sf3w,sf3a = $L"
