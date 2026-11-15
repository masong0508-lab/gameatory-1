#!/bin/bash
# stage 8: unicorn-sim twin of the production disc (same translation pr_l, same runtime, interpreter fallback on): CDSIM drivers, no renderer (no GTE in unicorn), pad from the host (sim_keys).
# usage: simdisc.sh NAME "extra cflags"
set -e; cd "$(dirname "$0")/.."
NAME=$1; XF=$2; PRD=${PRD:-pr_l}; RPG=${RPG:-out/touched_f1.pkl.rompages}
FL=$(python3 t/mkrompages.py $RPG ${NPAGES:-72} out/$PRD/coldtab_P.bin out/$PRD/rompages_P.pkl)
PC=$(echo "$FL" | sed -n 's/.*PCACHE_ADDR=\(0x[0-9a-f]*\).*/\1/p'); NS=8
WORLD=$(python3 t/worldaddr.py ${WORLDPRD:-$PRD})
SECS=$(python3 -c "import os;print((os.path.getsize('out/$PRD/cold_P.bin')+2047)//2048)")
export SNAPFILE=SNAPST.BIN
PRD=$PRD NAME=$NAME BLD=bld_$NAME DOLLDEF=$(printf '0x%08x' $(( PC + NS*4096 ))) CFL="-DCDSIM -DNOSF3 -DSIMKEYS -DSNAPRESUME -DTESTFAST -DPRESENT_EVERY=2 -DPCACHE_ADDR=$PC -DNSLOT=$NS -DCOLD_SECS=$SECS -DSF_WORLD_ADDR=${WORLD}u -DSF_WORLD_LO=${WORLD}u $XF" sh ps1rt/build.sh 2>&1 | grep -v "experimental"
