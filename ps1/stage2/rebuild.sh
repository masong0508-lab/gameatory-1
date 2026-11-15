#!/bin/sh
cd "$(dirname "$0")"
python3 t2m.py "../../../roms/Payback (Europe) (En,Fr,De,Es,It).gba" out/iw.bin out/pr --map P --pruned --cache out/prog_pr.pkl --tag P --resident out/resident.pkl 2>&1 | grep -E "^words"
