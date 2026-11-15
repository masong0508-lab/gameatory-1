#!/bin/bash
# usage: run.sh game.iso out.png [seconds] [keyscript]   own copy of run_pcsxr.sh: own X display (xvfb-run -a), own log
# (out.png.log), kills only its own emulator.  keyscript lines: "<seconds from start> <xdotool arguments>"
if [ -z "$IN_XVFB" ]; then IN_XVFB=1 exec xvfb-run -a -s "-screen 0 800x600x24" "$0" "$@"; fi
ISO=$(readlink -f "$1"); OUT=$(readlink -f -m "$2"); T=${3:-8}; KEYS=$4; [ -n "$KEYS" ] && KEYS=$(readlink -f "$KEYS")
cd "$(dirname "$ISO")"      # peopsxgl reads gpuPeopsMesaGL.cfg from the cwd
stdbuf -o0 /usr/games/pcsxr -nogui -psxout -cdfile "$ISO" -runcd >"$OUT.log" 2>&1 &
PID=$!
if [ -n "$KEYS" ]; then ( while read t rest; do sleep $t; xdotool $rest; done < "$KEYS" ) & fi
sleep $T
import -window root "$OUT"
kill -9 $PID 2>/dev/null; wait $PID 2>/dev/null
exit 0
