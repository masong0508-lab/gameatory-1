#!/bin/bash
# endsz.sh NAME "cflags": build with probe linker script, print __bss_end
cd "$(dirname "$0")"; export ROM="/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/roms/Payback (Europe) (En,Fr,De,Es,It).gba"
LD=ps1_probe.ld bash tools12/build.sh "$1" "$2" >/dev/null 2>&1
llvm-nm out/bld_$1/payback.elf | grep -E " __bss_end| __bss_start"
