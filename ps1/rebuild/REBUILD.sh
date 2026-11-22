#!/bin/bash
# REBUILD.sh: build "Payback PS1 (original game) release candidate 4" = the PR #1 (head d02652a) prepared PS1 sources,
# strict physical-memory linker script ps1rt/ps1.ld, title-boot profile (pr_lb + world window of pr_l), data-only ISO.
# Written for that tree: the comments and the layout report assume its page list (56 pages from touched_f1_boot.pkl.rompages).
# The current release is built with track_a_reuse.sh (README.md); the stage 19 driver takes 62 pages from t/resident62.txt.
#
#   usage:  TREE=... ROM=... SURV=... OUTDIR=... REBUILD.sh
#   env:    TREE    the prepared tree (required); when it does not exist yet, it is made from PRWT
#           PRWT    a checkout of the repository whose ps1/tools/prepare.py makes TREE (required only when TREE does not exist)
#           ROM     the untouched 8 MiB Payback (Europe) cartridge image (required)
#           SURV    the directory of private inputs listed in private_inputs.sha256 (required)
#           OUTDIR  where the results are copied (required; outside the repository, the files derive from the ROM)
#           NAME    name of the results (default payback-rc4)
#           PATH=/usr/lib/llvm-19/bin:$PATH  builds with LLVM 19 instead of the default LLVM 18.1.3 (different EXE, see REBUILD_PLAN.md)
#           PADDBG=  (set, empty) drops -DPADDBG at PR head d02652a (the GS/GN state lines on the BIOS TTY that the pcsxr session
#                    scripts read); since stage 19 the release has none and PADDBG=FLAGS replaces the default
#           EXTRA="-D..."  extra C flags for rt.c / sf3.c (test variants only)
#
# Inputs (all private, derived from the player's own ROM; nothing here may be copied into the repository):
#   - the prepared tree TREE, made by `python3 ps1/tools/prepare.py --output TREE` in the PR worktree (149 files)
#   - the untouched 8 MiB Payback (Europe) ROM
#   - the surviving stage 7/18 translation outputs in SURV (proven valid UNCHANGED for the PR's RAM/VRAM layout:
#     REBUILD_PLAN.md section 2, verify_inputs.py, and byte-identical regeneration by track_b_regenerate.sh)
# Outputs: OUTDIR/NAME.exe, OUTDIR/NAME.iso, OUTDIR/NAME.files.txt (disc file listing), OUTDIR/NAME.SYSTEM.CNF.txt,
#          OUTDIR/NAME.layout.txt (memory layout numbers), OUTDIR/NAME.elf, OUTDIR/NAME.nm.txt, build step logs in TREE/out/bld_NAME/logs
set -euo pipefail
: "${TREE:?set TREE to the prepared tree (python3 ps1/tools/prepare.py --output TREE; made from PRWT when missing)}"
: "${ROM:?set ROM to the untouched 8 MiB Payback (Europe) cartridge image}"
: "${SURV:?set SURV to the directory of private inputs listed in private_inputs.sha256}"
: "${OUTDIR:?set OUTDIR to a directory outside the repository for the results}"
NAME=${NAME:-payback-rc4}
EXTRA=${EXTRA:-}
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$ROM" ] || { echo "ROM: no such file: $ROM" >&2; exit 2; }
[ -d "$SURV" ] || { echo "SURV: no such directory: $SURV" >&2; exit 2; }
ROM="$(cd "$(dirname "$ROM")" && pwd)/$(basename "$ROM")"; SURV="$(cd "$SURV" && pwd)"     # relative paths keep working after the cd
mkdir -p "$OUTDIR"; OUTDIR="$(cd "$OUTDIR" && pwd)"
export ROM PYTHONDONTWRITEBYTECODE=1
step() { echo; echo "=== $(date +%H:%M:%S) $*"; }
want() { local got; got=$(sha256sum "$1" | cut -c1-${#2}); if [ "$got" = "$2" ]; then echo "ok    $1  sha256 $2"; else echo "FAIL  $1  sha256 $got..., expected $2" >&2; exit 3; fi; }

step "R0 tools and tree"
for t in python3 clang ld.lld llvm-objcopy llvm-nm genisoimage isoinfo sha256sum; do command -v $t >/dev/null || { echo "missing tool: $t" >&2; exit 2; }; done
clang --version | head -n 1; ld.lld --version
[ "$(stat -c %s "$ROM")" = 8388608 ] || { echo "ROM is not 8 MiB" >&2; exit 2; }
if [ ! -d "$TREE" ]; then
  : "${PRWT:?TREE $TREE does not exist: set PRWT to a checkout of the repository to make it from (or run python3 ps1/tools/prepare.py --output TREE)}"
  mkdir -p "$(dirname "$TREE")"; TREE="$(cd "$(dirname "$TREE")" && pwd)/$(basename "$TREE")"
  (cd "$PRWT" && python3 ps1/tools/prepare.py --output "$TREE")
fi
cd "$TREE"
[ -f SOURCE_MANIFEST.json ] && [ -f tools12/build.sh ] && [ -f ps1rt/ps1.ld ] || { echo "not a prepared tree: $TREE" >&2; exit 2; }
echo "tree $TREE, manifest sha256 $(sha256sum SOURCE_MANIFEST.json | cut -c1-16)"

step "R1 stage the surviving private inputs (copies, 13 hashes checked)"
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

step "R2 files the prepared tree needs but neither contains nor checks"
# t/swi5.bin (56 byte ARM stub): prune.py reads it at import time; ps1rt/build.sh --check of PR head d02652a does not look for it
# (it does since commit d0d0010).
[ -f t/swi5.bin ] || { clang --target=armv4t-none-eabi -c t/swi5.s -o out/swi5.o && llvm-objcopy -O binary --only-section=.text out/swi5.o t/swi5.bin; }
want t/swi5.bin      1ef66d21718d657c
want out/kp/kplan.h  864279772c8ced4e              # the checked-in pad plan WITH KPLB/KPLC: do not regenerate it the stage 7 way

step "R3 layout proof of the staged inputs against this tree (verify_inputs.py of part 1)"
if [ -f "$HERE/verify_inputs.py" ]; then
  python3 -B "$HERE/verify_inputs.py" out . > out/verify_inputs.log 2>&1 || { tail -n 30 out/verify_inputs.log; exit 4; }
  tail -n 1 out/verify_inputs.log
else echo "verify_inputs.py not found next to this script: skipped"; fi

step "R4 preflight of the title-boot profile, then the build (strict ps1.ld, two disc passes that must agree)"
python3 t/mkrompages.py out/touched_f1_boot.pkl.rompages 56 out/pr_lb/coldtab_P.bin out/pr_lb/rompages_P.pkl > /dev/null
PRD=pr_lb ROM="$ROM" sh ps1rt/build.sh --check
# tools12/build.sh NAME EXTRA  =  NPAGES=56 PRD=pr_lb WORLDPRD=pr_l RPG=out/touched_f1_boot.pkl.rompages VOL=PAYBACK \
#                                 bash t/disc7.sh NAME "-DSF3_DEFER -DPADDBG EXTRA" 0   ->  ps1rt/build.sh with LD=ps1.ld (default)
ROM="$ROM" bash tools12/build.sh "$NAME" "$EXTRA"

step "R5 results"
mkdir -p "$OUTDIR"
cp "out/$NAME.exe" "$OUTDIR/$NAME.exe"; cp "out/$NAME.iso" "$OUTDIR/$NAME.iso"; cp "out/bld_$NAME/payback.elf" "$OUTDIR/$NAME.elf"
llvm-nm -n "out/bld_$NAME/payback.elf" > "$OUTDIR/$NAME.nm.txt"
ls -l "$OUTDIR/$NAME.exe" "$OUTDIR/$NAME.iso"
sha256sum "$OUTDIR/$NAME.exe" "$OUTDIR/$NAME.iso"
{ echo "# files on $NAME.iso (isoinfo -l; data track only, volume $(isoinfo -d -i "$OUTDIR/$NAME.iso" | sed -n 's/^Volume id: //p'), system id $(isoinfo -d -i "$OUTDIR/$NAME.iso" | sed -n 's/^System id: //p'))"
  isoinfo -l -i "$OUTDIR/$NAME.iso"
  echo "# name, first sector, bytes"
  isoinfo -l -i "$OUTDIR/$NAME.iso" | grep -E ";1" | awk '{print $NF, $(NF-2), $5}' | sed 's/\]//'
} > "$OUTDIR/$NAME.files.txt"
isoinfo -i "$OUTDIR/$NAME.iso" -x '/SYSTEM.CNF;1' > "$OUTDIR/$NAME.SYSTEM.CNF.txt"
echo "--- SYSTEM.CNF"; cat -A "$OUTDIR/$NAME.SYSTEM.CNF.txt"
echo "--- disc files (name, first sector, bytes)"; grep -A 20 "^# name" "$OUTDIR/$NAME.files.txt" | tail -n +2
python3 -B - "out/bld_$NAME/payback.elf" "out/bld_$NAME/logs" "$NAME" > "$OUTDIR/$NAME.layout.txt" <<'P'
import subprocess, sys, glob, re, os
nm = subprocess.run(['llvm-nm', '-n', sys.argv[1]], capture_output=True, text=True, check=True).stdout
s = {p[2]: int(p[0], 16) for p in (l.split() for l in nm.splitlines()) if len(p) == 3}
rt, doll0, doll1, ppu, sf1 = s['__bss_end'], s['__doll_start'], s['__dlbss_end'], s['__ppu_start'], s['__sfbss_end']
print('runtime  ends 0x%08x (limit 0x80028000): %6d of 98304 bytes, %5d free' % (rt, rt - 0x80010000, 0x80028000 - rt))
print('pagecache     0x%08x..0x%08x (%d pages of 4 KiB)' % (s['__ps1_pcache_start'], s['__ps1_pcache_end'], (s['__ps1_pcache_end'] - s['__ps1_pcache_start']) // 4096))
print('ragdoll       0x%08x..0x%08x: %6d bytes, %5d free below the PPU scratch at 0x%08x' % (doll0, doll1, doll1 - doll0, ppu - doll1, ppu))
print('ppu scratch   0x%08x, veneer scratch 0x%08x, draw ring 0x8017c000' % (ppu, s['__veneer_scratch']))
print('renderer      0x80199000..0x%08x (limit 0x801b0000): %6d of 94208 bytes, %5d free' % (sf1, sf1 - 0x80199000, 0x801b0000 - sf1))
assert rt <= 0x80028000 and doll1 <= ppu == 0x8017a000 and s['__veneer_scratch'] == 0x8017b000 and sf1 <= 0x801b0000
print('hot blob      0x80030000 (cold overlay home starts at COLD_HOST 0x%08x), cold table 0x%08x, resident ROM pages (rompack) 0x%08x..0x%08x' % (s['COLD_HOST'] and int.from_bytes(open(sys.argv[1].replace('payback.elf', 'payback.bin'), 'rb').read()[s['COLD_HOST'] - 0x80010000:s['COLD_HOST'] - 0x80010000 + 4], 'little'), s['coldtab'], s['rompack'], s['__ps1_pcache_start']))
P
# the compile flags the build really used (world window, page cache, cold sectors) are in the driver's environment: recompute them the way t/disc7.sh does
{ echo "world window  $(python3 t/worldaddr.py pr_l)..0x80108000 ($(python3 -c "print(0x80108000-int('$(python3 t/worldaddr.py pr_l)',16))") bytes; largest world 239616)"
  python3 t/mkrompages.py out/touched_f1_boot.pkl.rompages 56 out/pr_lb/coldtab_P.bin /dev/null 2>&1 >/dev/null | sed -e 's/^/rom pages     /' -e 's/ NSLOT=[0-9]*/; page cache = 8 slots of 4 KiB (NS=8 is fixed in t\/disc7.sh, the NSLOT this tool prints is not used)/'
  echo "cold overlay  COLD.BIN $(stat -c %s out/pr_lb/cold_P.bin) bytes = $(( ($(stat -c %s out/pr_lb/cold_P.bin) + 2047) / 2048 )) sectors, $(( ($(stat -c %s out/pr_lb/cold_P.bin) + 16383) / 16384 )) groups of 16 KiB"
  echo "compiler      $(clang --version | head -n 1)"
} >> "$OUTDIR/$NAME.layout.txt"
echo "--- layout"; cat "$OUTDIR/$NAME.layout.txt"
echo
echo "REBUILD done: $OUTDIR/$NAME.exe and $OUTDIR/$NAME.iso (data track only; CD audio and the licence area are added by tools7/mkdisc2.py, README.md)"
