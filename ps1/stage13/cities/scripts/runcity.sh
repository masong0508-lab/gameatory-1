#!/bin/bash
# runcity.sh K [T] : run disc out/ckK.iso in the emulator with its own HOME (blank card) and X server, shots every 30 s
cd "$(dirname "$(readlink -f "$0")")"
K=$1; T=${2:-780}
./mkhome.sh homes/r$K >/dev/null 2>&1
./run13.sh out/ck$K.iso run/ck$K $T 30 $PWD/homes/r$K
