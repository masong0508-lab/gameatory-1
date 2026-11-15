#!/usr/bin/env python3
"""mkkplan.py PAD_BOOT.json OUT/kplan.h [extra in-level plan entries 'a,b,mask;...']  (TEST-ONLY pad plan for the scripted discs)
KPL = the menu plan recorded from the stock game's title -> level path (mgba/padlog.py); KPL2 = in-level walk/drive plan (frames since the level clock runs;
mask bits: 1=A 2=B 4=SELECT 8=START 16=RIGHT 32=LEFT 64=UP 128=DOWN 256=R 512=L)."""
import json,sys
d=json.load(open(sys.argv[1])); extra=[]
if len(sys.argv)>3 and sys.argv[3]:
    for t in sys.argv[3].split(';'): extra.append([int(x) for x in t.split(',')])
KPL2=[[0,240,64],[240,300,96],[300,540,64],[540,600,80],[600,606,1],[606,800,64],[800,1000,64],[1000,1060,96],[1060,1300,64],[1300,1360,80],[1360,1700,64],[1700,1760,96],[1760,2400,64]]
KPL2+=extra
f=lambda L:'{'+','.join('{%d,%d,%d}'%tuple(x) for x in L)+'}'
open(sys.argv[2],'w').write('/* generated: pad plan for the test disc (TEST-ONLY) */\nstatic const u32 KPL[][3]=%s;\nstatic const u32 NKPL=%d;\nstatic const u32 KPL2[][3]=%s;\nstatic const u32 NKPL2=%d;\n#define CAR_T 800\n'%(f(d['plan']),len(d['plan']),f(KPL2),len(KPL2)))
