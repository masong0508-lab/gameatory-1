#!/bin/bash
cd "$(dirname "$(readlink -f "$0")")"
K=$1
TOUCH_FROM=level PERTURB_CYC=7001 nice -n 19 python3 t/snapdump.py f1k$K 60 1700 out/SNAPST_f1k$K.BIN out/touched_f1k$K.pkl > out/snapdump_f1k$K.log 2>&1
