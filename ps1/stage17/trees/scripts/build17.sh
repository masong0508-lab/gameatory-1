#!/bin/bash
# build17.sh NAME SF3SRC : a tree-pose test disc for map 0 (title boot, scripted path, test unlock, fixed park-tree poses)
cd "$(dirname "$(readlink -f "$0")")"; . ./env.sh
X="-DSF3_DEFER -DPADDBG -DTESTUNLOCK=900 -DPRINT_EVERY_SF3=1 -DTREETEST=3"
SF3SRC=${2:-../sf/sf3.c} KPDIR=out/kp0 NPAGES=56 PRD=pr_lb WORLDPRD=pr_l RPG=out/touched_f1_boot.pkl.rompages VOL=PAYBACK bash t/disc7.sh $1 "$X" 0 2>&1 | tail -3
