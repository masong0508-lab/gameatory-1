#!/bin/bash
# buildall.sh : the 13 test discs (title boot, scripted path to city K / story city, test unlock, spin sweep at the start pose)
cd "$(dirname "$(readlink -f "$0")")"; . ./env.sh
X="-DSF3_DEFER -DPADDBG -DTESTUNLOCK=900 -DPRINT_EVERY_SF3=1 -DSPINTEST=3"
for k in 0 1 2 3 4 5 6 7 8 9 10; do KPDIR=out/kp$k NPAGES=56 PRD=pr_lb WORLDPRD=pr_l RPG=out/touched_f1_boot.pkl.rompages VOL=PAYBACK bash t/disc7.sh ck$k "$X" 0 2>&1 | tail -1; done
for c in 0 2; do KPDIR=out/kps$c NPAGES=56 PRD=pr_lb WORLDPRD=pr_l RPG=out/touched_f1_boot.pkl.rompages VOL=PAYBACK bash t/disc7.sh cks$c "$X" 0 2>&1 | tail -1; done
echo BUILDALL-DONE
