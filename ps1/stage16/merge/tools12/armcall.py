#!/usr/bin/env python3
"""ANALYSIS: log entries (r0-r3, lr, tick) to given guest addresses in the ARM sim.  usage: armcall.py ROM NTICKS addr1,addr2,... [max]"""
import sys,os
addrs=[int(x,16) for x in sys.argv[3].split(',')]; MX=int(sys.argv[4]) if len(sys.argv)>4 else 40
sys.argv=[sys.argv[0],sys.argv[1],sys.argv[2],'/dev/null']
src=open('tools12/armfade.py').read().replace("pickle.dump(dict(calls=calls,snaps=snaps),open(sys.argv[3],'wb'))","")
cnt={}
src=src.replace("t0=time.time()","""
def ent(uc,addr,sz,ud):
    n=cnt[addr]=cnt.get(addr,0)+1
    if n<=MX: print('CALL',hex(addr),'n',n,'tick',io.nd,'r0-r3',[hex(uc.reg_read(UC_ARM_REG_R0+k)) for k in range(4)],'lr',hex(uc.reg_read(UC_ARM_REG_LR)),'sp',hex(uc.reg_read(UC_ARM_REG_SP)),flush=True)
for a in addrs: A.u.hook_add(UC_HOOK_CODE,ent,None,a&~1,a&~1)
t0=time.time()""")
exec(compile(src,'armfade_call','exec'))
print('counts',{hex(k):v for k,v in cnt.items()})
