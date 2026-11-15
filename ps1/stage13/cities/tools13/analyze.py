#!/usr/bin/env python3
"""analyze.py LOG... : per run, the renderer's lines per frame (host sf3_frame lines, 1 line = 1 hblank; budget 456 for 30 fps), prims, overflow, LOD, map ids, GRIDCHK / MAPFOLLOW lines"""
import sys,re,os,statistics as st
MATS=('sky','road','kerb','grass','plaza','concrete','glass','brick','teal','cream','steel','car','accent','ship','glow','stunt')
WD=os.environ.get('WORLDS','out/maps')
for f in sys.argv[1:]:
    L=open(f,errors='replace').read().splitlines()
    fr=[]; first=None
    for l in L:
        m=re.search(r'SF3 frame (\d+) map (\d+) gmap (\d+) pos (-?\d+) (-?\d+) (-?\d+) hd (-?\d+) veh (\d+) ents (\d+) eng (\d+) host (\d+) lines prim (\d+) ovf (\d+) lod (\d+)',l)
        if m:
            g=[int(x) for x in m.groups()]; fr.append(g)
    sp=[int(m.group(1)) for l in L for m in [re.search(r'SPIN \d+ hd \d+ map \d+ host (\d+) prim (\d+)',l)] if m]
    spp=[int(m.group(1)) for l in L for m in [re.search(r'SPIN \d+ hd \d+ map \d+ host \d+ prim (\d+)',l)] if m]
    sd=[l.split('* ',1)[-1].strip() for l in L if 'SPIN done' in l]
    ev=[l.split('* ',1)[-1].strip() for l in L if re.search(r'GRIDCHK|MAPFOLLOW|MAPCHANGE|deferred sf3|guest map|TEST-ONLY|RT_MISS|panic|PANIC|fault|FAULT|SF3W bad|SF3M bad',l)]
    print('==',f.split('/')[-1],'frames',len(fr))
    if sp: print('    heading sweep (12 headings, start pose): host lines per heading %s | mean %.0f max %d over456 %d | max prim %d'%(sp,st.mean(sp),max(sp),sum(1 for v in sp if v>456),max(spp)))
    for d in sd: print('   ',d)
    for e in ev[:12]: print('   ',e[:170])
    if fr:
        h=[x[10] for x in fr]; steady=[x for x in fr if x[0]>=4]; hs=[x[10] for x in steady] or h
        print('    maps',sorted({x[1] for x in fr}),'gmaps',sorted({x[2] for x in fr}),'first pos',fr[0][3:6],'last pos',fr[-1][3:6],'ents',fr[-1][8])
        print('    lines all: n %d mean %.0f median %.0f max %d | frames>456: %d (%.0f%%) | steady(n>=4): mean %.0f median %.0f max %d >456 %.0f%%'%(len(h),st.mean(h),st.median(h),max(h),sum(1 for v in h if v>456),100*sum(1 for v in h if v>456)/len(h),st.mean(hs),st.median(hs),max(hs),100*sum(1 for v in hs if v>456)/len(hs)))
        try:
            import numpy as np
            w=np.load('%s/world%d/world.npz'%(WD,fr[0][1])); cx,cz=fr[0][3]>>10,fr[0][5]>>10
            lo,hi,sh,mt=int(w['lo'][cx,cz]),int(w['hi'][cx,cz]),int(w['shape'][cx,cz]),int(w['mat'][cx,cz])
            print('    start cell (%d,%d): floor lo %d hi %d shape %d %s | guest y %d -> %s'%(cx,cz,lo,hi,sh,MATS[mt],fr[0][4],'on the floor' if fr[0][4]==hi or fr[0][4]==lo else 'off the cell floor by %d (deck/ramp/other)'%min(abs(fr[0][4]-hi),abs(fr[0][4]-lo))))
        except Exception as ex: print('    (start cell check skipped: %s)'%ex)
        print('    prim max %d  ovf total %d  lod hist %s'%(max(x[11] for x in fr),sum(x[12] for x in fr),{k:sum(1 for x in fr if x[13]==k) for k in range(4)}))
