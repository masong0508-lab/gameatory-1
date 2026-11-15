#!/bin/bash
# usage: run_pcsxr.sh game.iso out.png [seconds]   headless PCSXR (HLE BIOS, GL plugin) + screenshot
if [ -z "$IN_XVFB" ]; then IN_XVFB=1 exec xvfb-run -a -s "-screen 0 800x600x24" "$0" "$@"; fi
ISO=$(readlink -f "$1"); OUT=$(readlink -f -m "$2"); T=${3:-8}
cd "$(dirname "$ISO")"      # peopsxgl reads gpuPeopsMesaGL.cfg from the cwd
stdbuf -o0 timeout $((T+10)) /usr/games/pcsxr -nogui -psxout -cdfile "$ISO" -runcd >/tmp/pcsxr.log 2>&1 &
sleep $T
import -window root "$OUT"
pkill -9 -f /usr/games/pcsxr
