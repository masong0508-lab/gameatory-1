#!/bin/bash
# usage: [OUT=dir] [PFX=tag] tests/poses.sh [extra cflags]  -> $OUT/ps1_pose<k>.png for k in 0..7 (parallel, own xvfb each)
cd "$(dirname "$0")/.."
OUT=${OUT:-shots}; PFX=${PFX:-p}; mkdir -p $OUT
for k in 0 1 2 3 4 5 6 7; do ./build.sh $PFX$k -DPOSE=$k -DSTATLOG "$@" >/dev/null & done; wait
for b in '0 1 2 3' '4 5 6 7'; do for k in $b; do tests/run.sh build/sf2b_$PFX$k.iso $OUT/ps1_pose$k.png ${SECS:-9} & done; wait; done
for k in 0 1 2 3 4 5 6 7; do echo "pose $k: $(grep -E '^ \* F 64' $OUT/ps1_pose$k.png.log | head -1 | cut -c1-40)"; done
