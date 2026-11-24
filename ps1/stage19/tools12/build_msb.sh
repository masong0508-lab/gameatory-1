#!/bin/bash
# Milestone B stage B1: the merged Star-FlyBack GBA ROM (stuntfox/build.py ROM --merge --no-remixes --amiga DIR, 16 MiB) on the PS1.
#   usage: ROM=/abs/merged.gba bash tools12/build_msb.sh NAME ["extra cflags"]      (run in a prepared tree whose out/ holds the merged
#          translation: ps1/msb/translate_msb.sh, then the boot image, SF3M.BIN and pr_lb / pr_l of that run)
# The original game's entry point tools12/build.sh is unchanged and still builds rc10 byte for byte; this one adds, on top of the same
# release flags (rc10, tools12/build.sh):
#   -DMERGED     16 MiB ROM window (4096 pages, rt.c ROM_NPG, the page table to 0x8002e000, 8 interpreter stacks), an error screen for a page past
#                the image, the intro translated (prune.py without id 3, interp_glue.h), pg_fr in the ragdoll region
#   MERGED=1     ps1rt/build.sh accepts the 16 MiB ROM and checks the intro site the merged way; ROM.BIN on the disc is the merged ROM (song 3 zeroed by
#                stuntfox's mkmusic.drop_song)
#   61 resident ROM pages (t/resident_msb.txt), the pause block t/pause_pages_msb.txt (both: the original lists, map column pages moved to 0x08800000+)
# TEST discs only until Milestone B's B7 (PLAN.md).
set -euo pipefail
: "${ROM:?set ROM to the merged Star-FlyBack ROM (16 MiB)}"
case "$ROM" in /*) ;; *) ROM="$PWD/$ROM" ;; esac
[ "$(stat -c %s "$ROM")" = 16777216 ] || { echo "build_msb.sh: the merged ROM must be 16 MiB (--no-remixes)" >&2; exit 2; }
cd "$(dirname "$0")/.."
export ROM MERGED=1 ROMPAGES=4096 PZLIST=t/pause_pages_msb.txt PRUNE_DROP=3      # PRUNE_DROP: mkps1.py writes STUBTAB without id 3, as the translation was made
NPAGES=61 RPG=t/resident_msb.txt bash tools12/build.sh "${1:?give an output name}" "-DMERGED ${2:-}"
