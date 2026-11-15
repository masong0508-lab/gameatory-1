"""state-driven pad bot for Payback (works on any backend that exposes r8/r16/r32 of the GBA address space: mGBA Emu or the PS1 sim wrapper)
Payback's own controls (control setup screen): A accelerate, B reverse/brake, Left/Right turn, R shoot/horn, L in/out vehicle, Up next weapon, Down previous weapon, Start pause."""
import math
TURN=5760.0
def s32(v): return v-(1<<32) if v&0x80000000 else v
def s16(v): return v-(1<<16) if v&0x8000 else v
class Mem:
    """adapter: g(addr,size) reads guest memory"""
    def __init__(s,r8,r16,r32): s.r8,s.r16,s.r32=r8,r16,r32
def ent_ptr(m,i,ew_base=None):
    p=m.r32(0x03000c60+4*i)
    return p
def to_off(p,host=False):
    return p
def ents(m,host_ew=None):
    """list of dict for all entities; pointers are raw 0x02xxxxxx (mGBA) or host addresses in EWRAM window (PS1 guest): host_ew = host EWRAM base or None"""
    nl=s16(m.r16(0x0300000c)); out=[]
    for i in range(nl+1):
        p=m.r32(0x03000c60+4*i)
        if host_ew is not None:
            if not (host_ew<=p<host_ew+0x40000): continue
            q=0x02000000+(p-host_ew)
        else:
            if p>>24!=2: continue
            q=p
        dp=m.r32(q+0x1c); idx=(dp-0x08354af4)//0x3c if 0x08354af4<=dp<0x08354af4+128*0x3c else -1
        cls=-1
        if idx>=0: cls=0 if idx<=27 or 45<=idx<=48 else (1 if (38<=idx<=44 or 49<=idx<=65) else (2 if 28<=idx<=31 else 3 if idx<=81 else 255))
        out.append(dict(i=i,q=q,cls=cls,idx=idx,x=s32(m.r32(q+4)),z=s32(m.r32(q+8)),hd=s16(m.r16(q+0x12)),hp=s16(m.r16(q+0x68)),score=s32(m.r32(q+0x90))))
    return out
def level(m): return dict(clk=m.r32(0x02001e00),map=s16(m.r16(0x02001d40)),ci=s16(m.r16(0x02001db8)),nl=s16(m.r16(0x0300000c)))
def steer(me,tx,tz,deadband=90):
    """keys to turn towards (tx,tz): returns (turn_key or None, abs error in turns)"""
    des=math.atan2(tx-me['x'],tz-me['z'])/(2*math.pi)*TURN
    err=(des-me['hd']+TURN/2)%TURN-TURN/2
    k=None
    if err>deadband: k='LEFT'
    elif err<-deadband: k='RIGHT'
    return k,abs(err)/TURN
