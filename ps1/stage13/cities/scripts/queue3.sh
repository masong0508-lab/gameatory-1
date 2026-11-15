#!/bin/bash
cd "$(dirname "$(readlink -f "$0")")"
while ! grep -q BUILDALL-DONE run/buildall.out; do sleep 5; done
echo 2 1 3 0 4 5 6 7 8 9 10 S2 S0 | tr ' ' '\n' | xargs -P 3 -I{} ./runcity.sh {} 1000
