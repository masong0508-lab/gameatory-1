#!/usr/bin/env python3
"""ANALYSIS: who writes OBJ tile VRAM (0x06014000..0x06018000)?  Same setup as armfade.py (real id1/id3); hooks VRAM writes there, logs first writes per call site.
usage: armvw.py ROM NTICKS"""
import sys,os
sys.argv=[sys.argv[0],sys.argv[1],sys.argv[2],'/dev/null']
src=open('tools12/armfade.py').read().replace("pickle.dump(dict(calls=calls,snaps=snaps),open(sys.argv[3],'wb'))","")
hits={}; 
src=src.replace("t0=time.time()","""
def vw(uc,acc,addr,sz,val,ud):
    pc=uc.reg_read(UC_ARM_REG_PC); lr=uc.reg_read(UC_ARM_REG_LR); k=(pc&~0xff,lr&~0xff)
    if k not in hits: hits[k]=[io.nd,addr,val,sz,0]; print('OBJVRAM write tick',io.nd,'addr',hex(addr),'pc',hex(pc),'lr',hex(lr),'val',hex(val),flush=True)
    hits[k][4]+=1
A.u.hook_add(UC_HOOK_MEM_WRITE,vw,None,0x06014000,0x06017fff)
t0=time.time()""")
exec(compile(src,'armfade_vw','exec'))
print('hits',{(hex(a),hex(b)):v for (a,b),v in hits.items()})
