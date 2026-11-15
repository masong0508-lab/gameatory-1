#!/bin/bash
# usage: run_hw.sh disc(.iso|.cue) out.png secs log [keyscript]   keyscript: lines "T xdotool-args" executed T seconds after start (e.g. "5 keydown x")
if [ -z "$IN_XVFB" ]; then IN_XVFB=1 exec xvfb-run -a -s "-screen 0 800x600x24" "$0" "$@"; fi
ISO=$(readlink -f "$1"); OUT=$(readlink -f -m "$2"); T=${3:-8}; LOG=$(readlink -f -m "$4"); KS=$5
cd "$(dirname "$ISO")"
stdbuf -o0 timeout $((T+10)) /usr/games/pcsxr -nogui -psxout -cdfile "$ISO" -runcd >"$LOG" 2>&1 &
start=$(date +%s.%N)
if [ -n "$KS" ]; then while read -r t rest; do [ -z "$t" ] && continue; now=$(date +%s.%N); w=$(echo "$t - ($now - $start)" | bc -l); [ "${w:0:1}" != "-" ] && sleep $w; eval xdotool $rest; done < "$KS"; fi
now=$(date +%s.%N); w=$(echo "$T - ($now - $start)" | bc -l); [ "${w:0:1}" != "-" ] && sleep $w
import -window root "$OUT"
pkill -9 -f /usr/games/pcsxr
