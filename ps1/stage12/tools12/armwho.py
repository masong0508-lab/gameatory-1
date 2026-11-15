#!/usr/bin/env python3
"""ANALYSIS: which real routine (gfx_fade_flip id1 / gfx_effect id3) contains the IWRAM span code calls (0x3007800).  usage: armwho.py ROM NTICKS"""
import sys
sys.argv=[sys.argv[0],sys.argv[1],sys.argv[2],'/dev/null']
src=open('tools12/armfade.py').read().replace("pickle.dump(dict(calls=calls,snaps=snaps),open(sys.argv[3],'wb'))","")
src=src.replace("t0=time.time()","""
inside=[0]; mk={}
def mkent(uc,addr,sz,ud):
    k=(inside[0],io.nd); mk[k]=mk.get(k,0)+1
A.u.hook_add(UC_HOOK_CODE,mkent,None,0x3007800,0x3007800)
for aa,ii in real.items():
    def e2(uc,addr,sz,ud,ii=ii):
        lr=uc.reg_read(UC_ARM_REG_LR); prev=inside[0]; inside[0]=ii
        def ret(u,a,s,d):
            inside[0]=prev
        A.u.hook_add(UC_HOOK_CODE,ret,None,lr&~1,lr&~1)
    A.u.hook_add(UC_HOOK_CODE,e2,None,aa,aa)
t0=time.time()""")
exec(compile(src,'armfade_who','exec'))
print('maker calls by (inside_id, tick):',sorted(mk.items()))
print('calls recorded:',[(c['id'],c['tick'],c['r']) for c in calls][:20])
