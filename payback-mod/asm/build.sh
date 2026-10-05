#!/bin/sh
# Rebuilds paybackmod/editor.bin and editor.json from hook.s and editor.c (needs clang and ld.lld).
set -e
cd "$(dirname "$0")"
T=$(mktemp -d)
clang --target=armv4t-none-eabi -mthumb -mcpu=arm7tdmi -Os -ffreestanding -fno-builtin -nostdlib -c editor.c -o $T/editor.o
clang --target=armv4t-none-eabi -c hook.s -o $T/hook.o
ld.lld -T link.ld $T/hook.o $T/editor.o -o $T/editor.elf 2>/dev/null
llvm-objcopy -O binary $T/editor.elf ../paybackmod/editor.bin
llvm-nm $T/editor.elf | python3 -c 'import sys, json; print(json.dumps({p[2]: int(p[0], 16) for p in (l.split() for l in sys.stdin) if p[2] in ("hook", "cols")}))' > ../paybackmod/editor.json
rm -r $T
