#!/bin/bash
# stage 4 pipeline from the full-cold run on (needs ROM env, out/touched_f1.pkl from snapdump.py f1 ...): rank -> F2 -> snapshot -> L -> disc
# stage 19: every step's failure stops the script (pipefail; no output filter hides an exit status) and the last step builds the snapshot-resume
# TEST disc through t/disc7.sh, which derives the page cache, ragdoll, world and cold geometry exactly as every other disc build does.
set -euo pipefail; cd "$(dirname "$0")/.."; ROM="${ROM:?set ROM}"; export ROM
EXTRA_TOUCH=${EXTRA_TOUCH:-tools7/extra_touch.txt} python3 t/mkrank.py out/touched_f1.pkl out/pr_f1 out/rank_S.pkl
COLD_RANK=out/rank_S.pkl COLD_GAP=0x8017a000,0x80200000 python3 t2m.py "$ROM" out/iw.bin out/pr_f2 --map P --pruned --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr_f2.log 2>&1
cp out/pr/rompages_P.pkl out/pr_f2/
PRD=pr_f2 NAME=f2 BLD=bld_f2 LD=ps1_f.ld NO_INTERP=1 CFL="-DCDSIM -DNOSF3 -DKPLAN -I../out/kp -DTESTFAST -DPRESENT_EVERY=2 -DCOLDGROUPS=512 -DPCACHE_ADDR=0x80600000 -DNSLOT=512" sh ps1rt/build.sh
python3 t/snapdump.py f2 60 1200 out/SNAPST.BIN out/touched_f2.pkl > out/snapdump_f2.log 2>&1
grep SNAPSHOT out/snapdump_f2.log
COLD_RANK=out/rank_S.pkl COLD_ONLY=1 COLD_FULLTAB=out/pr_f2/coldtab_P.bin python3 t2m.py "$ROM" out/iw.bin out/pr_l --map P --pruned --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr_l.log 2>&1
cmp out/pr_f2/payback_P.bin out/pr_l/payback_P.bin
python3 - <<'P'
a=open('out/pr_f2/cold_P.bin','rb').read(); b=open('out/pr_l/cold_P.bin','rb').read(); n=len(b); assert a[:n]==b, 'cold prefix differs'; print('hot blob and %d KiB cold prefix identical'%(n//1024))
P
# 56 resident pages leave room for the 8-slot cache and the ragdoll below the PPU scratch (the old default of 72 does not fit: the link fails)
KPLAN=1 PRD=pr_l RPG=out/touched_f1.pkl.rompages NPAGES=${NPAGES:-56} bash t/disc7.sh s4 "" 1
