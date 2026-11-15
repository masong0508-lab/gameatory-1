#!/usr/bin/env python3
"""touched guest labels (snapdump.py) -> the set of cold function entries the scenario executes.  usage: mkrank.py touched.pkl PRDIR(the full-cold translation the labels came from) rank.pkl
Each label is mapped guest -> host (payback_P.map) and then to the cold-table row whose host span contains it (coldtab_P.bin), so function boundaries are the translator's own
(stage 4 fix: the old version used the function list of the stage 2 program, which put 0x08077d94 into the function at 0x08077d50 and left it out of the scenario)."""
import sys,pickle,struct,bisect
gs=pickle.load(open(sys.argv[1],'rb')); D=sys.argv[2]
m={}
for l in open(D+'/payback_P.map'):
    a,h=l.split(); m[int(a,16)]=int(h,16)
d=open(D+'/coldtab_P.bin','rb').read(); n=struct.unpack_from('<I',d,0)[0]
rows=sorted((struct.unpack_from('<4I',d,4+16*i) for i in range(n)),key=lambda r:r[2])
HS=[r[2] for r in rows]
S=set()
for a in gs:
    h=m.get(a)
    if h is None: continue
    j=bisect.bisect_right(HS,h)-1
    if j>=0 and rows[j][2]<=h<rows[j][3]: S.add(rows[j][0])
pickle.dump(S,open(sys.argv[3],'wb')); print('scenario cold functions',len(S),'of',n)
