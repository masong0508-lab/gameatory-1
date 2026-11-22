#!/bin/bash
# build a disc variant: build.sh NAME "extra cflags"   (needs ROM env; run from the stage tree root)
# stage 19 release profile: the 62 measured resident ROM pages (t/resident62.txt), single-page CD fetches into 8 slots (-DPCACHE1), no menu
# assist.  KPLAN=1 (see tools12/build_test_assist.sh) adds the self-playing menu assist for rig sessions: a TEST disc, never a release.
set -euo pipefail
: "${ROM:?set ROM to your Payback Europe ROM}"
case "$ROM" in /*) ;; *) ROM="$PWD/$ROM" ;; esac
export ROM
cd "$(dirname "$0")/.."
NPAGES=${NPAGES:-62} PRD=pr_lb WORLDPRD=pr_l RPG=${RPG:-t/resident62.txt} VOL=PAYBACK KPLAN=${KPLAN:-0} \
    bash t/disc7.sh "${1:?give an output name}" "-DSF3_DEFER -DPCACHE1 ${PADDBG-"-DPADDBG"} ${2:-}" 0
