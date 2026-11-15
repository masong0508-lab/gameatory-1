#!/bin/sh
# usage: build_hwtest.sh  (from anywhere) -> ../out/hwtest.exe ; disc built by mkdisc.py (data ISO with PSX.EXE, optional CD-DA tracks)
set -e; cd "$(dirname "$0")"; mkdir -p ../out/hwt
F="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic -O2 -Wno-unused-command-line-argument -ffreestanding -G0 -mno-gpopt -mllvm -disable-mips-delay-filler"   # the clang MIPS-I branch-delay filler breaks load-delay slots (found with hwtest: -O2 corrupted the save bitmap)
clang $F -c hwtest.c -o ../out/hwt/hwtest.o 2>&1 | grep -E 'error|warning: (incompat|unused var)' || true
clang $F -c crt0.s -o ../out/hwt/crt0.o
ld.lld -T ps1.ld ../out/hwt/crt0.o ../out/hwt/hwtest.o -o ../out/hwt/hwtest.elf 2>&1 | head
llvm-objcopy -O binary ../out/hwt/hwtest.elf ../out/hwt/hwtest.bin
python3 - ../out/hwt/hwtest.bin ../out/hwtest.exe <<'P'
import struct,sys
d=open(sys.argv[1],'rb').read(); d+=b'\0'*((-len(d))%2048)
h=bytearray(0x800); h[0:8]=b'PS-X EXE'
struct.pack_into('<IIIIIIIIIIII',h,0x10,0x80010000,0,0x80010000,len(d),0,0,0,0,0x801fd000,0,0,0)
open(sys.argv[2],'wb').write(bytes(h)+d); print('exe',len(h)+len(d))
P
