#!/bin/bash
# usage: run4.sh game.iso outprefix seconds [shot_interval] [HOME-with-.pcsxr]  own emulator binary name (sfemu3) and own X server (xs3) so other jobs' pkill patterns do not hit it
ISO=$(readlink -f "$1"); OUT=$(readlink -f -m "$2"); T=${3:-60}; IV=${4:-0}; EH=${5:-$HOME}
D=$((300+RANDOM%500)); B=$(dirname "$(readlink -f "$0")")/bin
$B/xs3 :$D -screen 0 800x600x24 >/dev/null 2>&1 & XP=$!
sleep 1; export DISPLAY=:$D
cd "$(dirname "$ISO")"
HOME=$EH stdbuf -o0 $B/sfemu3 -nogui -psxout -cdfile "$ISO" -runcd >"$OUT.log" 2>&1 &
PID=$!
if [ "$IV" != 0 ]; then el=0; while [ $el -lt $T ] && kill -0 $PID 2>/dev/null; do sleep $IV; el=$((el+IV)); import -window root "${OUT}_t$(printf %04d $el).png"; done
else sleep $T; for k in 1 2 3 4 5; do import -window root "${OUT}_$k.png"; sleep 0.37; done; fi
kill -9 $PID 2>/dev/null; kill $XP 2>/dev/null; exit 0
