#!/usr/bin/env python3
"""mkcoldall.py PROG.pkl RESIDENT.pkl OUT.pkl : cold set = every discovered function that is not resident and not a stub."""
import sys,pickle; sys.path.insert(0,'.')
import prune
res,funcs=pickle.load(open(sys.argv[2],'rb')); stubs={a for a,n in prune.STUBS.values()}
cold={f for f in funcs if f not in res and f not in stubs}; print('cold',len(cold),'resident',len(res))
pickle.dump((cold,funcs),open(sys.argv[3],'wb'))
