#!/bin/bash
# usage: run7.sh disc(.iso|.cue) outprefix secs keyscript [shot_interval]   headless PCSXR (HLE BIOS, emulator-only), log lines stamped with seconds since start, screenshots every N s.
# keyscript lines: "T xdotool-args" (T seconds after start, fractional ok, ascending).
if [ -z "$IN_XVFB" ]; then IN_XVFB=1 exec xvfb-run -a -s "-screen 0 800x600x24" "$0" "$@"; fi
ISO=$(readlink -f "$1"); OUT=$(readlink -f -m "$2"); T=${3:-60}; KS=$4; IV=${5:-0}
cd "$(dirname "$ISO")"
start=$(date +%s.%N)
( stdbuf -o0 timeout $((T+15)) /usr/games/pcsxr -nogui -psxout -cdfile "$ISO" -runcd 2>&1 | python3 -u -c "
import sys,time
t0=$start
for l in sys.stdin: sys.stdout.write('%7.2f %s'%(time.time()-t0,l))" > "$OUT.log" ) &
if [ -n "$IV" ] && [ "$IV" != 0 ]; then ( n=0; while [ $n -lt $T ]; do sleep $IV; n=$((n+IV)); import -window root "${OUT}_t$(printf %04d $n).png"; done ) & fi
if [ -n "$KS" ] && [ -f "$KS" ]; then   while read -r t rest; do [ -z "$t" ] && continue; now=$(date +%s.%N); w=$(echo "$t - ($now - $start)" | bc -l); [ "${w:0:1}" != "-" ] && sleep $w; W=$(xdotool search --onlyvisible --name PCSXR | head -1); [ -n "$W" ] && { xdotool windowfocus $W; xdotool mousemove 300 200; }; echo "KEY $t $W $rest" >> "$OUT.keys"; eval xdotool $rest; done < "$KS"; fi
now=$(date +%s.%N); w=$(echo "$T - ($now - $start)" | bc -l); [ "${w:0:1}" != "-" ] && sleep $w
import -window root "${OUT}_end.png"
pkill -9 -f /usr/games/pcsxr
