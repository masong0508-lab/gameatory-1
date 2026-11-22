#!/bin/sh
# Build an assembled stage-16+ tree, not this historical overlay in isolation.
# ROM=/path/Payback.gba [NAME=s3] [BLD=bld] [CFL=...] sh ps1rt/build.sh [--check]
# Generated translation/maps belong under ../out; private ROM bytes stay there.
set -eu
set -f
CALLER_DIR=$(pwd)
: "${ROM:?set ROM to your Payback Europe ROM}"
case "$ROM" in /*) ;; *) ROM="$CALLER_DIR/$ROM" ;; esac
export ROM
cd "$(dirname "$0")"

PRD=${PRD:-pr}; NAME=${NAME:-s3}; BLD=${BLD:-bld}; BOOT=${BOOT:-boot.bin}
AUTO=${AUTO:-0}; DEMO=${DEMO:-0}; SNAP=${SNAP:-0}; CFL=${CFL:-}
NO_INTERP=${NO_INTERP:-}; IPEXT=${IPEXT:-}; DOLLDEF=${DOLLDEF:-}
SNAPFILE=${SNAPFILE:-}; SF3SRC=${SF3SRC:-../sf/sf3.c}; LINK_SCRIPT=${LD:-ps1.ld}
PROGPKL=${PROGPKL:-../out/s2/prog_pr.pkl}; export PROGPKL
PS1_CC=${PS1_CC:-clang}; PS1_LD=${PS1_LD:-ld.lld}; PS1_OBJCOPY=${PS1_OBJCOPY:-llvm-objcopy}
PS1_GENISOIMAGE=${PS1_GENISOIMAGE:-genisoimage}; PS1_ISOINFO=${PS1_ISOINFO:-isoinfo}

fail() { echo "PS1 build: $*" >&2; exit 1; }
for label in "$NAME" "$BLD" "$PRD"; do
    case "$label" in ''|.|..|*[!A-Za-z0-9_.-]*) fail "NAME, BLD and PRD must be simple output names" ;; esac
done
case "$BLD" in "$PRD"|s2|"$BOOT"|SF3M.BIN|"$NAME.exe"|"$NAME.iso") fail "BLD aliases a generated input or published output" ;; esac
case "${1:-}" in ''|--check) ;; *) fail "only --check is accepted; configure the build with environment variables" ;; esac

missing=0
for tool in python3 "$PS1_CC" "$PS1_LD" "$PS1_OBJCOPY" "$PS1_GENISOIMAGE" "$PS1_ISOINFO"; do
    if ! command -v "$tool" >/dev/null 2>&1; then echo "Missing tool: $tool" >&2; missing=1; fi
done
for file in "$ROM" ../mkps1.py rt.c crt0.s font.h hw_pad.h hw_card.h hw_cdda.h hw_radio.h hw_stub.h \
    ppu12.h "$LINK_SCRIPT" "$SF3SRC" ../sf/ps1.h ../sf/sfmem.h ../sf/sfdata.s ../tools/mips1_lint.py \
    ../rd/doll.c ../rd/ragdoll_ps1.c ../rd/ragdoll_ps1.h ../rd/gte_rp.h ../rd/ps1.h \
    "../out/$BOOT" ../out/SF3M.BIN "../out/$PRD/payback_P.map" "../out/$PRD/payback_P.bin" \
    "../out/$PRD/meta_P.pkl" "../out/$PRD/coldtab_P.bin" "../out/$PRD/rompages_P.pkl" "$PROGPKL"; do
    if [ ! -f "$file" ]; then echo "Missing input: $file" >&2; missing=1; fi
done
# mkps1.py imports prune.py, which reads this assembled ARM stub while packaging.
if [ ! -f ../t/swi5.bin ]; then
    echo 'Missing input: ../t/swi5.bin (assemble it from t/swi5.s; see README.md)' >&2
    missing=1
fi
if [ -z "$NO_INTERP" ]; then
    for file in ../interp/interp.c ../interp/interp.h ../interp/interp_asm.s interp_glue.h; do
        if [ ! -f "$file" ]; then echo "Missing input: $file" >&2; missing=1; fi
    done
fi
if [ "$SNAP" = 1 ] && [ ! -f ../out/SNAP.BIN ]; then echo 'Missing input: ../out/SNAP.BIN' >&2; missing=1; fi
if [ -n "$SNAPFILE" ] && [ ! -f "../out/$SNAPFILE" ]; then echo "Missing input: ../out/$SNAPFILE" >&2; missing=1; fi
[ "$missing" = 0 ] || fail 'assemble the source tree and generate its private translation/map inputs first; see ps1/STATUS.md'
python3 - "$ROM" <<'PY'
from pathlib import Path
import sys
size = Path(sys.argv[1]).stat().st_size
if size != 8 * 1024 * 1024:
    raise SystemExit(f'PS1 build: expected the 8 MiB Payback Europe ROM, got {size} bytes; '
                     'the current runtime has an 8 MiB page window and cannot build a merged Stunt Fox ROM')
PY
if [ "${1:-}" = --check ]; then echo 'PS1 build inputs and commands are present'; exit 0; fi

# A failed compile must never reach the linker with an old object, or replace
# an earlier successful EXE/ISO. Each invocation starts with an empty workspace.
mkdir -p ../out
WORK=$(mktemp -d "../out/.${NAME}.build.XXXXXX")
mkdir "$WORK/logs"
trap 'status=$?; if [ "$status" != 0 ]; then echo "PS1 build failed; previous outputs kept. Diagnostics: $WORK/logs" >&2; fi' EXIT
run() {
    label=$1; shift
    if "$@" > "$WORK/logs/$label.log" 2>&1; then
        return 0
    else
        status=$?
        cat "$WORK/logs/$label.log" >&2
        echo "PS1 build step failed: $label (exit $status)" >&2
        return "$status"
    fi
}

# -mno-check-zero-division: clang otherwise puts `teq divisor,$zero,7` behind every division; teq is MIPS II and raises a Reserved Instruction
# exception on the R3000A.  The divisors of the runtime and the interpreter cannot be zero (constants, a timer period >= 1, tested determinants).
F="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic -O2 -Wno-unused-command-line-argument -ffreestanding -G0 -mno-gpopt -mno-check-zero-division -mllvm -disable-mips-delay-filler"
[ "$AUTO" != 1 ] || F="-DAUTOKEYS $F"
[ "$DEMO" != 1 ] || F="-DSF3_DEMO $F"
if [ "$SNAP" = 1 ]; then F="-DSF3_SNAP $F"; export NSNAP=${NSNAP:-14}; fi
# The combined stage17 trees + stage18 models exceed the 92 KiB renderer
# region at -O2 with LLVM 19. Keep the linker's unchanged RAM boundary and
# compile for size. SFOPT is explicit so performance experiments are visible.
SFF="-DSF_NOLIBC --target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic ${SFOPT:--Os} -ffreestanding -G0 -mno-gpopt -fomit-frame-pointer -mno-check-zero-division -Wno-unused-command-line-argument -Wno-unused-function -I../sf -mllvm -disable-mips-delay-filler $CFL"
RDF="--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic -O3 -mllvm -inline-threshold=500 -ffreestanding -G0 -mno-gpopt -fomit-frame-pointer -mno-check-zero-division -Wno-unused-command-line-argument -Wno-unused-function -mllvm -disable-mips-delay-filler -DRP_LEVEL=2 -DRP_NS_BASE=3 -DRP_NS_DIV=10 -DRP_NSMAX=6 -DRP_HINGE_LAST=1 -DRP_FAST=1"

mkexe() {
    run "package-$PASS" python3 ../mkps1.py "$ROM" "../out/$PRD" P "../out/$BOOT" "../out/$PRD/rompages_P.pkl" "$WORK"
    if [ -z "$NO_INTERP" ]; then
        run "interp-$PASS" "$PS1_CC" $F -Os -I../interp -c ../interp/interp.c -o "$WORK/interp.o"
        run "interp-asm-$PASS" "$PS1_CC" $F -c ../interp/interp_asm.s -o "$WORK/interp_asm.o"
        IPO="$WORK/interp.o $WORK/interp_asm.o"; CFL_IP=-I../interp
    else IPO=; CFL_IP=-DNO_INTERP; fi
    run "runtime-$PASS" "$PS1_CC" $F $CFL $CFL_IP ${RTOPT:--Os} -c rt.c -o "$WORK/rt.o"
    run "startup-$PASS" "$PS1_CC" $F -c crt0.s -o "$WORK/crt0.o"
    run "symbols-$PASS" "$PS1_CC" $F -c "$WORK/syms.c" -o "$WORK/syms.o"
    run "blobs-$PASS" "$PS1_CC" $F -c "$WORK/blobs.s" -o "$WORK/blobs.o"
    run "renderer-$PASS" "$PS1_CC" $SFF -c "$SF3SRC" -o "$WORK/sf3.o"
    run "renderer-sections-$PASS" "$PS1_OBJCOPY" --prefix-alloc-sections=.sf "$WORK/sf3.o"
    run "ragdoll-$PASS" "$PS1_CC" $RDF -I../rd -c ../rd/doll.c -o "$WORK/doll.o"
    run "ragdoll-sections-$PASS" "$PS1_OBJCOPY" --prefix-alloc-sections=.dl "$WORK/doll.o"
    run "renderer-data-$PASS" "$PS1_CC" $F -I../out -c ../sf/sfdata.s -o "$WORK/sfdata.o"
    run "link-$PASS" "$PS1_LD" --defsym=ip_stacks=${IPSTK:-0x8002c000} $IPEXT -T "$LINK_SCRIPT" \
        "$WORK/crt0.o" "$WORK/rt.o" $IPO "$WORK/syms.o" "$WORK/blobs.o" "$WORK/sf3.o" "$WORK/doll.o" "$WORK/sfdata.o" \
        ${DOLLDEF:+--defsym=__doll_addr=$DOLLDEF} -o "$WORK/payback.elf"
    # every compiled function must consist of R3000A (MIPS I + COP0 + GTE) instructions only: the build fails otherwise
    run "mips1-lint-$PASS" python3 ../tools/mips1_lint.py "$WORK/payback.elf"
    run "binary-$PASS" "$PS1_OBJCOPY" -O binary "$WORK/payback.elf" "$WORK/payback.bin"
    run "exe-$PASS" python3 - "$WORK/payback.bin" "$WORK/$NAME.exe" <<'PY'
import struct, sys
from pathlib import Path
data = Path(sys.argv[1]).read_bytes()
if not data:
    raise SystemExit('linked PS1 binary is empty')
data += b'\0' * (-len(data) % 2048)
header = bytearray(2048)
header[:8] = b'PS-X EXE'
struct.pack_into('<IIIIIIIIIIII', header, 0x10, 0x80010000, 0, 0x80010000, len(data),
                 0, 0, 0, 0, 0x801fd000, 0, 0, 0)
Path(sys.argv[2]).write_bytes(header + data)
PY
}

mkiso() {
    ISO_DIR="$WORK/iso"
    mkdir -p "$ISO_DIR"
    cp "$WORK/$NAME.exe" "$ISO_DIR/PSX.EXE"
    cp "$ROM" "$ISO_DIR/ROM.BIN"
    if [ -f "../out/$PRD/cold_P.bin" ]; then cp "../out/$PRD/cold_P.bin" "$ISO_DIR/COLD.BIN"; fi
    cp ../out/SF3M.BIN "$ISO_DIR/SF3M.BIN"
    if [ -n "$SNAPFILE" ]; then cp "../out/$SNAPFILE" "$ISO_DIR/SNAPST.BIN"; fi
    if [ "$SNAP" = 1 ]; then cp ../out/SNAP.BIN "$ISO_DIR/SNAP.BIN"; fi
    printf 'BOOT = cdrom:\\PSX.EXE;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFF00\r\n' > "$ISO_DIR/SYSTEM.CNF"
    run "iso-$PASS" "$PS1_GENISOIMAGE" -quiet -V "${VOL:-PAYBACKSF3}" -sysid PLAYSTATION -o "$WORK/$NAME.iso" "$ISO_DIR"
}

lbas() {
    run "isoinfo-$PASS" "$PS1_ISOINFO" -l -i "$WORK/$NAME.iso" || return $?
    python3 - "$WORK/logs/isoinfo-$PASS.log" "../out/$PRD/cold_P.bin" "$SNAP" "$SNAPFILE" <<'PY'
import re, sys
from pathlib import Path
entries = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    match = re.search(r'\[\s*(\d+)\s+\d+\]\s+(\S+)', line)
    if match:
        entries[match[2].split(';')[0]] = int(match[1])
cold = Path(sys.argv[2])
required = ['ROM.BIN', 'SF3M.BIN', 'PSX.EXE']
if cold.exists(): required.append('COLD.BIN')
if sys.argv[3] == '1': required.append('SNAP.BIN')
if sys.argv[4]: required.append('SNAPST.BIN')
for name in required:
    if name not in entries:
        raise SystemExit('missing ISO directory entry: ' + name)
pages = (cold.stat().st_size + 4095) // 4096 if cold.exists() else 0
print(','.join(map(str, (entries['ROM.BIN'], entries.get('COLD.BIN', 0), pages,
                       entries['SF3M.BIN'], entries['SF3M.BIN'],
                       entries.get('SNAP.BIN', 0), entries.get('SNAPST.BIN', 0)))))
PY
}

unset LBAS
PASS=1; mkexe; mkiso; L=$(lbas)
export LBAS=$L
PASS=2; mkexe; mkiso; L2=$(lbas)
[ "$L" = "$L2" ] || fail "disc sector locations moved between passes: $L -> $L2"

# Publish only after every command and the two-pass sector check succeeded.
# Retain the earlier build directory under a unique backup for diagnostics.
if [ -e "../out/$BLD" ]; then
    BACKUP=$(mktemp -d "../out/.${BLD}.previous.XXXXXX")
    rmdir "$BACKUP"
    mv "../out/$BLD" "$BACKUP"
fi
mv "$WORK" "../out/$BLD"
WORK="../out/$BLD"
mv "$WORK/$NAME.exe" "../out/$NAME.exe"
mv "$WORK/$NAME.iso" "../out/$NAME.iso"
echo "Built ../out/$NAME.exe and ../out/$NAME.iso; disc LBAs: $L"
