#!/bin/bash
# usage: run_long.sh game.iso outprefix seconds   headless PCSXR, 5 screenshots at the end (the GL plugin sometimes presents a half-drawn frame)
if [ -z "$IN_XVFB" ]; then IN_XVFB=1 exec xvfb-run -a -s "-screen 0 800x600x24" "$0" "$@"; fi
ISO=$(readlink -f "$1"); OUT=$(readlink -f -m "$2"); T=${3:-60}
cd "$(dirname "$ISO")"
stdbuf -o0 timeout $((T+20)) /usr/games/pcsxr -nogui -psxout -cdfile "$ISO" -runcd >/tmp/pcsxr_long.log 2>&1 &
sleep $T
for k in 1 2 3 4 5; do import -window root "${OUT}_$k.png"; sleep 0.37; done
pkill -9 -f /usr/games/pcsxr
