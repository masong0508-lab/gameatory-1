#!/bin/bash
# usage: spin.sh NAME secs [extra cflags]  -> build disc with PROFSPIN, run, print stats
cd "$(dirname "$0")/.."; N=$1; T=${2:-100}; shift; shift
EXTRA="-DPRINT_EVERY_SF3=1 -DPROFSPIN=6 $*" NAME=$N BLD=bld_$N t/mk_disc.sh 2>&1 | grep -iE "error|exe size" | head -5
mkdir -p out/r_$N; ./run4.sh out/$N.iso out/r_$N/$N $T 0 >/dev/null 2>&1
python3 t/spin_stats.py out/r_$N/$N.log 8
