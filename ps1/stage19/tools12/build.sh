#!/bin/bash
# build a disc variant: build.sh NAME "extra cflags"   (needs ROM env; run from the stage tree root)
# stage 19 release profile: the 62 measured resident ROM pages (t/resident62.txt), single-page CD fetches into 8 slots (-DPCACHE1), no menu
# assist and no pad/entity debug log.  KPLAN=1 (see tools12/build_test_assist.sh) adds the self-playing menu assist for rig sessions and, unless
# PADDBG is set, the PADDBG log (PADRAW / GS / GN lines on the TTY): a TEST disc, never a release.  PADDBG=FLAGS overrides the default of either profile.
# Dispatch phase 1 (PLAN.md Stage 2, rt.c dsp_boot): D3 D1 D4 D2, one flag each; DISP="" builds without them, DISP="-DDISP_D3 ..." picks items.
set -euo pipefail
: "${ROM:?set ROM to your Payback Europe ROM}"
case "$ROM" in /*) ;; *) ROM="$PWD/$ROM" ;; esac
export ROM
cd "$(dirname "$0")/.."
KP=${KPLAN:-0}
if [ "$KP" = 1 ]; then DBG=${PADDBG--DPADDBG}; else DBG=${PADDBG-}; fi
# PS1 speed Stage 1 (ps1rt/clk.h): the real-time guest clock in the level.  CLOCKF= (set empty) builds the virtual clock of the
# ps1fix release; a subset is allowed within clk.h's dependency rules (1f RTC_QUANT and 1g RTC_DT can be left out on their own).
CLOCKF=${CLOCKF-"-DRTC64 -DRTC_TIMERS -DRTC_PRESENT -DRTC_PMAX=100 -DRTC_GFRAMES -DRTC_QUANT -DRTC_DT"}
DISP=${DISP-"-DDISP_D3 -DDISP_D1 -DDISP_D4 -DDISP_D2"}
# PS1 speed stage 3, boot and CD quick wins, one flag each: -DEXEPACK packed PSX.EXE (ps1rt/exepack.py, crt0 unpacks it), -DCOLD1PASS
# COLD.BIN in one pass in the boot's black screen, -DPCPAIR 8 KiB page pairs while no level clock runs, -DCDPADPOLL pad polls during CD
# waits and long loads.  BOOTF= (set empty) builds without them; any subset works.  -DCDSTAT, -DCDDA_DATARADIO, -DCDPADPOLL_AB and
# -DPCPAIR_LEVEL are TEST-only measurement switches.  -DPADSPLIT (wave 1 fixup, rt.c io_read): in the menus a KEYINPUT read that sees one
# button go up and another go down reports the release first and the new press from the next guest frame on.
BOOTF=${BOOTF-"-DEXEPACK -DCOLD1PASS -DPCPAIR -DCDPADPOLL -DPADSPLIT"}
# rc9: -DPZBLOCK the pause block (rt.c pz_load, t/pause_pages.txt -> PAUSE.BIN): the pages read after Start and after Return to game in a
# level come in with one seek.  PZF= (set empty) builds without it.
PZF=${PZF-"-DPZBLOCK"}
NPAGES=${NPAGES:-62} PRD=pr_lb WORLDPRD=pr_l RPG=${RPG:-t/resident62.txt} VOL=PAYBACK KPLAN=$KP \
    bash t/disc7.sh "${1:?give an output name}" "-DSF3_DEFER -DPCACHE1 $DBG ${CLOCKF} ${DISP} ${BOOTF} ${PZF} ${2:-}" 0
