#!/bin/sh
# run_all.sh DISC OUTROOT [SYMS] [CORE]  - every session, one after the other (one emulator process at a time).
#
#   DISC     .cue / .bin / .iso of the build under test (pcsx_rearmed reads a plain 2048-byte ISO as well)
#   OUTROOT  output root: OUTROOT/<session>.log, OUTROOT/<session>/{sheet.png,result.json,script.txt,tty_timeline.txt,...}
#   SYMS     the ELF (or nm output / linker map) of THIS build; optional, but most counters and the assist switch need it
#   CORE     pcsx_rearmed (default, HLE BIOS) | swanstation | beetle  (the accurate cores run through tools/ob_session.py with
#            openboot as firmware from RIG_SYSTEM; the disc must then be one that runs there, see BOOTROM.md)
#
# Environment: SOAK_FRAMES (default 120000), ONLY="a b c" (session letters to run, default all); RIG_CORES and RIG_SYSTEM
# as described in README.md.
# States are written to OUTROOT/states (copy the good ones to the state directory, RIG_STATES or ps1/rig/states).  A summary
# of every FAIL is printed at the end.
DISC=$1; OUT=$2; SYMS=$3; CORE=${4:-pcsx_rearmed}
HERE=$(cd "$(dirname "$0")" && pwd)
[ -n "$DISC" ] && [ -n "$OUT" ] || { echo "usage: run_all.sh DISC OUTROOT [SYMS] [CORE]"; exit 2; }
mkdir -p "$OUT"
S=""; [ -n "$SYMS" ] && S="--syms $SYMS"
case "$CORE" in
  swanstation|beetle) PY="python3 $HERE/tools/ob_session.py" ;;
  *) PY="python3" ;;
esac
want() { [ -z "$ONLY" ] && return 0; for x in $ONLY; do [ "$x" = "$1" ] && return 0; done; return 1; }
LOGS=""     # the logs written by THIS invocation (OUTROOT may hold logs of earlier runs)
run() { letter=$1; name=$2; shift 2; want "$letter" || return 0
  LOGS="$LOGS $OUT/$name.log"
  echo "=== $name: $*"
  $PY "$@" --disc "$DISC" --core "$CORE" $S --state-dir "$OUT/states" --out "$OUT/$name" > "$OUT/$name.log" 2>&1
  echo "    exit $? ($(grep -c '^PASS' "$OUT/$name.log") PASS, $(grep -c '^FAIL' "$OUT/$name.log") FAIL)"; }
run a a_boot_to_title      "$HERE/sessions/boot_to_title.py" --save-state
run b b_new_game_to_level  "$HERE/sessions/new_game_to_level.py" --path pad --save-state
run b b_assist_path        "$HERE/sessions/new_game_to_level.py" --path assist --save-state
run j j_replay_script      "$HERE/sessions/replay.py" --script "$OUT/b_new_game_to_level/script.txt" --assist off
run d d_maps               "$HERE/sessions/maps.py"
run e e_save_load          "$HERE/sessions/save_load.py"
run f f_soak               "$HERE/sessions/soak.py" --max-frames ${SOAK_FRAMES:-120000}
run c c_in_level           "$HERE/sessions/in_level.py"
run g g_state_check        "$HERE/sessions/state_check.py"
run h h_speed              "$HERE/sessions/speed.py"
if [ "$CORE" = "pcsx_rearmed" ]; then      # the interpreter check needs pcsx_rearmed's CPU interpreter
  run i i_strict_cpu         "$HERE/sessions/strict_cpu.py"
  run i i_strict_cpu_patched "$HERE/sessions/strict_cpu.py" --patch-invalid
fi
echo "=== done"
echo "--- every FAIL of the sessions run now (count, line):"
[ -n "$LOGS" ] && grep -h -E '^FAIL' $LOGS | sed 's/ \[.*//' | sort | uniq -c | sort -rn | head -60
