#!/bin/sh
# usage: eval.sh NAME cflags...  -> out_NAME.txt (instruction counts per 30 fps frame, windows) and q_NAME.txt (PC quality metrics)
cd "$(dirname "$0")/.."; N=$1; shift; . tools/cfgs.sh
sh tools/bench_build.sh 2 $N $(cfg c5) -DRP_FAST=1 "$@" >/dev/null 2>&1
PERFRAME=pf_$N.txt python3 -I tools/mipsprof.py $N 0 720 > out_$N.txt 2>&1
gcc -O2 -w -DRP_GTE_SIM $(cfg c5) -DRP_FAST=1 "$@" -Isrc tools/host_quality.c -o q_$N -lm && ./q_$N > q_$N.txt
echo "== $N $@"; python3 tools/win.py pf_$N.txt; head -1 q_$N.txt | cut -c1-200
