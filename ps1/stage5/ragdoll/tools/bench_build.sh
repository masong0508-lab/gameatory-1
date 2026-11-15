#!/bin/sh
# usage: bench_build.sh LEVEL TAG [cflags] -> build/bench_L.elf (links at 0x100000 so a MIPS model can run it)
set -e; cd "$(dirname "$0")/.."; L=$1; shift; T=$1; shift; mkdir -p build
F="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic ${OPT:--O3 -mllvm -inline-threshold=500} -ffreestanding -G0 -mno-gpopt -fomit-frame-pointer -mno-check-zero-division -Wno-unused-command-line-argument -Wno-unused-function -Isrc -mllvm -disable-mips-delay-filler"
clang $F -DRP_LEVEL=$L "$@" -c src/bench.c -o build/bench_$T.o 2>&1 | grep -E 'error' || true
clang $F -c src/bstart.s -o build/bstart.o
printf 'ENTRY(_start)\nSECTIONS{ . = 0x100000; .text : { *(.text.start) *(.text*) *(.rodata*) *(.data*) *(.sdata*) } . = ALIGN(4); .bss : { *(.bss*) *(.sbss*) *(COMMON) } /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.gnu.attributes) *(.pdr) *(.comment) *(.mdebug*) } }\n' > build/bench.ld
ld.lld -T build/bench.ld build/bstart.o build/bench_$T.o -o build/bench_$T.elf
