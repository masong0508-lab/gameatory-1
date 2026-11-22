#!/bin/bash
# stage 4 pipeline from the full-cold run on (needs ROM env, out/touched_f1.pkl from snapdump.py f1 ...): rank -> F2 -> snapshot -> L -> disc
set -e; cd "$(dirname "$0")/.."; ROM="${ROM:?set ROM}"
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
FL=$(python3 t/mkrompages.py out/touched_f1.pkl.rompages ${NPAGES:-72} out/pr_l/coldtab_P.bin out/pr_l/rompages_P.pkl)
SNAPFILE=SNAPST.BIN PRD=pr_l NAME=s4 BLD=bld_l CFL="-DKPLAN -DSNAPRESUME -I../out/kp $FL" sh ps1rt/build.sh 2>&1 | tail -2
