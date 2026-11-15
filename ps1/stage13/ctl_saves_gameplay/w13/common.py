import sys,os,struct
S='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/v12/ps1/s13_ctl/'
sys.path.insert(0,S+'mgba')
from emu import Emu
import scenes
ROM=sorted(__import__('glob').glob(S+'../../../roms/*.gba'))[0]
def s32(v): return v-(1<<32) if v&0x80000000 else v
def s16(v): return v-(1<<16) if v&0x8000 else v
def state(e):
    nl=s16(e.r16(0x0300000c)); ci=s16(e.r16(0x02001db8))
    tab=0x03000c60
    p=e.r32(tab+4*ci)
    d=dict(clk=e.r32(0x02001e00),nl=nl,ci=ci,map=e.r16(0x02001d40))
    if 0<=ci<=nl and p>>24==2:
        d.update(x=s32(e.r32(p+4)),z=s32(e.r32(p+8)),y=e.r16(p+0xc),hd=s16(e.r16(p+0x12)),hp=s16(e.r16(p+0x68)),score=s32(e.r32(p+0x90)),defp=e.r32(p+0x1c))
        dp=d['defp']
        if 0x08354af4<=dp<0x08354af4+128*0x3c: d['cls']=e.r8(dp+0x26)
    return d
def ents(e):
    nl=s16(e.r16(0x0300000c)); out=[]
    for i in range(nl+1):
        p=e.r32(0x03000c60+4*i)
        if p>>24!=2: continue
        dp=e.r32(p+0x1c); cls=e.r8(dp+0x26) if 0x08354af4<=dp<0x08354af4+128*0x3c else -1
        out.append((i,cls,s32(e.r32(p+4))>>1,s32(e.r32(p+8))>>1,s16(e.r16(p+0x12)),(dp-0x08354af4)//0x3c if cls>=0 else -1))
    return out
