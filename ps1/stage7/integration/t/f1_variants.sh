#!/bin/bash
# stage 7: coverage from several timing-perturbed runs of the full-cold sim (the live game's random numbers differ from any single sim run); union -> out/touched_f1.pkl
cd "$(dirname "$0")/.."
for k in ${VARIANTS:-7001 13337 29993 51111 90001 123457}; do
  ( PERTURB_CYC=$k TOUCH_FROM=level python3 t/snapdump.py f1 60 ${TOTAL:-1700} out/SNAPST_f1_$k.BIN out/touched_f1_p$k.pkl > out/snapdump_f1_$k.log 2>&1 ) &
done; wait
python3 - <<'P'
import pickle,glob
u=set(pickle.load(open('out/touched_f1.pkl','rb'))); n0=len(u)
for f in glob.glob('out/touched_f1_p*.pkl'):
    if f.endswith('.rompages'): continue
    s=set(pickle.load(open(f,'rb'))); print(f,len(s),'new',len(s-u)); u|=s
pickle.dump(u,open('out/touched_f1.pkl','wb')); print('union',n0,'->',len(u))
P
