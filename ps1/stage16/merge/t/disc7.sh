#!/bin/bash
# stage 7 disc build from the L translation (out/pr_l): usage disc7.sh NAME "extra cflags" [snap]   (snap=0 builds the title-boot variant without SNAPRESUME)
# memory map decisions made here: page cache NSLOT=8 (stage 4 had 40), the ragdoll code behind it, the renderer's world window right behind the cold prefix.
set -e; cd "$(dirname "$0")/.."
NAME=$1; XF=$2; SNAP=${3:-1}; PRD=${PRD:-pr_l}; RPG=${RPG:-out/touched_f1.pkl.rompages}
FL=$(python3 t/mkrompages.py $RPG ${NPAGES:-72} out/$PRD/coldtab_P.bin out/$PRD/rompages_P.pkl)
PC=$(echo "$FL" | sed -n 's/.*PCACHE_ADDR=\(0x[0-9a-f]*\).*/\1/p'); NS=8
DOLL=$(printf '0x%08x' $(( PC + NS*4096 )))
WORLD=$(python3 t/worldaddr.py ${WORLDPRD:-$PRD})
SECS=$(python3 -c "import os;print((os.path.getsize('out/$PRD/cold_P.bin')+2047)//2048)")
SNAPOPT=""; [ "$SNAP" = 1 ] && SNAPOPT="-DSNAPRESUME" && export SNAPFILE=SNAPST.BIN
PRD=$PRD NAME=$NAME BLD=bld_$NAME DOLLDEF=$DOLL CFL="-DKPLAN $SNAPOPT -I../${KPDIR:-out/kp} -DPCACHE_ADDR=$PC -DNSLOT=$NS -DCOLD_SECS=$SECS -DSF_WORLD_ADDR=${WORLD}u -DSF_WORLD_LO=${WORLD}u $XF" sh ps1rt/build.sh 2>&1 | grep -v "experimental"
