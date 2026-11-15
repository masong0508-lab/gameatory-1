#!/usr/bin/env python3
"""TEST-ONLY unicorn-MIPS sim of the Payback PS1 exe with a modelled SIO0: a DualShock (digital / config / analog) and a memory card in slot 1.
The runtime's real pad driver (hw_pad.h) and card driver (hw_card.h) run unchanged against it (build flag -DSIMSIO); GPU/GTE/SPU/CD-ROM are not modelled
(the CD is a memory-mapped image: -DCDSIM).  No ROM data is stored here; the disc image comes from the caller.
  sim=Sim13(exe,iso,elf,card='card.mcd'); sim.pad=callable(gba_frame)->PS1 button mask (active high: b0 Select ... b15 Square); sim.cb=callable(sim)->True to stop at each present()
EMULATOR-ONLY / SIM-ONLY: not hardware, not PCSXR."""
import sys,struct,os,subprocess,time
from unicorn import *
from unicorn.mips_const import *
PAL,VRAM,EW,IW=0x80180000,0x80181000,0x801b0000,0x801f0000
class Sio:
    """SIO0 register model (JOY_DATA 0x40, JOY_STAT 0x44, JOY_MODE 0x48, JOY_CTRL 0x4a, JOY_BAUD 0x4e) + ISTAT bit 7 (ack) + devices on port 0 (pad / memory card) as the BIOS-less driver uses them"""
    def __init__(s,card=None):
        s.ctrl=0; s.rx=0xff; s.rxfull=False; s.ack=False; s.port=0; s.dev=None; s.idx=0; s.n=0; s.buf=[]; s.sel=False
        s.pad_mask=0; s.pad_mode='digital'; s.cfg=False; s.sticks=(128,128,128,128); s.pad_fn=None
        s.card=bytearray(open(card,'rb').read()) if card else None; s.card_path=card; s.cflag=0x08; s.cdirty=False
        s.ncard_r=s.ncard_w=s.npoll=0; s.cur=None
    # ---- pad
    def pad_id(s): return 0xf3 if s.cfg else (0x73 if s.pad_mode=='analog' else 0x41)
    def pad_bytes(s):
        m=(~s.pad_fn()&0xffff) if s.pad_fn else 0xffff
        out=[0xff,s.pad_id(),0x5a,m&255,m>>8]
        if s.cfg or s.pad_mode=='analog': out+=list(s.sticks)
        return out
    # ---- card
    def card_start(s,cmd):
        c=s.card
        if cmd==0x52:
            s.cur=('r',None); return 140
        if cmd==0x57: s.cur=('w',None); return 138
        s.cur=None; return 3
    def byte(s,b):
        """one byte written to JOY_DATA -> (reply byte, device expects more bytes)"""
        if s.idx==0:
            s.dev=None
            if s.port==0 and b==0x01: s.dev='pad'
            elif s.port==0 and b==0x81 and s.card is not None: s.dev='card'
            else: return 0xff,False
            s.buf=[b]; s.idx=1
            if s.dev=='pad': return 0xff,True
            return 0xff,True
        i=s.idx; s.buf.append(b); s.idx+=1
        if s.dev=='pad':
            if i==1:                      # command byte
                s.cmd=b
                if b==0x42: s.resp=s.pad_bytes(); s.npoll+=1
                elif b==0x43: s.resp=[0xff,s.pad_id(),0x5a,0,0,0,0,0,0]
                elif b==0x44: s.resp=[0xff,s.pad_id(),0x5a,0,0,0,0,0,0]
                else: s.resp=[0xff,s.pad_id(),0x5a,0,0,0,0,0,0]
                s.n=len(s.resp) if b==0x42 else 9
                if s.cfg and b==0x42: s.n=9
                if b==0x42 and not s.cfg and s.pad_mode=='digital': s.n=5
                return s.resp[1],True
            r=s.resp[i] if i<len(s.resp) else 0
            if i==s.n-1:
                if s.cmd==0x43 and len(s.buf)>=4: s.cfg=(s.buf[3]==1)
                if s.cmd==0x44 and s.cfg: s.pad_mode='analog' if s.buf[3]==1 else 'digital'
            return r,i<s.n-1
        # memory card
        if i==1:
            s.n=s.card_start(b); s.cmdb=b
            return s.cflag,True
        cmd=s.cmdb
        if cmd not in (0x52,0x57): return 0xff,i<s.n-1
        if cmd==0x52:
            if i==2: return 0x5a,True
            if i==3: return 0x5d,True
            if i==4: s.f=b<<8; return 0,True
            if i==5: s.f|=b; return s.f>>8,True
            if i==6: return 0x5c,True
            if i==7: return 0x5d,True
            if i==8: return s.f>>8,True
            if i==9: return s.f&255,True
            if i<138:
                if i==10:
                    s.data=bytes(s.card[s.f*128:s.f*128+128]) if s.f<1024 else b'\0'*128; s.chk=(s.f>>8)^(s.f&255)
                    for x in s.data: s.chk^=x
                    s.ncard_r+=1; s.cflag=0
                return s.data[i-10],True
            if i==138: return s.chk&255,True
            return 0x47,False
        # write
        if i==2: return 0x5a,True
        if i==3: return 0x5d,True
        if i==4: s.f=b<<8; return 0,True
        if i==5: s.f|=b; return s.f>>8,True
        if i<134: return b if False else 0,True
        if i==134:
            d=bytes(s.buf[6:134]); c=(s.f>>8)^(s.f&255)
            for x in d: c^=x
            s.wok=(c==b and s.f<1024)
            if s.wok:
                s.card[s.f*128:s.f*128+128]=d; s.cdirty=True; s.ncard_w+=1; s.cflag=0
            return 0,True
        if i==135: return 0x5c,True
        if i==136: return 0x5d,True
        return (0x47 if s.wok else 0x4e),False
    def save_card(s,path=None):
        p=path or s.card_path
        if p and s.card is not None: open(p,'wb').write(bytes(s.card)); s.cdirty=False
    # ---- registers
    def rd(s,off,size):
        if off==0x40:
            v=s.rx; s.rxfull=False; return v
        if off==0x44: return 5|(2 if s.rxfull else 0)|(0x80|0x200 if s.ack else 0)
        if off==0x4a: return s.ctrl&~0x10
        return 0
    def wr(s,off,size,val):
        if off==0x40:
            if not (s.ctrl&2): return
            r,more=s.byte(val&0xff); s.rx=r; s.rxfull=True; s.ack=more
        elif off==0x4a:
            if val&0x10: s.ack=False
            s.ctrl=val
            if val&0x40: s.idx=0; s.dev=None; s.ack=False
            if not (val&2): s.idx=0; s.dev=None; s.ack=False; s.rxfull=False
            s.port=(val>>13)&1
