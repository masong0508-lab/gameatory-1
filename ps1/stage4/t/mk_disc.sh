#!/bin/bash
# last step of final.sh alone: rebuild the PS1 disc out/s4.iso after a change in ps1rt/ or sf/ (needs out/pr_l, out/SNAPST.BIN)
set -e; cd "$(dirname "$0")/.."
FL=$(python3 t/mkrompages.py out/touched_f1.pkl.rompages ${NPAGES:-72} out/pr_l/coldtab_P.bin out/pr_l/rompages_P.pkl)
SNAPFILE=SNAPST.BIN PRD=pr_l NAME=${NAME:-s4} BLD=${BLD:-bld_l} CFL="-DKPLAN -DSNAPRESUME -I../out/kp $FL $EXTRA" sh ps1rt/build.sh 2>&1 | tail -2
