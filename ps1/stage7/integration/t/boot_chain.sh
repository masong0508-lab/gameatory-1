#!/bin/bash
# title-boot translation: level groups first (rank_S), then the groups only the menus/boot run (rank_B), emitted as the L prefix (tiers 0 and 1)
set -e; cd "$(dirname "$0")/.."; ROM="${ROM:?set ROM}"
python3 t/mkrank.py out/touched_f1.pkl out/pr_f1 out/rank_S.pkl; python3 t/mkrank.py out/touched_f1_boot.pkl out/pr_f1 out/rank_B.pkl
COLD_RANK=out/rank_S.pkl COLD_RANK2=out/rank_B.pkl COLD_GAP=0x8017a000,0x80200000 python3 t2m.py "$ROM" out/iw.bin out/pr_f2b --map P --pruned --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr_f2b.log 2>&1
cp out/pr/rompages_P.pkl out/pr_f2b/
COLD_RANK=out/rank_S.pkl COLD_RANK2=out/rank_B.pkl COLD_MAXRANK=1 COLD_ONLY=1 COLD_FULLTAB=out/pr_f2b/coldtab_P.bin python3 t2m.py "$ROM" out/iw.bin out/pr_lb --map P --pruned --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr_lb.log 2>&1
cmp out/pr_f2b/payback_P.bin out/pr_lb/payback_P.bin
python3 - <<'P'
a=open('out/pr_f2b/cold_P.bin','rb').read(); b=open('out/pr_lb/cold_P.bin','rb').read(); n=len(b); assert a[:n]==b,'cold prefix differs'; print('boot variant: hot blob and %d KiB cold prefix (level + menus) identical to the full-cold translation'%(n//1024))
P
cp out/pr/rompages_P.pkl out/pr_lb/
