#!/bin/bash
# build a test/release disc variant: build.sh NAME "extra cflags"   (needs ROM env; run from the stage tree root)
set -euo pipefail
: "${ROM:?set ROM to your Payback Europe ROM}"
case "$ROM" in /*) ;; *) ROM="$PWD/$ROM" ;; esac
export ROM
cd "$(dirname "$0")/.."
NPAGES=56 PRD=pr_lb WORLDPRD=pr_l RPG=out/touched_f1_boot.pkl.rompages VOL=PAYBACK bash t/disc7.sh "${1:?give an output name}" "-DSF3_DEFER ${PADDBG-"-DPADDBG"} ${2:-}" 0
