#!/bin/bash
# build a test/release disc variant: build.sh NAME "extra cflags"   (needs ROM env; run from the stage tree root)
set -e; cd "$(dirname "$0")/.."
export ROM="${ROM:-/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/roms/Payback (Europe) (En,Fr,De,Es,It).gba}"
NPAGES=56 PRD=pr_lb WORLDPRD=pr_l RPG=out/touched_f1_boot.pkl.rompages VOL=PAYBACK bash t/disc7.sh "$1" "-DSF3_DEFER -DPADDBG $2" 0 2>&1 | grep -v "^pages touched" | tail -5
