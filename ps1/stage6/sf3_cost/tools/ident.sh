#!/bin/bash
# usage: ident.sh NAME_REF "ref flags" NAME_NEW "new flags"  : fixed LOD 3 + hash, runs both in parallel, compares per-frame hash
cd "$(dirname "$0")/.."
(SF3SRC=${REFSRC:-../sf/sf3.c} t/spin.sh $1 80 -DFIELDS=2 -DFIXLOD=3 -DSPINHASH $2 > out/$1.stat 2>&1) &
sleep 3
(t/spin.sh $3 80 -DFIELDS=2 -DFIXLOD=3 -DSPINHASH $4 > out/$3.stat 2>&1) &
wait
cat out/$1.stat out/$3.stat | grep -E "^n |ph"
python3 - $1 $3 <<'P'
import sys; sys.path.insert(0,'t')
from spin_stats import load
a={x[0]:x for x in load('out/r_%s/%s.log'%(sys.argv[1],sys.argv[1]))}; b={x[0]:x for x in load('out/r_%s/%s.log'%(sys.argv[2],sys.argv[2]))}
k=[i for i in a if i in b and i>=3]; print(len(k),'frames compared; hash equal',sum(a[i][5]==b[i][5] for i in k),'prim equal',sum(a[i][3]==b[i][3] for i in k))
P
