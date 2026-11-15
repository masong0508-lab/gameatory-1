#!/bin/bash
set -e; cd /tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/v12/ps1/stage4; ROM="$ROM"
python3 t/mkrank.py out/touched_f1.pkl out/rank_S.pkl
# 3. F2 = same translation, scenario groups first
COLD_RANK=out/rank_S.pkl COLD_GAP=0x8017c000,0x80200000 python3 t2m.py "$ROM" out/iw.bin out/pr_f2 --map P --pruned --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr_f2.log 2>&1
cp out/pr/rompages_P.pkl out/pr_f2/
PRD=pr_f2 NAME=f2 BLD=bld_f2 LD=ps1_f.ld CFL="-DCDSIM -DNOSF3 -DKPLAN -I../out/kp -DTESTFAST -DPRESENT_EVERY=2 -DCOLDGROUPS=512 -DPCACHE_ADDR=0x80600000" sh ps1rt/build.sh
python3 t/snapdump.py f2 60 1500 out/SNAPST.BIN out/touched_f2.pkl
# 4. L = F2 with only the scenario groups emitted; check hot blob and cold prefix are byte-identical to F2
COLD_RANK=out/rank_S.pkl COLD_ONLY=1 python3 t2m.py "$ROM" out/iw.bin out/pr_l --map P --pruned --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr_l.log
cmp out/pr_f2/payback_P.bin out/pr_l/payback_P.bin
python3 - <<'P'
a=open('out/pr_f2/cold_P.bin','rb').read(); b=open('out/pr_l/cold_P.bin','rb').read(); n=len(b); assert a[:n]==b, 'cold prefix differs'; print('hot blob and %d KiB cold prefix identical'%(n//1024))
P
cp out/pr/rompages_P.pkl out/pr_l/
# 5. the PS1 disc: real hardware drivers, renderer on, resume from SNAPST.BIN
SNAPFILE=SNAPST.BIN PRD=pr_l NAME=s4 BLD=bld_l CFL="-DKPLAN -DSNAPRESUME -I../out/kp" sh ps1rt/build.sh