class Sim13:
    def __init__(s,exe,iso,elf,card=None,ram=0x1000000):
        e=open(exe,'rb').read(); pc0,gp,ta,ts=struct.unpack_from('<IIII',e,0x10)
        u=s.u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN); u.mem_map(0,ram)
        d=open(iso,'rb').read(); u.mem_map(0x10000000,(len(d)+0xfff)&~0xfff); u.mem_write(0x10000000,d)
        u.mem_write(ta&0x1fffffff,e[0x800:0x800+ts]); s.out=bytearray(); s.rc=0
        s.sio=Sio(card)
        def r(uc,off,size,ud):
            a=0x1f801000+off
            if 0x1f801040<=a<0x1f801050: return s.sio.rd(a-0x1f801000,size)
            if a==0x1f801814: return 0x1c000000
            if a==0x1f801070: return 1|(0x80 if s.sio.ack else 0)
            if a==0x1f801110: s.rc=(s.rc+7)&0xffff; return s.rc
            return 0
        def w(uc,off,size,val,ud):
            a=0x1f801000+off
            if 0x1f801040<=a<0x1f801050: s.sio.wr(a-0x1f801000,size,val)
            elif a==0x1f801070 and not (val&0x80): s.sio.ack=False
        u.mmio_map(0x1f801000,0x1000,r,None,w,None); u.mem_map(0x1f000000,0x10000)
        def a0(uc,addr,sz,ud):
            if uc.reg_read(UC_MIPS_REG_9)==0x3c: s.out.append(uc.reg_read(UC_MIPS_REG_4)&0xff)
            uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_31))
        u.hook_add(UC_HOOK_CODE,a0,None,0xa0,0xa0)
        nm=subprocess.run(['llvm-nm','-n',elf],capture_output=True,text=True).stdout
        s.sym={l.split()[2]:int(l.split()[0],16) for l in nm.splitlines() if len(l.split())==3}
        s.pc0=pc0; u.reg_write(UC_MIPS_REG_29,0x801fd000); s.vbl=0; s.cb=None
        u.hook_add(UC_HOOK_CODE,s._v,None,s.sym['present'],s.sym['present'])
    @property
    def pad(s): return s.sio.pad_fn
    @pad.setter
    def pad(s,f): s.sio.pad_fn=f
    def _v(s,uc,a,sz,ud):
        s.vbl+=1
        if s.cb and s.cb(s): uc.emu_stop()
    def rd(s,a,n): return bytes(s.u.mem_read(a&0x1fffffff,n))
    def r32(s,a): return struct.unpack('<I',s.rd(a,4))[0]
    def r16(s,a): return struct.unpack('<H',s.rd(a,2))[0]
    def r8(s,a): return s.rd(a,1)[0]
    def s32(s,a): v=s.r32(a); return v-(1<<32) if v&0x80000000 else v
    def s16(s,a): v=s.r16(a); return v-(1<<16) if v&0x8000 else v
    def w32(s,a,v): s.u.mem_write(a&0x1fffffff,struct.pack('<I',v&0xffffffff))
    def sv(s,n): return s.sym[n]
    def gframe(s): return s.r32(s.sym['io_cyc'])//280896
    def run(s,pc=None,count=4000000000):
        try: s.u.emu_start(pc if pc is not None else s.pc0,0,count=count)
        except UcError as e: print('exc',e,hex(s.u.reg_read(UC_MIPS_REG_PC)))
    # ---- guest game state (Payback's memory as the translated guest holds it)
    def state(s):
        d=dict(clk=s.r32(EW+0x1e00),map=s.s16(EW+0x1d40),nl=s.s16(IW+0xc),ci=s.s16(EW+0x1db8),gf=s.gframe())
        nl,ci=d['nl'],d['ci']
        if 0<=ci<=nl<=100:
            p=s.r32(IW+0xc60+4*ci)
            if EW<=p<EW+0x40000:
                o=p-EW; d.update(x=s.s32(EW+o+4),z=s.s32(EW+o+8),y=s.r16(EW+o+0xc),hd=s.s16(EW+o+0x12),hp=s.s16(EW+o+0x68),score=s.s32(EW+o+0x90),defp=s.r32(EW+o+0x1c))
                dp=d['defp']
                if 0x08354af4<=dp<0x08354af4+128*0x3c: d['cls']=None
        return d
