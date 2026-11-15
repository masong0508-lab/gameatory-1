#!/bin/sh
# usage: hwbuild_opt.sh src.c optflags outname
cd /tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/v12/ps1/stage2/ps1rt
F="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic $2 -ffreestanding -G0 -mno-gpopt -Wno-unused-command-line-argument"
clang $F -c $1 -o ../out/hwt/$3.o 2>&1 | grep error; ld.lld -T ps1.ld ../out/hwt/crt0.o ../out/hwt/$3.o -o ../out/hwt/$3.elf && llvm-objcopy -O binary ../out/hwt/$3.elf ../out/hwt/$3.bin && python3 - $3 <<'P'
import struct,sys
n=sys.argv[1]
d=open('../out/hwt/%s.bin'%n,'rb').read(); d+=b'\0'*((-len(d))%2048)
h=bytearray(0x800); h[0:8]=b'PS-X EXE'
struct.pack_into('<IIIIIIIIIIII',h,0x10,0x80010000,0,0x80010000,len(d),0,0,0,0,0x801fd000,0,0,0)
open('../out/hwt/%s.exe'%n,'wb').write(bytes(h)+d)
P
cd ../out && rm -rf dd_$3 && mkdir dd_$3 && cp hwt/$3.exe dd_$3/PSX.EXE && printf 'BOOT = cdrom:\\PSX.EXE;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFF00\r\n' > dd_$3/SYSTEM.CNF && genisoimage -quiet -V HWTEST -o $3.iso dd_$3
