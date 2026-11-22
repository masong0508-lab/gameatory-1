#!/bin/bash
# stage 7 disc build from the L translation (out/pr_l): usage disc7.sh NAME "extra cflags" [snap]   (snap=0 builds the title-boot variant without SNAPRESUME)
# memory map decisions made here: page cache NSLOT=8 (stage 4 had 40), the ragdoll code behind it, the renderer's world window right behind the cold prefix.
# stage 19: the self-playing menu assist (KPLAN, out/kp/kplan.h) is a TEST feature and is compiled in only with KPLAN=1; a release disc has none.
# SNAPRESUME (snap=1) is test-only as well and needs KPLAN=1.
set -euo pipefail
: "${ROM:?set ROM to your Payback Europe ROM}"
case "$ROM" in /*) ;; *) ROM="$PWD/$ROM" ;; esac
export ROM
cd "$(dirname "$0")/.."
NAME=$1; XF=$2; SNAP=${3:-1}; PRD=${PRD:-pr_l}; RPG=${RPG:-out/touched_f1.pkl.rompages}; KPLAN=${KPLAN:-0}
case "$KPLAN" in 0|1) ;; *) echo "disc7.sh: KPLAN must be 0 or 1" >&2; exit 2 ;; esac
if [ "$SNAP" = 1 ] && [ "$KPLAN" != 1 ]; then echo "disc7.sh: snap=1 (SNAPRESUME) is a test build: set KPLAN=1" >&2; exit 2; fi
FL=$(python3 t/mkrompages.py $RPG ${NPAGES:-72} out/$PRD/coldtab_P.bin out/$PRD/rompages_P.pkl)
PC=$(echo "$FL" | sed -n 's/.*PCACHE_ADDR=\(0x[0-9a-f]*\).*/\1/p'); NS=8
DOLL=$(printf '0x%08x' $(( PC + NS*4096 )))
WORLD=$(python3 t/worldaddr.py ${WORLDPRD:-$PRD})
SECS=$(python3 -c "import os;print((os.path.getsize('out/$PRD/cold_P.bin')+2047)//2048)")
SNAPOPT=""; [ "$SNAP" = 1 ] && SNAPOPT="-DSNAPRESUME" && export SNAPFILE=SNAPST.BIN
KPOPT=""; [ "$KPLAN" = 1 ] && KPOPT="-DKPLAN -I../${KPDIR:-out/kp}" && echo "disc7.sh: TEST build $NAME with the menu assist (KPLAN)" >&2
PRD=$PRD NAME=$NAME BLD=bld_$NAME DOLLDEF=$DOLL CFL="$KPOPT $SNAPOPT -DPCACHE_ADDR=$PC -DNSLOT=$NS -DCOLD_SECS=$SECS -DSF_WORLD_ADDR=${WORLD}u -DSF_WORLD_LO=${WORLD}u $XF" sh ps1rt/build.sh
