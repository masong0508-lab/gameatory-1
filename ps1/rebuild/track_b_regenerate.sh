#!/bin/bash
# Track B (full regeneration, DRAFT): rebuild every private input of the title-boot PS1 build from the player's own files, for the
# RAM/VRAM layout of PR #1 (head d02652a), and compare each result with the file that survived from the stage 7 pipeline.
#
#   usage:  ROM=/abs/payback.gba AMIGA=/abs/amiga/payback REPO=/abs/checkout SURV=/abs/inputs  track_b_regenerate.sh TREE [step ...]
#           TREE  = a directory made by `python3 ps1/tools/prepare.py --output TREE`
#           steps = b0 b1 b2 b3 b4 b5 b6 b7 b8 b9 b10 b11 b12 hashes (default: all, in this order; later steps need the earlier
#                   outputs; "hashes" compares TREE/out with private_inputs.sha256 and can run alone)
#   env:    ROM           the untouched 8 MiB Payback (Europe) cartridge image (required)
#           SURV          surviving files to compare with, used ONLY for comparisons (required; set it empty, SURV=, when there
#                         is no copy: "hashes" still compares with the list).  The directory of private_inputs.sha256 works;
#                         the complete out/ directory of the stage 7 pipeline also has pr/ and the two touched_f1*.pkl sets
#           AMIGA         the owner's Amiga Payback folder (with maps/) for b7 (required for b7 unless GBA and ELF are given)
#           GBA, ELF      an existing merged GBA build (cartridge + stuntfox-merge.elf) for b7; unset = build one in TREE/out/gba
#           REPO          checkout whose tools build the cartridge and decode Payback's maps (required for b7)
#           SEED_TOUCHED  VALIDATION ONLY: skip the two simulator runs of b9 and take their outputs from this directory
#           SIM_FRAMES    TEST ONLY: length of the b9 runs (default 1500; the level starts at frame 1103)
#           NAME          name of the final EXE/ISO (default payback_rc)
# Status of this draft: every step except the two 1500-frame simulator runs of b9 was executed in this environment (LLVM 18.1.3)
# and reproduced the surviving files byte for byte; b9 was only smoke-tested for 250 frames.  See REBUILD_PLAN.md.
# Everything written here derives from the player's ROM and Amiga files: it stays in TREE/out, never in the repository.
set -euo pipefail
: "${ROM:?set ROM to the untouched 8 MiB Payback (Europe) cartridge image (absolute path)}"
SURV=${SURV?set SURV to a copy of the private inputs listed in private_inputs.sha256, or to nothing (SURV=) to skip those comparisons}
TREE=${1:?give the prepared tree (python3 ps1/tools/prepare.py --output TREE)}; shift || true
STEPS=${*:-b0 b1 b2 b3 b4 b5 b6 b7 b8 b9 b10 b11 b12 hashes}
NAME=${NAME:-payback_rc}
case " $STEPS " in *" b7 "*)
  : "${REPO:?set REPO to a checkout of the repository (b7 builds the cartridge with its stuntfox/build.py and decodes the maps with it)}"
  [ -n "${GBA:-}" ] || : "${AMIGA:?set AMIGA to the Amiga Payback folder (with maps/) for b7, or give GBA and ELF}" ;;
