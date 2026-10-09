#!/bin/sh
# Host-side physics test: tools/sim/run.sh [loop|turn|ship] [boost tick]
cd "$(dirname "$0")/../.." || exit 1
S=src
clang -O1 -g -fno-builtin -Wall -Wno-unused-function -I$S $S/fx.c $S/world.c $S/physics.c $S/car.c $S/ship.c \
    $S/loops.c build/gen/tables.c tools/sim/sim.c -o build/sim || exit 1
./build/sim build/gen/world.bin "$@"
