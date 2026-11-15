#!/bin/bash
# stage 13 TEST-ONLY sim build (unicorn, real pad + memory card drivers over a modelled SIO0): mksim13.sh NAME "extra cflags"
set -e; cd "$(dirname "$0")/.."
NAME=$1; XF=$2
PRD=pr_f2 NAME=$NAME BLD=bld_$NAME LD=ps1_f.ld CFL="-DCDSIM -DSIMSIO -DNOSF3 -DTESTFAST -DCOLDGROUPS=512 -DPCACHE_ADDR=0x80600000 -I../out/kp $XF" sh ps1rt/build.sh 2>&1 | grep -v experimental
