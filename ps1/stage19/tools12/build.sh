#!/bin/bash
# build a disc variant: build.sh NAME "extra cflags"   (needs ROM env; run from the stage tree root)
# stage 19 release profile: the 62 measured resident ROM pages (t/resident62.txt), single-page CD fetches into 8 slots (-DPCACHE1), no menu
# assist and no pad/entity debug log.  KPLAN=1 (see tools12/build_test_assist.sh) adds the self-playing menu assist for rig sessions and, unless
# PADDBG is set, the PADDBG log (PADRAW / GS / GN lines on the TTY): a TEST disc, never a release.  PADDBG=FLAGS overrides the default of either profile.
set -euo pipefail
: "${ROM:?set ROM to your Payback Europe ROM}"
case "$ROM" in /*) ;; *) ROM="$PWD/$ROM" ;; esac
export ROM
cd "$(dirname "$0")/.."
KP=${KPLAN:-0}
if [ "$KP" = 1 ]; then DBG=${PADDBG--DPADDBG}; else DBG=${PADDBG-}; fi
NPAGES=${NPAGES:-62} PRD=pr_lb WORLDPRD=pr_l RPG=${RPG:-t/resident62.txt} VOL=PAYBACK KPLAN=$KP \
    bash t/disc7.sh "${1:?give an output name}" "-DSF3_DEFER -DPCACHE1 $DBG ${2:-}" 0