esac
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$ROM" ] || { echo "ROM: no such file: $ROM" >&2; exit 2; }
[ -z "$SURV" ] || [ -d "$SURV" ] || { echo "SURV: no such directory: $SURV" >&2; exit 2; }
abspath() { if [ -d "$1" ]; then (cd "$1" && pwd); else echo "$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; fi; }
ROM=$(abspath "$ROM"); [ -z "$SURV" ] || SURV=$(abspath "$SURV")      # relative paths keep working after the cd below
[ -z "${REPO:-}" ] || REPO=$(abspath "$REPO"); [ -z "${AMIGA:-}" ] || AMIGA=$(abspath "$AMIGA")
[ -z "${GBA:-}" ] || GBA=$(abspath "$GBA"); [ -z "${ELF:-}" ] || ELF=$(abspath "$ELF")
[ -z "${SEED_TOUCHED:-}" ] || SEED_TOUCHED=$(abspath "$SEED_TOUCHED")
FRAMES=${SIM_FRAMES:-1500}           # GBA frames per simulator run in b9; anything but 1500 is only for testing this script
GAP=0x8017a000,0x80200000            # = __ppu_start .. end of guest RAM windows; MUST equal the linker's first scratch byte (ps1_f.ld)
SIMCFL="-DCDSIM -DNOSF3 -DKPLAN -I../out/kp -DTESTFAST -DPRESENT_EVERY=2 -DCOLDGROUPS=512 -DPCACHE_ADDR=0x80600000 -DNSLOT=512"
T2M="--map P --pruned --tag P --resident out/s2/resident.pkl"
export ROM PYTHONDONTWRITEBYTECODE=1
[ -d "$TREE" ] || { echo "no such tree: $TREE (make it with: python3 ps1/tools/prepare.py --output $TREE)" >&2; exit 2; }
TREE="$(cd "$TREE" && pwd)"; cd "$TREE"
[ -f SOURCE_MANIFEST.json ] && [ -f t2m.py ] || { echo "not a prepared tree: $TREE" >&2; exit 2; }
mkdir -p out/s2 out/maps out/sf3m
step() { echo; echo "=== $(date +%H:%M:%S) $*"; }
took() { echo "    ($(( $(date +%s) - $1 )) s)"; }
# want FILE SHA256PREFIX: a deterministic generator must reproduce the surviving file exactly
want() { local got; got=$(sha256sum "$1" | cut -c1-${#2}); if [ "$got" = "$2" ]; then echo "    ok    $1  sha256 $2"; else echo "    FAIL  $1  sha256 $got..., expected $2" >&2; exit 3; fi; }
# same NEW SURVIVING LABEL: report only (simulator-derived files may legitimately differ; judge with the notes in REBUILD_PLAN.md)
same() { if [ -z "$SURV" ] || [ ! -f "$2" ]; then echo "    ?     $3: no surviving file to compare"; elif cmp -s "$1" "$2"; then echo "    SAME  $3 ($(sha256sum "$1" | cut -c1-16))"; else echo "    DIFF  $3 (new $(sha256sum "$1" | cut -c1-16), surviving $(sha256sum "$2" | cut -c1-16))"; fi; }
# nogap PRDIR: no cold span of a simulator translation may overlap the reserved range (PPU/veneer scratch, draw ring, guest RAM)
nogap() { python3 -B - "$1" <<'P'
import struct, sys
d = open(sys.argv[1] + '/coldtab_P.bin', 'rb').read(); n = struct.unpack_from('<I', d, 0)[0]
bad = [r for r in (struct.unpack_from('<4I', d, 4 + 16 * i) for i in range(n)) if r[3] > 0x8017a000 and r[2] < 0x80200000]
print('    %s: %d rows, %d spans inside 0x8017a000..0x80200000' % (sys.argv[1], n, len(bad)))
sys.exit(1 if bad else 0)
P
}
# sameset NEW SURVIVING LABEL: compare two pickled sets/dicts
sameset() { python3 -B - "$1" "$2" "$3" "$SURV" <<'P'
import os, pickle, sys
a = pickle.load(open(sys.argv[1], 'rb'))
if not sys.argv[4] or not os.path.exists(sys.argv[2]): print('    ?     %s: %d entries, no surviving file to compare' % (sys.argv[3], len(a))); sys.exit(0)
b = pickle.load(open(sys.argv[2], 'rb'))
if a == b: print('    SAME  %s: %d entries' % (sys.argv[3], len(a)))
else:
    ka, kb = set(a), set(b)
    print('    DIFF  %s: new %d, surviving %d, only new %d, only surviving %d' % (sys.argv[3], len(ka), len(kb), len(ka - kb), len(kb - ka)))
P
}

b0() { step "b0 tools, ARM SWI stub, pad plan"
  for t in python3 clang ld.lld llvm-objcopy llvm-nm genisoimage isoinfo; do command -v $t >/dev/null || { echo "missing tool: $t" >&2; exit 2; }; done
  python3 -c "import unicorn, numpy, PIL; print('    unicorn', unicorn.__version__)"
  [ "$(stat -c %s "$ROM")" = 8388608 ] || { echo "ROM is not 8 MiB" >&2; exit 2; }
  [ -f t/swi5.bin ] || { clang --target=armv4t-none-eabi -c t/swi5.s -o out/swi5.o && llvm-objcopy -O binary --only-section=.text out/swi5.o t/swi5.bin; }
  want t/swi5.bin 1ef66d21718d657c                  # 56 bytes; prune.py reads it at import time
  want out/kp/kplan.h 864279772c8ced4e              # checked-in pad plan with KPL, KPLB, KPLC, KPL2.  Do NOT run tools7/mkkplan.py the
}                                                   # stage 7 way (build_ps1.sh line 23): that drops KPLB/KPLC, which rt.c needs.

b1() { step "b1 IWRAM image at guest main (unicorn ARM, < 1 s)"
  python3 tools7/mkiw.py "$ROM" out/iw.bin
  want out/iw.bin 9b294845872f5d6d; }

b2() { step "b2 guest discovery (about 35 s)"; local t0=$(date +%s)
  python3 -I tools7/mkprog.py                       # expect: prog ok 220981
  want out/s2/prog_pr.pkl 98e3fb9586bd5291; took $t0; }

b3() { step "b3 ARM-side coverage, 3000 ticks (about 170 s)"; local t0=$(date +%s)
  python3 -I tools7/explore.py L3 3000 "[0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81]" "" > out/explore_L3.log 2>&1
  grep "^end tick" out/explore_L3.log               # expect: end tick 3000 swis 91 dl 6425 demand 0
  want out/cov_L3.pkl b422f240b76a9b5b; took $t0; }

b4() { step "b4 resident (hot) set and cold sets (3 s)"
  python3 mkresident.py out/s2/prog_pr.pkl out/s2/resident.pkl out/cov_L3.pkl | tail -n 1                 # touched 79 resident 85 insns 5980 of 220981
  python3 -I tools7/mkcoldall.py out/s2/prog_pr.pkl out/s2/resident.pkl out/cold_all.pkl                   # cold 2723 resident 85
  python3 mkcold.py out/s2/prog_pr.pkl out/s2/resident.pkl out/s2/cold.pkl 85000 out/cov_L3.pkl | tail -n 1   # cold 779 functions 84999 insns (budget 85000)
  want out/s2/resident.pkl 4cf2055930500efd; want out/s2/cold.pkl 572d2fb04a3a718c; want out/cold_all.pkl 32c72d8015355c1b; }

b5() { step "b5 boot translation and ARM-vs-MIPS lockstep -> boot.bin (about 20 s)"; local t0=$(date +%s)
  python3 t2m.py "$ROM" out/iw.bin out/pr_b $T2M --cache out/s2/prog_pr.pkl --cold out/s2/cold.pkl > out/pr_b.log 2>&1
  BOOT=out/boot.bin python3 lockstep2.py "$ROM" out/pr_b P 3 > out/boot.log 2>&1
  grep -E "^io writes|^snapshots compared" out/boot.log
  grep -q "io writes arm 3196 mips 3196 first mismatch None" out/boot.log
  grep -q "snapshots compared 3 word diffs {'EWRAM': 0, 'IWRAM': 0, 'PAL': 0, 'VRAM': 0, 'OAM': 0}" out/boot.log
  want out/boot.bin 1b264ca5a9cee352; took $t0; }   # 396,448 bytes; guest state only, no host layout inside (see plan, section 2)

b6() { step "b6 default-profile translation 'pr' and the empty ROM page list the simulator builds use (10 s)"
  python3 t2m.py "$ROM" out/iw.bin out/pr $T2M --cache out/s2/prog_pr.pkl --cold out/cold_all.pkl > out/pr.log 2>&1
  python3 -c "import pickle;pickle.dump([],open('out/pr/rompages_P.pkl','wb'))"
  same out/pr/payback_P.bin "$SURV/pr/payback_P.bin" "pr hot blob (85,184 bytes: --cache gives a 56 byte longer blob than the uncached runs below)"; }

b7() { step "b7 world pack SF3M.BIN from the merged GBA build (build about 90 s unless GBA/ELF are given; dump + pack about 20 s)"; local t0=$(date +%s)
  if [ -z "${GBA:-}" ]; then
    : "${AMIGA:?set AMIGA (the Amiga Payback folder with maps/), or give GBA and ELF}"
    rm -rf out/gba; mkdir -p out/gba                 # private copy of the tracked sources: the build never writes into the repository
    (cd "$REPO" && git ls-files -z | xargs -0 cp --parents -t "$TREE/out/gba")
    (cd out/gba/stuntfox && python3 build.py --merge --no-remixes --amiga "$AMIGA" -o "$TREE/out/built.gba" "$ROM" > "$TREE/out/build_gba.log" 2>&1)
    tail -n 1 out/build_gba.log | cut -c1-200        # expect world 0 {'boxes': 1983, 'lots': 1043, 'ramps': 436, 'items': 5950, ... 'ladders': 9 ...}
    GBA=$TREE/out/built.gba; ELF=$TREE/out/gba/stuntfox/build/merge/stuntfox-merge.elf
  fi
  for n in 0 1 2 3 4 5 6 7 8 9 10; do python3 -I tools7/dumpworld.py --rom "$GBA" --elf "$ELF" --map $n --out out/maps/world$n --repo "$REPO" > out/maps/d$n.log 2>&1; done
  python3 -I tools7/mkmaps7.py out/maps "$ELF" "$GBA" out/sf3m > out/mkmaps7.log
  tail -n 1 out/mkmaps7.log                          # expect: SF3M.BIN sectors 2855
  cp out/sf3m/SF3M.BIN out/SF3M.BIN
  want out/SF3M.BIN 87e0ea7eae36caaa; took $t0; }    # 5,847,040 bytes; map 1 is 239,616 bytes = the whole world window

b8() { step "b8 full-cold translation with the NEW gap and the first simulator build f1 (about 55 s)"; local t0=$(date +%s)
  # t/rebuild_f1.sh still says COLD_GAP=0x8017c000 at the PR head: do not use it unpatched (patch ps1-0001).
  COLD_GAP=$GAP python3 t2m.py "$ROM" out/iw.bin out/pr_f1 $T2M --cold out/cold_all.pkl > out/pr_f1.log 2>&1      # no --cache, as in the original chain
  cp out/pr/rompages_P.pkl out/pr_f1/
  nogap out/pr_f1
  want out/pr_f1/payback_P.bin 240345132e9f7ac5      # the hot blob all physical profiles share (85,128 bytes)
  PRD=pr_f1 NAME=f1 BLD=bld_f1 LD=ps1_f.ld NO_INTERP=1 CFL="$SIMCFL" sh ps1rt/build.sh 2>&1 | tail -n 1; took $t0; }

b9() { step "b9 the two discovery runs in the 16 MiB unicorn simulator (THE LONG PART: 1500 GBA frames each; 4 to 12 minutes each, run in parallel)"; local t0=$(date +%s)
  if [ -n "${SEED_TOUCHED:-}" ]; then
    echo "    VALIDATION MODE: simulator runs skipped, outputs taken from $SEED_TOUCHED"
    cp "$SEED_TOUCHED/touched_f1_base.pkl" out/touched_f1.pkl; cp "$SEED_TOUCHED/touched_f1.pkl.rompages" out/
    cp "$SEED_TOUCHED/touched_f1_boot.pkl" "$SEED_TOUCHED/touched_f1_boot.pkl.rompages" out/
  else
    rm -f out/touched_f1.pkl out/touched_f1.pkl.rompages out/touched_f1_boot.pkl out/touched_f1_boot.pkl.rompages
    TOUCH_FROM=level python3 t/snapdump.py f1 60 $FRAMES out/SNAPST_f1.BIN out/touched_f1.pkl > out/snapdump_f1.log 2>&1 &
    TOUCH_FROM=boot python3 t/snapdump.py f1 60 $FRAMES out/SNAPST_f1_boot.BIN out/touched_f1_boot.pkl > out/snapdump_f1_boot.log 2>&1 &
    wait
    # expect in both logs:  LEVEL clock runs at gba frame 1103 map 0 / SNAPSHOT at gba frame 1165.7 / done frame 1501.70...
    # expect: touched guest instr-labels 4949 (level run) and 9006 (boot run); no line starting with "exc"
    grep -hE "^LEVEL|^SNAPSHOT|^done frame|^touched|^exc" out/snapdump_f1.log out/snapdump_f1_boot.log | cut -c1-110 || true
    if grep -q "^exc" out/snapdump_f1.log out/snapdump_f1_boot.log; then echo "a simulator run stopped on a CPU exception: see out/snapdump_f1*.log" >&2; exit 4; fi
    [ -f out/touched_f1.pkl ] && [ -f out/touched_f1_boot.pkl ] || { echo "a simulator run produced no snapshot (level not reached?): see out/snapdump_f1*.log" >&2; exit 4; }
  fi
  sameset out/touched_f1.pkl "$SURV/touched_f1_base.pkl" "level-run guest labels (stage 7: 4949)"
  sameset out/touched_f1_boot.pkl "$SURV/touched_f1_boot.pkl" "boot-run guest labels (stage 7: 9006)"
  sameset out/touched_f1.pkl.rompages "$SURV/touched_f1.pkl.rompages" "ROM pages read from level start (stage 7: 58 pages)"
  sameset out/touched_f1_boot.pkl.rompages "$SURV/touched_f1_boot.pkl.rompages" "ROM pages read from power-on (stage 7: 99 pages)"; took $t0; }

b10() { step "b10 title-boot translation pr_lb: level tier, then the menus/boot tier (about 85 s)"; local t0=$(date +%s)
  # Exactly what stage 7 shipped: tier 0 = the level run WITHOUT tools7/extra_touch.txt (172 functions), tier 1 = the boot run (289).
  python3 t/mkrank.py out/touched_f1.pkl out/pr_f1 out/rank_S0.pkl          # expect: scenario cold functions 172 of 3299
  python3 t/mkrank.py out/touched_f1_boot.pkl out/pr_f1 out/rank_B.pkl      # expect: scenario cold functions 289 of 3299
  COLD_RANK=out/rank_S0.pkl COLD_RANK2=out/rank_B.pkl COLD_GAP=$GAP python3 t2m.py "$ROM" out/iw.bin out/pr_f2b $T2M --cold out/cold_all.pkl > out/pr_f2b.log 2>&1
  COLD_RANK=out/rank_S0.pkl COLD_RANK2=out/rank_B.pkl COLD_MAXRANK=1 COLD_ONLY=1 COLD_FULLTAB=out/pr_f2b/coldtab_P.bin python3 t2m.py "$ROM" out/iw.bin out/pr_lb $T2M --cold out/cold_all.pkl > out/pr_lb.log 2>&1
  nogap out/pr_f2b
  cmp out/pr_f2b/payback_P.bin out/pr_lb/payback_P.bin
  python3 -c "a=open('out/pr_f2b/cold_P.bin','rb').read(); b=open('out/pr_lb/cold_P.bin','rb').read(); assert a[:len(b)]==b, 'cold prefix differs'; print('    hot blob and %d byte cold prefix identical to the full-cold translation' % len(b))"
  for f in payback_P.bin cold_P.bin coldtab_P.bin payback_P.map meta_P.pkl; do same out/pr_lb/$f "$SURV/pr_lb/$f" pr_lb/$f; done; took $t0; }

b11() { step "b11 level-tier translation pr_l, which fixes the renderer's world window (about 85 s)"; local t0=$(date +%s)
  EXTRA_TOUCH=tools7/extra_touch.txt python3 t/mkrank.py out/touched_f1.pkl out/pr_f1 out/rank_S.pkl        # expect: scenario cold functions 216 of 3299
  COLD_RANK=out/rank_S.pkl COLD_GAP=$GAP python3 t2m.py "$ROM" out/iw.bin out/pr_f2 $T2M --cold out/cold_all.pkl > out/pr_f2.log 2>&1
  COLD_RANK=out/rank_S.pkl COLD_ONLY=1 COLD_FULLTAB=out/pr_f2/coldtab_P.bin python3 t2m.py "$ROM" out/iw.bin out/pr_l $T2M --cold out/cold_all.pkl > out/pr_l.log 2>&1
  nogap out/pr_f2
  cmp out/pr_f2/payback_P.bin out/pr_l/payback_P.bin
  python3 -c "a=open('out/pr_f2/cold_P.bin','rb').read(); b=open('out/pr_l/cold_P.bin','rb').read(); assert a[:len(b)]==b, 'cold prefix differs'; print('    hot blob and %d byte cold prefix identical to the full-cold translation' % len(b))"
  echo "    world window starts at $(python3 t/worldaddr.py pr_l) (must print 0x800cd800 or lower: the assert inside needs 239,616 bytes below 0x80108000)"
  for f in payback_P.bin cold_P.bin coldtab_P.bin payback_P.map meta_P.pkl; do same out/pr_l/$f "$SURV/pr_l/$f" pr_l/$f; done; took $t0; }
  # Not needed for the title-boot disc and therefore left out: t/f1_variants.sh (six perturbed runs, about 11 minutes; with
  # extra_touch.txt they add no function: the set stays at 216), the f2 simulator run and SNAPST.BIN (snapshot-resume discs only).

b12() { step "b12 the physical title-boot build: strict ps1.ld, two disc passes (10 s)"; local t0=$(date +%s)
  ROM="$ROM" bash tools12/build.sh "$NAME" ""        # runs t/mkrompages.py (56 preloaded ROM pages), t/worldaddr.py, ps1rt/build.sh
  sha256sum "out/$NAME.exe" "out/$NAME.iso"          # LLVM 18.1.3 + inputs identical to stage 7: EXE 55e534290e4356e6...; the ISO hash changes with every build (file dates)
  llvm-nm -n "out/bld_$NAME/payback.elf" | grep -E " (__bss_end|__ps1_pcache_start|__doll_start|__dlbss_end|__ppu_start|__veneer_scratch|__sfbss_end)$"
  took $t0; }

hashes() { step "hashes: every file of private_inputs.sha256 that exists under TREE/out, by full sha256 (report only)"
  # Expected DIFF: kp/kplan.h (the tree's own pad plan, see b0) and */rompages_P.pkl (written by the build).  The two
  # touched_*.rompages come from the simulator runs of b9: b9 compares them as sets, here they are compared byte for byte.
  local list="$HERE/private_inputs.sha256" n=0 h f
  [ -f "$list" ] || { echo "    $list not found: skipped"; return 0; }
  while read -r h f; do
    [ -f "out/$f" ] || continue; n=$((n + 1))
    if [ "$(sha256sum "out/$f" | cut -d' ' -f1)" = "$h" ]; then echo "    SAME  $f"; else echo "    DIFF  $f"; fi
  done < <(awk '!/^#/ && NF == 3 {print $1, $3}' "$list")
  echo "    $n listed files present under TREE/out"; }

for s in $STEPS; do case $s in b0|b1|b2|b3|b4|b5|b6|b7|b8|b9|b10|b11|b12|hashes) $s ;; *) echo "unknown step $s" >&2; exit 2 ;; esac; done
echo; echo "Track B steps done: $STEPS"
