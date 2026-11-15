#!/bin/bash
set -e; cd "$(dirname "$0")/.."
python3 t/snapdump.py f2 60 1500 out/SNAPST.BIN out/touched_f2.pkl > out/snapdump_f2.log 2>&1
grep SNAPSHOT out/snapdump_f2.log
SNAPFILE=SNAPST.BIN PRD=pr_l NAME=s4 BLD=bld_l CFL="-DKPLAN -DSNAPRESUME -I../out/kp" sh ps1rt/build.sh 2>&1 | tail -2
