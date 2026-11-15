#!/bin/bash
# build_ps1.sh: Star-FlyBack on PS1, one reproducible pipeline.  ROM (Payback, Europe) + the Amiga Payback files + the remix MP3s in, one .bin/.cue out.
#   ROM=/path/Payback.gba AMIGA=/path/amiga/Payback/payback MUSIC_MODS=dir MUSIC_PB=dir [REPO=/path/gameatory-1] [OUT=./out] ./build_ps1.sh [all|title|snap]
#   all  = snapshot-resume disc (lands in the level at once) AND the title-boot disc (power-on -> title -> level, scripted pad plan)   snap / title = one of them
# Needs: python3 + numpy + pillow + unicorn, clang + ld.lld + llvm-objcopy (mipsel and armv4t targets), genisoimage, ffmpeg, libmgba (padlog), xvfb + pcsxr only for tests/.
# Nothing derived from the ROM, the Amiga files or the music is ever written outside OUT.  Payback song 3 is never put on the disc.
set -e; HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"
: "${ROM:?set ROM}"; : "${AMIGA:?set AMIGA}"; REPO=${REPO:-/home/user/gameatory-1}; export ROM AMIGA
OUT=${OUT:-$HERE/out}; MODE=${1:-all}; mkdir -p "$OUT"; [ "$OUT" = "$HERE/out" ] || { rm -f out; ln -s "$OUT" out; }
step(){ echo "=== $(date +%H:%M:%S) $*"; }
mkdir -p out/s2 out/kp out/maps out/sf3m
# ---- 1. Payback side: IWRAM image, code discovery, coverage -> hot (resident) set and cold set
step "iw.bin";      [ -f out/iw.bin ] || python3 tools7/mkiw.py "$ROM" out/iw.bin
step "discovery";   [ -f out/s2/prog_pr.pkl ] || python3 -I tools7/mkprog.py
step "coverage (ARM-side, 3000 ticks)"; [ -f out/cov_L3.pkl ] || python3 -I tools7/explore.py L3 3000 "[0x3ff,0x3ff&~8,0x3ff,0x3ff&~1,0x3ff,0x3ff&~0x81]" "" > out/explore_L3.log 2>&1
step "resident + cold sets"
python3 mkresident.py out/s2/prog_pr.pkl out/s2/resident.pkl out/cov_L3.pkl | tail -1
python3 -I tools7/mkcoldall.py out/s2/prog_pr.pkl out/s2/resident.pkl out/cold_all.pkl
python3 mkcold.py out/s2/prog_pr.pkl out/s2/resident.pkl out/s2/cold.pkl 85000 out/cov_L3.pkl | tail -1
[ -f t/swi5.bin ] || { clang --target=armv4t-none-eabi -c t/swi5.s -o out/swi5.o && llvm-objcopy -O binary --only-section=.text out/swi5.o t/swi5.bin; }
# ---- 2. pad plan (the stock game's title -> level path, recorded with libmgba), boot image
step "pad plan";    [ -f out/pad_boot.json ] || (cd mgba && python3 padlog.py "$ROM" ../out/pad_boot.json > ../out/padlog.log 2>&1)
python3 tools7/mkkplan.py out/pad_boot.json out/kp/kplan.h "${KPL2_EXTRA:-}"
step "boot image";  python3 t2m.py "$ROM" out/iw.bin out/pr_b --map P --pruned --cache out/s2/prog_pr.pkl --tag P --resident out/s2/resident.pkl --cold out/s2/cold.pkl > out/pr_b.log 2>&1
BOOT=out/boot.bin python3 lockstep2.py "$ROM" out/pr_b P 3 > out/boot.log 2>&1
python3 t2m.py "$ROM" out/iw.bin out/pr --map P --pruned --cache out/s2/prog_pr.pkl --tag P --resident out/s2/resident.pkl --cold out/cold_all.pkl > out/pr.log 2>&1
python3 -c "import pickle;pickle.dump([],open('out/pr/rompages_P.pkl','wb'))"
# ---- 3. maps: the Star-FlyBack GBA build by the repo's own tools -> 11 world dumps -> SF3M.BIN (all maps, compact, on the CD)
step "Star-FlyBack GBA build (for the world data and the pb_* tables)"
if [ ! -f out/built.gba ]; then rm -rf out/repo; cp -r "$REPO" out/repo; (cd out/repo/stuntfox && python3 build.py --merge --no-remixes --amiga "$AMIGA" -o ../../built.gba "$ROM" > ../../build_gba.log 2>&1); fi
ELF=$PWD/out/repo/stuntfox/build/merge/stuntfox-merge.elf
step "11 world dumps + SF3M.BIN"
if [ ! -f out/SF3M.BIN ]; then
  for n in 0 1 2 3 4 5 6 7 8 9 10; do python3 -I tools7/dumpworld.py --rom out/built.gba --elf $ELF --map $n --out out/maps/world$n --repo $PWD/out/repo > out/maps/d$n.log 2>&1; done
  python3 -I tools7/mkmaps7.py out/maps $ELF out/built.gba out/sf3m > out/mkmaps7.log; cp out/sf3m/SF3M.BIN out/SF3M.BIN; fi
# ---- 4. the live level: full-cold sim build, scenario run, rank, L build (stage 4 final.sh), then the discs
step "stage 4 chain (f1 sim, snapshot, rank, f2, L)"
bash t/rebuild_f1.sh > out/f1.log 2>&1 || true
bash t/final.sh > out/final.log 2>&1
step "discs"
bash t/disc7.sh s7 "" 1 > out/disc_s7.log 2>&1
python3 tools7/mkdisc2.py --iso out/s7.iso --out out/disc/StarFlyBack-PS1-live --default-tracks
# ---- 5. title-boot variant (renderer deferred to level start; the level is NOT reached in pcsxr in practical time): run t/boot_chain.sh first
#   NPAGES=56 PRD=pr_lb WORLDPRD=pr_l RPG=out/touched_f1_boot.pkl.rompages bash t/disc7.sh s7b "-DSF3_DEFER" 0
# ---- coverage note: the cold prefix is scenario-bounded (renderer window shares RAM).  Functions the sim never ran but pcsxr did are listed in tools7/extra_touch.txt
#   (found with t/covloop.sh: run the snapshot disc in pcsxr, collect RT_MISS, add, rebuild; T=330 gives ~97 presented frames).  Test-only trigger flags for disc7.sh extra cflags:
#   -DMAPTEST -DMAPTEST_AT=n -DMAPTEST_TO=m, -DDOLLTEST -DDOLLTEST_AT=n, -DRADIO_TEST, -DRADIO_AUTOPLAY, -DPADDBG, -DPRINT_EVERY_SF3=15; rt.c is built -Os by default (RTOPT) to fit under 0x80028000.
