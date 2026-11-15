#!/bin/bash
# Stage 11 water pass: re-run everything.  Emulator-only (PCSXR 1.9.94, HLE BIOS, GL plugin under Xvfb).  Needs the player's own files, passed on the command line:
#   ROM   the built Star-FlyBack .gba    ELF  the stuntfox-merge.elf of the same build    AMIGA  the Amiga Payback folder (the one with maps/)    DUMPS  dumpworld.py output dirs world0..world10
# usage: tests/pipeline.sh ROM ELF AMIGA DUMPS WORK
# Nothing derived from the ROM or the Amiga copy is committed; WORK (scratch) holds MAPS.BIN, poses, discs and screenshots.
set -e; cd "$(dirname "$0")/.."; ROM=$1; ELF=$2; AMIGA=$3; DUMPS=$4; W=$5; mkdir -p $W/an
T="python3 -I tools"
# 1. the checker: classification per map, Amiga comparison (grids 0..3), after-fill numbers
$T/water_check.py $DUMPS --amiga $AMIGA --out $W/an/check_before.json | tee $W/an/check_before.txt
$T/water_check.py $DUMPS --amiga $AMIGA --fill --out $W/an/check_after.json | tee $W/an/check_after.txt
# 2. data: MAPS.BIN as the stage 5 converter makes it (--nofill) and with the water pass (holes filled, far-water bits)
mkdir -p $W/before $W/after
$T/mkps1world.py --all $DUMPS $ELF "$ROM" $W/before --nofill > /dev/null          # (the far-water bits are in both; only the fill differs)
$T/mkps1world.py --all $DUMPS $ELF "$ROM" $W/after --amiga $AMIGA > /dev/null
mkdir -p build/maps; cp $W/after/FONT.VRM build/maps/
# 3. poses (shore, bridge, edge: 45; holes: 21; sweeps: 6 x 20)
$T/water_check.py $DUMPS --poses $W/wposes_base.h >/dev/null
$T/water_check.py $DUMPS --poses $W/wposes_h.h --holes 3 >/dev/null
$T/water_check.py $DUMPS --poses $W/wposes_s.h --sweeps 1 >/dev/null
# 4. discs: before = -DNOFARWATER + the unfilled MAPS.BIN, after = the water pass.  u = island underlay painted magenta (-DDEBUG_UNDERLAY=1)
B="-DWPOSE -DHUD0=2"
for set in base:wposes_base.h:200:70 h:wposes_h.h:120:50 s:wposes_s.h:90:40; do IFS=: read n f fr se <<<"$set"; cp $W/$f src/$f
  fl="-DWPOSES_H=\"$f\" -DWPFR=$fr -DWPSET=$se"; [ $n != base ] && fl="$fl -DFORCELOD=1"
  for v in 0 1; do for u in "" u; do
    M=$W/after; X=""; [ $v = 0 ] && { M=$W/before; X="-DNOFARWATER"; }; [ -n "$u" ] && X="$X -DDEBUG_UNDERLAY=1"
    mkdir -p build/maps; cp $M/MAPS.BIN build/maps/MAPS.BIN
    eval ./build.sh ${n}${v}${u} $B $fl $X
  done; done; done
# 5. run (each disc ~10 min) and analyse: xvfb-run -a -s "-screen 0 800x600x24" python3 tools/wp_run.py build/sf5m_<tag>.iso $W/an/<tag> 2300
#    python3 -I tools/wp_pixels.py src/wposes_base.h $W/an/base1 $W/an/base1u $DUMPS     (holes, far water, flicker per pose and map)
#    python3 -I tools/wp_sweeps.py src/wposes_s.h $W/an/s1u $DUMPS $W/an/s1             (sweep spikes)
# 6. the tour disc: AUTOTOUR (every map, 4 views, one log line a view); run it, then compare scanlines per view with the before disc (-DNOFARWATER, MAPS.BIN from before/):
#    python3 -I tools/tour_cmp.py tour_before.log tour_after.log     (first lap only; the tour loops)
#    python3 -I tools/ba_montage.py OUT.png an/base0 an/base0u an/base1 an/base1u 3,28,40     (before/after sheet, underlay magenta)
cp $W/after/MAPS.BIN build/maps/MAPS.BIN; ./build.sh tour -DAUTOTOUR
