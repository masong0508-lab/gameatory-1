#!/bin/bash
# usage: flashcap.sh game.iso out.raw [seconds]  PCSXR in its own Xvfb, ffmpeg grabs the 640x480 game window at 60 Hz as 8-bit gray frames (out.raw)
if [ -z "$IN_XVFB" ]; then IN_XVFB=1 exec xvfb-run -a -s "-screen 0 800x600x24" "$0" "$@"; fi
ISO=$(readlink -f "$1"); OUT=$(readlink -f -m "$2"); T=${3:-30}
cd "$(dirname "$ISO")"
stdbuf -o0 /usr/games/pcsxr -nogui -psxout -cdfile "$ISO" -runcd >"$OUT.log" 2>&1 &
PID=$!
sleep 6      # boot + upload
ffmpeg -loglevel error -y -f x11grab -framerate 60 -video_size 640x480 -i "$DISPLAY+0,0" -t $T -pix_fmt gray -f rawvideo "$OUT"
kill -9 $PID 2>/dev/null; wait $PID 2>/dev/null
