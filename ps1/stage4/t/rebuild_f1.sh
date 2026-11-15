#!/bin/bash
# rebuild the full-cold sim build f1 (needs ROM env) and run the level-start sim; usage: rebuild_f1.sh
set -e; cd "$(dirname "$0")/.."; ROM="${ROM:?set ROM}"
[ -n "$SKIP_T2M" ] || COLD_GAP=0x8017c000,0x80200000 python3 t2m.py "$ROM" out/iw.bin out/pr_f1 --map P --pruned --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr_f1.log 2>&1
[ -n "$SKIP_T2M" ] || cp out/pr/rompages_P.pkl out/pr_f1/
PRD=pr_f1 NAME=f1 BLD=bld_f1 LD=ps1_f.ld CFL="-DCDSIM -DNOSF3 -DKPLAN -I../out/kp -DTESTFAST -DPRESENT_EVERY=2 -DCOLDGROUPS=512 -DPCACHE_ADDR=0x80600000" sh ps1rt/build.sh >/dev/null 2>&1
python3 t/snapdump.py f1 60 1500 out/SNAPST_f1.BIN out/touched_f1.pkl > out/snapdump_f1.log 2>&1
tail -8 out/snapdump_f1.log
