#!/bin/sh
# usage: build.sh TAG [cflags]  -> out/sf2b_TAG.iso   (run from stage2b/)
set -e; cd "$(dirname "$0")"; T=$1; shift; O=build/sf2b_$T; mkdir -p build
F="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic ${OPT:--O3 -mllvm -inline-threshold=500} -ffreestanding -G0 -mno-gpopt -fomit-frame-pointer -mno-check-zero-division -Wno-unused-command-line-argument -Wno-unused-function -Isrc -mllvm -disable-mips-delay-filler"
clang $F "$@" -c src/sf.c -o $O.o 2>&1 | grep -v 'MIPS-I support is experimental' | grep -E 'error|warning|note' | head -30 && true
clang $F -c src/crt0.s -o build/crt0_$T.o 2>&1 | grep error || true
clang $F -c src/data.s -o build/data_$T.o 2>&1 | grep error || true
ld.lld -T src/ps1.ld build/crt0_$T.o $O.o build/data_$T.o -o $O.elf
llvm-objcopy -O binary $O.elf $O.bin
python3 - $O <<'P'
import struct,sys
o=sys.argv[1]; d=open(o+'.bin','rb').read(); d+=b'\0'*((-len(d))%2048)
h=bytearray(0x800); h[0:8]=b'PS-X EXE'
struct.pack_into('<IIIIIIIIIIII',h,0x10,0x80010000,0,0x80010000,len(d),0,0,0,0,0x801fff00,0,0,0)
open(o+'.exe','wb').write(bytes(h)+d)
P
rm -rf $O.d; mkdir $O.d; cp $O.exe $O.d/SF2B.EXE
printf 'BOOT = cdrom:\\SF2B.EXE;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFF00\r\n' > $O.d/SYSTEM.CNF
genisoimage -quiet -V SF2B -sysid PLAYSTATION -o $O.iso $O.d
cp ps1test/gpuPeopsMesaGL.cfg build/ 2>/dev/null || true
ls -l $O.exe | awk '{print $5, $9}'
