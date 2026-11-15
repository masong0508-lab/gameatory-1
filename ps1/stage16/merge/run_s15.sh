#!/bin/bash
# run_s15.sh CUE TAG [session args...]: fresh blank-card HOME in /dev/shm/s15, s15session.py (one emulator)
cd "$(dirname "$(readlink -f "$0")")"
CUE=$1; T=$2; shift 2
mkdir -p /dev/shm/s15/run
python3 - <<P
import sys; sys.path.insert(0,'tools13'); import pcx,shutil,os
shutil.rmtree('/dev/shm/s15/homes_$T',ignore_errors=True)
pcx.mkhome('/dev/shm/s15/homes_$T',os.path.abspath('../card1.orig.mcd'))
P
python3 -I tools16/s15session.py $CUE /dev/shm/s15/homes_$T /dev/shm/s15/run/$T "$@" > /dev/shm/s15/run/$T.out 2>&1
