#!/bin/bash
# Track A (fast path, validated): build the title-boot disc image of the ORIGINAL Payback PS1 port from the PR's prepared tree,
# re-using the surviving private inputs UNCHANGED.  They are proven compatible with the PR's RAM/VRAM layout (REBUILD_PLAN.md, section 2).
#
#   usage:  ROM=/abs/path/payback.gba SURV=/abs/path/inputs  track_a_reuse.sh TREE [NAME] ["extra cflags"]
#           TREE  = a directory made by `python3 ps1/tools/prepare.py --output TREE` (validated at PR head d02652a and at f1471a0)
#           NAME  = output name, default payback_rc  ->  TREE/out/NAME.exe, TREE/out/NAME.iso
#   env:    ROM   = the untouched 8 MiB Payback (Europe) cartridge image (required)
#           SURV  = the directory of private inputs listed in private_inputs.sha256 (required; nothing in the repository has them)
#           PADDBG  passed on to tools12/build.sh.  At PR head d02652a, PADDBG= (set empty) drops -DPADDBG, which v3 and the PR's
#                   private build had; since stage 19 the release has no PADDBG and PADDBG=FLAGS replaces the default
#           PATH  = put /usr/lib/llvm-19/bin first to build with LLVM 19 instead of the default LLVM 18
# Nothing is written outside TREE.  Everything staged or built here derives from the player's ROM: never copy it into the repository.
set -euo pipefail
: "${ROM:?set ROM to the untouched 8 MiB Payback (Europe) cartridge image (absolute path)}"
: "${SURV:?set SURV to the directory of private inputs listed in private_inputs.sha256 (boot.bin, SF3M.BIN, pr_l/, pr_lb/, s2/ ...)}"
TREE=${1:?give the prepared tree (python3 ps1/tools/prepare.py --output TREE)}; NAME=${2:-payback_rc}; EXTRA=${3:-}
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
[ -f "$ROM" ] || { echo "ROM: no such file: $ROM" >&2; exit 2; }
[ -d "$SURV" ] || { echo "SURV: no such directory: $SURV" >&2; exit 2; }
[ -d "$TREE" ] || { echo "no such tree: $TREE (make it with: python3 ps1/tools/prepare.py --output $TREE)" >&2; exit 2; }
ROM="$(cd "$(dirname "$ROM")" && pwd)/$(basename "$ROM")"; SURV="$(cd "$SURV" && pwd)"     # relative paths keep working after the cd
cd "$TREE"; TREE="$(pwd)"                              # absolute for accurate output paths and logs
[ -f SOURCE_MANIFEST.json ] && [ -f tools12/build.sh ] || { echo "not a prepared tree: $TREE" >&2; exit 2; }
[ "$(stat -c %s "$ROM")" = 8388608 ] || { echo "ROM is not 8 MiB" >&2; exit 2; }
step() { echo "=== $(date +%H:%M:%S) $*"; }
want() { local got; got=$(sha256sum "$1" | cut -c1-${#2}); if [ "$got" = "$2" ]; then echo "ok    $1  sha256 $2"; else echo "FAIL  $1  sha256 $got..., expected $2" >&2; exit 3; fi; }

step "A0 independently verify the owner's ROM and all 14 release inputs against full SHA-256 hashes"
python3 -B "$HERE/check_owner_inputs.py" "$HERE/private_inputs.sha256" "$SURV" --release --rom "$ROM"

step "A1 stage the surviving private inputs (copies)"
mkdir -p out/s2 out/pr_l out/pr_lb
cp "$SURV/boot.bin" "$SURV/SF3M.BIN" "$SURV/touched_f1_boot.pkl.rompages" out/
for f in payback_P.bin payback_P.map meta_P.pkl cold_P.bin coldtab_P.bin; do cp "$SURV/pr_l/$f" out/pr_l/; cp "$SURV/pr_lb/$f" out/pr_lb/; done
cp "$SURV/s2/prog_pr.pkl" out/s2/
rm -f out/pr_lb/rompages_P.pkl                       # written by t/mkrompages.py during the build (the copies lying around differ)
want out/boot.bin                      1b264ca5a9cee3525f8d335cb80a59ea
want out/SF3M.BIN                      87e0ea7eae36caaa88ae20177cff6bb4
want out/touched_f1_boot.pkl.rompages  23ca44c013506c60
want out/s2/prog_pr.pkl                98e3fb9586bd5291
want out/pr_lb/payback_P.bin           240345132e9f7ac5
want out/pr_lb/cold_P.bin              d67704aa9305116e
want out/pr_lb/coldtab_P.bin           346ca5137c748f86
want out/pr_lb/payback_P.map           3cd7f35ec9f26fa3
want out/pr_lb/meta_P.pkl              3146f25118ec438b
want out/pr_l/payback_P.bin            240345132e9f7ac5
want out/pr_l/cold_P.bin               1d98b84e6a3ed732
want out/pr_l/coldtab_P.bin            7a8a30942ae0d6ff
want out/pr_l/meta_P.pkl               0de2ea80495c0abe

step "A2 files the prepared tree needs but does not contain or check"
# t/swi5.bin: prune.py reads it at import time; ps1rt/build.sh --check does not look for it (the build then dies in package-1).
[ -f t/swi5.bin ] || { clang --target=armv4t-none-eabi -c t/swi5.s -o out/swi5.o && llvm-objcopy -O binary --only-section=.text out/swi5.o t/swi5.bin; }
want t/swi5.bin      1ef66d21718d657c
want out/kp/kplan.h  864279772c8ced4e              # the checked-in pad plan WITH KPLB/KPLC: do not regenerate it the stage 7 way

step "A3 layout proof of the staged inputs against this tree (verify_inputs.py)"
python3 -B "$HERE/verify_inputs.py" out . > out/verify_inputs.log 2>&1 || { tail -n 30 out/verify_inputs.log; exit 4; }
tail -n 1 out/verify_inputs.log

step "A4 preflight of the title-boot profile, then the build (two disc passes, strict ps1.ld)"
python3 t/mkrompages.py out/touched_f1_boot.pkl.rompages 56 out/pr_lb/coldtab_P.bin out/pr_lb/rompages_P.pkl > /dev/null
PRD=pr_lb ROM="$ROM" sh ps1rt/build.sh --check
ROM="$ROM" bash tools12/build.sh "$NAME" "$EXTRA"

step "A5 result"
ls -l "out/$NAME.exe" "out/$NAME.iso"
sha256sum "out/$NAME.exe" "out/$NAME.iso"
python3 -B - "out/bld_$NAME/payback.elf" <<'P'
import subprocess, sys
nm = subprocess.run(['llvm-nm', '-n', sys.argv[1]], capture_output=True, text=True, check=True).stdout
s = {p[2]: int(p[0], 16) for p in (l.split() for l in nm.splitlines()) if len(p) == 3}
rt, doll0, doll1, ppu, sf1 = s['__bss_end'], s['__doll_start'], s['__dlbss_end'], s['__ppu_start'], s['__sfbss_end']
print('runtime  ends 0x%08x: %6d of 98304 bytes, %5d free' % (rt, rt - 0x80010000, 0x80028000 - rt))
print('pagecache     0x%08x..0x%08x' % (s['__ps1_pcache_start'], s['__ps1_pcache_end']))
print('ragdoll       0x%08x..0x%08x: %6d bytes, %5d free below the PPU scratch at 0x%08x' % (doll0, doll1, doll1 - doll0, ppu - doll1, ppu))
print('renderer ends 0x%08x: %6d of 94208 bytes, %5d free' % (sf1, sf1 - 0x80199000, 0x801b0000 - sf1))
assert rt <= 0x80028000 and doll1 <= ppu == 0x8017a000 and s['__veneer_scratch'] == 0x8017b000 and sf1 <= 0x801b0000
P
isoinfo -l -i "out/$NAME.iso" | grep -E "COLD.BIN|PSX.EXE|ROM.BIN|SF3M.BIN|SYSTEM.CNF" | awk '{print "iso: " $NF, "sector", $(NF-2), "size", $5}' || true
echo "Track A done: $TREE/out/$NAME.exe and $TREE/out/$NAME.iso (data track only; CD audio and the licence area are added by tools7/mkdisc2.py, README.md)"

