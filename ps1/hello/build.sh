#!/bin/sh
# builds hello.exe (PS-EXE) with stock clang 18 + ld.lld, no SDK
set -e; cd "$(dirname "$0")"
F="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic -O2 -Wno-unused-command-line-argument"
clang $F -c main.c -o main.o 2>&1 | grep -E 'error' || true
clang $F -c crt0.s -o crt0.o 2>&1 | grep error || true
ld.lld -T ps1.ld crt0.o main.o -o hello.elf
llvm-objcopy -O binary hello.elf hello.bin
python3 - <<'P'
import struct
d=open('hello.bin','rb').read(); d+=b'\0'*((-len(d))%2048)
h=bytearray(0x800); h[0:8]=b'PS-X EXE'
struct.pack_into('<IIIIIIIIIIII',h,0x10,0x80010000,0,0x80010000,len(d),0,0,0,0,0x801fff00,0,0,0)
open('hello.exe','wb').write(bytes(h)+d)
P
ls -l hello.exe
