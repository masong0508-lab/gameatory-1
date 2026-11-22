#!/bin/bash
# endsz.sh NAME "cflags": build with probe linker script, print __bss_end
set -euo pipefail
: "${ROM:?set ROM to your Payback Europe ROM}"
case "$ROM" in /*) ;; *) ROM="$PWD/$ROM" ;; esac
export ROM
cd "$(dirname "$0")"
LD=ps1_probe.ld bash tools12/build.sh "${1:?give an output name}" "${2:-}"
llvm-nm "out/bld_$1/payback.elf" | grep -E " __bss_end| __bss_start"
