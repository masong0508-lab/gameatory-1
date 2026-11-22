#!/bin/sh
# build.sh: builds openboot (own-work test boot ROM) and its variants into ./build.  No Sony code or data is used.
#   OUT=dir ./build.sh        default dir: build
set -e
cd "$(dirname "$0")"
OUT=${OUT:-build}
mkdir -p "$OUT"
CF="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -mllvm -disable-mips-delay-filler -fno-pic -G0 -mno-gpopt -ffreestanding -fno-builtin -mno-check-zero-division -Os -Wall -Wno-unused-command-line-argument"
clang $CF -c start.S -o "$OUT/start.o"
clang $CF -c resident.S -o "$OUT/resident.o"
clang $CF -c boot.c -o "$OUT/boot.o"
ld.lld -T ob.ld -Map="$OUT/openboot.map" -o "$OUT/openboot.elf" "$OUT/start.o" "$OUT/resident.o" "$OUT/boot.o"
llvm-objcopy -O binary "$OUT/openboot.elf" "$OUT/openboot.raw"
# variants = the behaviour flags word (ob.h):   plain: the quiet machine, everything defined by Exec and nothing else
python3 mkvariant.py "$OUT/openboot.raw" "$OUT/openboot.bin"         0x000
python3 mkvariant.py "$OUT/openboot.raw" "$OUT/openboot_abi.bin"     0x08b   # REGS|SMASH1|DIRTY|GARBREGS: every documented right of a kernel call used, RAM not zero
python3 mkvariant.py "$OUT/openboot.raw" "$OUT/openboot_irq.bin"     0x010   # KIRQ: interrupts on, kernel-style CD-ROM interrupt handler
python3 mkvariant.py "$OUT/openboot.raw" "$OUT/openboot_strict.bin"  0x100   # STRICT: unresolved exceptions stop the machine
python3 mkvariant.py "$OUT/openboot.raw" "$OUT/openboot_noflush.bin" 0x040   # NOFLUSH: FlushCache does nothing
python3 mkvariant.py "$OUT/openboot.raw" "$OUT/openboot_real.bin"    0x19b   # all of the above that a real kernel is documented to do
python3 mkvariant.py "$OUT/openboot.raw" "$OUT/openboot_kern.bin"    0x0bf   # REGS|SMASH1|SMASH4|DIRTY|KIRQ|KVBL|GARBREGS: kernel-like, but unresolved exceptions are still skipped
llvm-nm -n "$OUT/openboot.elf" > "$OUT/openboot.sym"
ls -l "$OUT"/*.bin
