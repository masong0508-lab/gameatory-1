#!/bin/bash
# Milestone B stage B1: translate the merged Star-FlyBack GBA ROM (16 MiB, --merge --no-remixes --amiga) with the rc10 pipeline
# (t2m hot blob + cold groups + interpreter) into TREE/out, the inputs tools12/build_msb.sh needs.
#   usage: ROM=/abs/merged.gba ORIG=/abs/Payback.gba SEED=/abs/dir translate_msb.sh TREE
#   SEED holds the guest-address-only inputs re-used from the original game's pipeline (no host layout inside, no ROM bytes):
#     cov_L3.pkl (ARM coverage, explore.py), rank_S0.pkl / rank_B.pkl / rank_S.pkl (cold tiers from the original's simulator runs).
#   Payback's code sits at the same guest addresses in the merged ROM (441 patched halfwords), so these sets are valid hints; the mod's
#   own code (0x081b0000..0x082f6de8) is data for discovery (PB_DATA_SPANS) and runs in the interpreter, as does the overlay loader
#   0x08077508 (interp_glue.h ip_hle: it must switch the overlay hash slots).  Everything written derives from the player's ROM: never commit it.
set -euo pipefail
: "${ROM:?merged ROM}" "${ORIG:?original ROM}" "${SEED:?seed dir}"
TREE=$(cd "${1:?tree}" && pwd); cd "$TREE"
export PB_DATA_SPANS=081b0000-082f6de8,08077508-08077610 PRUNE_DROP=3 T2M_ROMPG_N=4096 PYTHONDONTWRITEBYTECODE=1 ROM
GAP=0x8017a000,0x80200000; T2M="--map P --pruned --tag P --resident out/s2/resident.pkl"
step() { echo "=== $(date +%H:%M:%S) $*"; }
[ "$(stat -c %s "$ROM")" = 16777216 ] || { echo "merged ROM must be 16 MiB (--no-remixes)" >&2; exit 2; }
mkdir -p out/s2
[ -f t/swi5.bin ] || { clang --target=armv4t-none-eabi -c t/swi5.s -o out/swi5.o && llvm-objcopy -O binary --only-section=.text out/swi5.o t/swi5.bin; }
step "b1 IWRAM image"; python3 tools7/mkiw.py "$ROM" out/iw.bin; python3 tools7/mkiw.py "$ORIG" out/iw_orig.bin
cmp out/iw.bin out/iw_orig.bin && echo "    IWRAM image at main identical to the original game's"
step "b2 discovery"; python3 tools7/mkprog.py
python3 - <<'P'
import pickle; P=pickle.load(open('out/s2/prog_pr.pkl','rb'))
n=sum(1 for a in P.ins if 0x081b0000<=a<0x082f6de8); m=sum(1 for a in P.ins if 0x08077508<=a<0x08077610)
print('    instructions inside the data spans: %d (must be 0), loader %d'%(n,m)); assert n==0 and m==0
print('    intro join 0x080234be translated:',0x080234be in P.ins and P.ins[0x080234be].op!='stub')
P
cp "$SEED/cov_L3.pkl" out/cov_L3.pkl
step "b4 resident and cold sets"
python3 mkresident.py out/s2/prog_pr.pkl out/s2/resident.pkl out/cov_L3.pkl | tail -n 1
python3 tools7/mkcoldall.py out/s2/prog_pr.pkl out/s2/resident.pkl out/cold_all.pkl
python3 mkcold.py out/s2/prog_pr.pkl out/s2/resident.pkl out/s2/cold.pkl 85000 out/cov_L3.pkl | tail -n 1
step "b5 boot translation and lockstep -> boot.bin"
python3 t2m.py "$ROM" out/iw.bin out/pr_b $T2M --cache out/s2/prog_pr.pkl --cold out/s2/cold.pkl > out/pr_b.log 2>&1
BOOT=out/boot.bin python3 lockstep2.py "$ROM" out/pr_b P 3 > out/boot.log 2>&1 || true
grep -E "^boot image|^io writes|^snapshots compared|^MIPS done|^ARM done" out/boot.log | cut -c1-200
[ -f out/boot.bin ] || { echo "no boot image" >&2; exit 4; }
cp "$SEED/rank_S0.pkl" "$SEED/rank_B.pkl" "$SEED/rank_S.pkl" out/
step "b10 title-boot translation pr_lb"
COLD_RANK=out/rank_S0.pkl COLD_RANK2=out/rank_B.pkl COLD_GAP=$GAP python3 t2m.py "$ROM" out/iw.bin out/pr_f2b $T2M --cold out/cold_all.pkl > out/pr_f2b.log 2>&1
COLD_RANK=out/rank_S0.pkl COLD_RANK2=out/rank_B.pkl COLD_MAXRANK=1 COLD_ONLY=1 COLD_FULLTAB=out/pr_f2b/coldtab_P.bin python3 t2m.py "$ROM" out/iw.bin out/pr_lb $T2M --cold out/cold_all.pkl > out/pr_lb.log 2>&1
cmp out/pr_f2b/payback_P.bin out/pr_lb/payback_P.bin
step "b11 level-tier translation pr_l"
# B1: the intro (0x080234be..) is translated now (prune id 3 dropped) and the hot blob is 10 KiB longer, so the level tier with the 44
# functions of tools7/extra_touch.txt (rank_S, 216) no longer fits below the world window (0x800d0000 > 0x800cd800); the tier of the base
# level run (rank_S0, 172) does (0x800cd800).  The 44 are interpreted in levels.  B2 lays the memory out again (PLAN.md 3.3).
COLD_RANK=out/rank_S0.pkl COLD_GAP=$GAP python3 t2m.py "$ROM" out/iw.bin out/pr_f2 $T2M --cold out/cold_all.pkl > out/pr_f2.log 2>&1
COLD_RANK=out/rank_S0.pkl COLD_ONLY=1 COLD_FULLTAB=out/pr_f2/coldtab_P.bin python3 t2m.py "$ROM" out/iw.bin out/pr_l $T2M --cold out/cold_all.pkl > out/pr_l.log 2>&1
cmp out/pr_f2/payback_P.bin out/pr_l/payback_P.bin
echo "    world window $(python3 t/worldaddr.py pr_l)"
for d in pr_lb pr_l; do echo "    $d: blob $(stat -c %s out/$d/payback_P.bin) cold $(stat -c %s out/$d/cold_P.bin) rows $(head -c4 out/$d/coldtab_P.bin | od -An -tu4)"; done
rm -rf out/pr_f2 out/pr_f2b out/pr_b
echo "translate_msb done"
