#!/bin/bash
# stage 4 pipeline (code only; needs the user's ROM at $ROM and stage2/stage3 intermediate files).  usage: mk_stage4.sh
set -e; cd "$(dirname "$0")/.."
ROM="${ROM:?set ROM}"
# 1. full-cold build F (sim only: every function translated, cold pool with a gap over the guest windows), pad plan compiled in
COLD_GAP=0x8017c000,0x80200000 python3 t2m.py "$ROM" out/iw.bin out/pr_f1 --map P --pruned --cache out/s2/prog_pr.pkl --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr_f1.log
cp out/pr/rompages_P.pkl out/pr_f1/
PRD=pr_f1 NAME=f1 BLD=bld_f1 LD=ps1_f.ld CFL="-DCDSIM -DNOSF3 -DKPLAN -I../out/kp -DTESTFAST -DPRESENT_EVERY=2 -DCOLDGROUPS=512 -DPCACHE_ADDR=0x80600000" sh ps1rt/build.sh
# 2. run the sim from power-on to the level and a few hundred frames on; record the guest functions executed after the snapshot point
python3 t/snapdump.py f1 60 1500 out/SNAPST_f1.BIN out/touched_f1.pkl
python3 t/mkrank.py out/touched_f1.pkl out/rank_S.pkl
# 3. F2 = same translation, scenario groups first
COLD_RANK=out/rank_S.pkl COLD_GAP=0x8017c000,0x80200000 python3 t2m.py "$ROM" out/iw.bin out/pr_f2 --map P --pruned --cache out/s2/prog_pr.pkl --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr_f2.log
cp out/pr/rompages_P.pkl out/pr_f2/
PRD=pr_f2 NAME=f2 BLD=bld_f2 LD=ps1_f.ld CFL="-DCDSIM -DNOSF3 -DKPLAN -I../out/kp -DTESTFAST -DPRESENT_EVERY=2 -DCOLDGROUPS=512 -DPCACHE_ADDR=0x80600000" sh ps1rt/build.sh
python3 t/snapdump.py f2 60 1500 out/SNAPST.BIN out/touched_f2.pkl
# 4. L = F2 with only the scenario groups emitted; check hot blob and cold prefix are byte-identical to F2
COLD_RANK=out/rank_S.pkl COLD_ONLY=1 python3 t2m.py "$ROM" out/iw.bin out/pr_l --map P --pruned --cache out/s2/prog_pr.pkl --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr_l.log
cmp out/pr_f2/payback_P.bin out/pr_l/payback_P.bin
python3 - <<'P'
a=open('out/pr_f2/cold_P.bin','rb').read(); b=open('out/pr_l/cold_P.bin','rb').read(); n=len(b); assert a[:n]==b, 'cold prefix differs'; print('hot blob and %d KiB cold prefix identical'%(n//1024))
P
cp out/pr/rompages_P.pkl out/pr_l/
# 5. the PS1 disc: real hardware drivers, renderer on, resume from SNAPST.BIN
SNAPFILE=SNAPST.BIN PRD=pr_l NAME=s4 BLD=bld_l CFL="-DKPLAN -DSNAPRESUME -I../out/kp" sh ps1rt/build.sh
