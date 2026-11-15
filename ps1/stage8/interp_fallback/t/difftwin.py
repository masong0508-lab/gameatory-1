#!/usr/bin/env python3
"""TEST-ONLY unicorn soak (stage 7): runs the PS1 sim build (SIMKEYS, CDSIM) from power-on through the menus into the level and keeps playing a long scripted+random
session (walk, entity swaps, pause menu, deaths, game over, new rampage on every city/difficulty, game menu items), logging counters.  A fault = any unicorn exception, a guest panic string, BADRD/BADWR, or a stalled game clock.
usage: soak.py VARIANT GBA_FRAMES OUT.json [seed] [start_frame_offset]"""
import sys,json,time,random,struct
sys.path.insert(0,'t'); import os
from sim4 import *
from unicorn.mips_const import *
V=sys.argv[1]; FR=int(sys.argv[2]); OUTJ=sys.argv[3]; SEED=int(sys.argv[4]) if len(sys.argv)>4 else 1
s=Sim('out/%s.exe'%V,'out/%s.iso'%V,'out/bld_%s/payback.elf'%V); sym=s.sym; CY=sym['io_cyc']; SK=sym['sim_keys']
rnd=random.Random(SEED)
A,B,SEL,STA,RT,LF,UP,DN,R,L=1,2,4,8,16,32,64,128,256,512
KPL=[(360,366,A),(426,432,A),(492,498,A),(558,564,A),(624,630,A),(750,756,A),(836,842,A),(902,908,A),(968,974,DN),(998,1004,DN),(1028,1034,A),(1094,1100,A)]   # the stock menu plan (power-on to the level)
W_FOOT=dict(A=0.55,B=0.08,LEFT=0.25,RIGHT=0.25,R=0.30,L=0.06,UP=0.12,DOWN=0.12)
BIT=dict(A=A,B=B,LEFT=LF,RIGHT=RT,R=R,L=L,UP=UP,DOWN=DN,START=STA)
def pad(w): 
    m=0
    for k,p in w.items():
        if rnd.random()<p: m|=BIT[k]
    return m
EWH,IWH=0x801b0000,0x801f0000
def safe(f,*a):
    try: return f(*a)
    except Exception as e: return None
def r16(a): return s.r16(a)
def r32(a): return s.r32(a)
def w16(a,v): s.u.mem_write(a&0x1fffffff,struct.pack('<H',v&0xffff))
def w8(a,v): s.u.mem_write(a&0x1fffffff,bytes([v&0xff]))
def clock(): return r32(EWH+0x1e00)
def nent(): return r16(IWH+0xc)+1
def ctrl(): return r16(EWH+0x1db8)
class Script:
    """generator of (mask, frames) segments; frames are GBA frames (io_cyc/280896)"""
    def __init__(self): self.g=self.run(); self.mask=0; self.until=0; self.stats=dict(levels=0,swaps=0,pauses=0,deaths=0,gameovers=0,menus=0,maps=set())
    def tap(self,m,hold=6,wait=40): return [(m,hold),(0,wait)]
    def level_session(self,frames):
        done=0
        while done<frames and clock()>0:
            seg=rnd.randint(10,50)
            yield (pad(W_FOOT),seg); done+=seg
            if rnd.random()<0.02 and clock()>0:
                n=nent(); w16(EWH+0x1db8,rnd.randrange(0,max(1,n))); self.stats['swaps']+=1
            if rnd.random()<0.006 and clock()>0:
                self.stats['pauses']+=1
                for x in self.tap(STA,8,40): yield x
                for _ in range(rnd.randint(0,4)):
                    for x in self.tap(rnd.choice([UP,DN]),6,20): yield x
                if rnd.random()<0.2: 
                    for x in self.tap(A,6,40): yield x     # Return to game (or whatever is selected)
                else:
                    for x in self.tap(STA,8,40): yield x
            if rnd.random()<0.003 and clock()>0:
                p=r32(IWH+0xc60+4*ctrl())
                if (p>>24)==0x80 or (p>>24)==0x01 or p>=0x801b0000 and p<0x801f0000: w16(p+0x68,0)
                self.stats['deaths']+=1
    def run(self):
        t=0     # stage 8: the production disc resumes inside a running level (snapshot): no boot plan
        while True:
            # wait for the level
            for _ in range(60):
                if clock()>0: break
                yield (0,30)
            if clock()==0:
                for x in self.tap(A,6,120): yield x
                continue
            self.stats['levels']+=1; self.stats['maps'].add(r16(EWH+0x1d40))
            yield from self.level_session(rnd.choice([3000,6000,9000]))
            # end the session: lives 0 and kill -> game over -> continue -> game menu
            self.stats['gameovers']+=1
            for _ in range(6):
                if clock()==0: break
                w8(EWH+0x1e4e,0); p=r32(IWH+0xc60+4*ctrl()); w16(p+0x68,0); yield (0,300)
            for _ in range(10): yield (A if rnd.random()<0.5 else 0,60)
            # game menu: random menu items sometimes, else rampage on a random city / difficulty
            self.stats['menus']+=1
            if rnd.random()<0.25:
                for _ in range(rnd.randint(3,10)):
                    yield from self.tap(rnd.choice([UP,DN,A,B,LF,RT]),6,rnd.choice([20,40,80]))
                for _ in range(6): yield from self.tap(B,6,60)
            city=rnd.randrange(3); diff=rnd.randrange(5)
            for m in (DN,DN): yield from self.tap(m)
            yield from self.tap(A,6,60)
            for m in [UP,UP]+[RT]*city+[DN]+[RT]*diff+[DN]: yield from self.tap(m)
            yield from self.tap(A,6,600)
            for _ in range(3):
                if clock()>0: break
                yield from self.tap(A,6,120)
WA=os.environ.get('WATCH') if 'os' in dir() else None
import os
WA=os.environ.get('WATCH')
WLOG=[]
if WA:
    wa=int(WA,16)
    def _mw(uc,acc,a,sz,v,ud):
        WLOG.append('W %x sz%d v=%x pc=%x ra=%x f=%d'%(a,sz,v&0xffffffff,uc.reg_read(UC_MIPS_REG_PC),uc.reg_read(UC_MIPS_REG_31),s.r32(CY)//280896))
    s.u.hook_add(UC_HOOK_MEM_WRITE,_mw,None,wa,wa+3)
import zlib,numpy as _np
LO_STK,HI_STK=0x8002c000,0x80030000
s.u.mem_write(LO_STK&0x1fffffff,b'\xa5'*(HI_STK-LO_STK))      # stack watermark for the interpreter's C stacks (16 depths x 1 KiB)
NIO=[0,0]
def iow(uc,a,sz,ud):
    off=uc.reg_read(UC_MIPS_REG_4); size=uc.reg_read(UC_MIPS_REG_5); val=uc.reg_read(UC_MIPS_REG_6)
    if size<4: val&=(1<<(8*size))-1
    NIO[0]+=1; NIO[1]=zlib.crc32(struct.pack('<III',off,size,val&0xffffffff),NIO[1])
s.u.hook_add(UC_HOOK_CODE,iow,None,sym['io_write'],sym['io_write'])
def normh():
    d=_np.frombuffer(s.rd(EWH,0x40000)+s.rd(IWH,0x8000),dtype='<u4').copy()
    top=d>>24
    reg=((top==2)&(d<=0x02040000))|((top==3))
    d=_np.where(reg,0x11111111,d)
    host=((d>=0x801b0000)&(d<0x801f8000)); d=_np.where(host,0x11111111,d)
    d=_np.where(((top==0x80)|(top==0x08))&~host,0x22222222,d)
    h=zlib.crc32(d.tobytes())
    for a,n in ((0x80180000,0x400),(0x80180400,0x400),(0x80181000,0x18000)): h=zlib.crc32(s.rd(a,n),h)
    return h&0xffffffff
HL=[]
sc=Script(); st=dict(until=0,mask=0,f=0,last_clk_f=0,last_clk=0,fault=None,rows=[],T=time.time(),insn=0)
IPL=[]
if 'interp_top' in sym:
    def _it(uc,a,sz,ud):
        g=uc.reg_read(UC_MIPS_REG_4); r=[s.r32(g+4*i) for i in range(19)]
        IPL.append('IT pc %08x lr %08x sp %08x r0-3 %08x %08x %08x %08x r4-7 %08x %08x %08x %08x r8-12 %08x %08x %08x %08x %08x'%(r[17],r[14],r[13],r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[9],r[10],r[11],r[12]))
        if len(IPL)>400: del IPL[:200]
    def _rp(uc,a,sz,ud):
        IPL.append('PUSH S %08x L %08x'%(uc.reg_read(UC_MIPS_REG_4),uc.reg_read(UC_MIPS_REG_5)))
    s.u.hook_add(UC_HOOK_CODE,_it,None,sym['interp_top'],sym['interp_top']); s.u.hook_add(UC_HOOK_CODE,_rp,None,sym['ip_res_push'],sym['ip_res_push'])
RING=[0]*80
def blk(uc,a,sz,ud):
    st['insn']+=sz//4; RING.pop(0); RING.append(a)
s.u.hook_add(UC_HOOK_BLOCK,blk)
def cb(s):
    f=r32(CY)//280896; st['f']=f
    while f>=st['until']:
        try: m,n=next(sc.g)
        except StopIteration: return True
        st['mask']=m; st['until']=max(f,st['until'])+n; 
        if n==0: continue
    s.u.mem_write(SK&0x1fffffff,struct.pack('<I',0x3ff&~st['mask']))
    HL.append((len(HL)+1,f,normh(),NIO[0],NIO[1]))
    try:
        if clock()>0:
            ci=ctrl(); pe=r32(IWH+0xc60+4*ci)
            if 0x801b0000<=pe<0x801f0000 or (pe>>24)==2:
                pe=(pe-0x02000000+0x801b0000) if (pe>>24)==2 else pe
                dsc=r32(pe+0x1c); st.setdefault('desc',{}); st['desc'][dsc]=st['desc'].get(dsc,0)+1; st.setdefault('maps',set()).add(r16(EWH+0x1d40))
    except Exception: pass
    if f>=st.get('nl',0):
        st['nl']=(f//500+1)*500
        c=clock(); row=dict(f=f,clk=c,map=r16(EWH+0x1d40),nent=nent(),insn=st['insn'],sec=time.time()-st['T'])
        for n in ('ip_enters','ip_undef','ip_swis','ip_depth_max','cold_loads','cold_calls','ip_stat_steps','ip_stat_calls','ip_rec_hi','rom_miss_count','cd_sectors'):
            if n in sym: row[n]=r32(sym[n])
        st['rows'].append(row)
        print('f',f,'clk',c,'map',row['map'],'nent',row['nent'],'insn %.2fG'%(st['insn']/1e9),'interp',row.get('ip_enters'),'cold',row.get('cold_loads'),'t %.0f'%row['sec'],flush=True)
        json.dump(dict(rows=st['rows'],stats={k:(sorted(v) if isinstance(v,set) else v) for k,v in sc.stats.items()}),open(OUTJ,'w')); import pickle; pickle.dump(HL,open(OUTJ+'.h','wb'))
    return f>=FR
s.cb=cb
import os
TO=int(os.environ.get('SOAKTO','0'))*1000000
try: s.u.emu_start(s.pc0,0,timeout=TO,count=400000000000)
except UcError as e: st['fault']='unicorn exception %s at pc %08x ra %08x'%(e,s.u.reg_read(UC_MIPS_REG_PC),s.u.reg_read(UC_MIPS_REG_31))
FD=None
if st['fault'] and 'ipst' not in str(FD):
    from capstone import *
    R=[s.u.reg_read(getattr(__import__('unicorn.mips_const',fromlist=['x']),'UC_MIPS_REG_%d'%i)) for i in range(32)]
    FD=dict(regs=['%08x'%x for x in R])
    ra=R[31]; pcv=s.u.reg_read(UC_MIPS_REG_PC); FD['pc']='%08x'%pcv
    cb_=safe(s.rd,ra-48,64); FD['code']=[ '%x %s %s'%(i.address,i.mnemonic,i.op_str) for i in Cs(CS_ARCH_MIPS,CS_MODE_MIPS32+CS_MODE_LITTLE_ENDIAN).disasm(cb_,ra-48)] if cb_ else []
    FD['stack']=[ (lambda v:'%08x'%struct.unpack('<I',v)[0] if v else 'unmapped')(safe(s.rd,R[29]+4*k,4)) for k in range(24)]
    FD['iplog']=IPL[-40:]; FD['ring']=['%08x'%x for x in RING];     FD['ipst']=dict(depth=safe(s.r32,sym['ip_depth']),rec_n=safe(s.r32,sym['ip_rec_n']),rec_hi=safe(s.r32,sym['ip_rec_hi']))
    print(json.dumps(FD))
if not st['fault'] and st['f']<FR:
    st['fault']='STALL (emulation returned early / timeout) pc %08x'%s.u.reg_read(UC_MIPS_REG_PC)
out=s.out.decode('latin1'); bad=[l for l in out.splitlines() if 'BADRD' in l or 'BADWR' in l or 'RT_MISS' in l or 'panic' in l.lower() or 'overflow' in l.lower() or 'CONFLICT' in l or 'INTERP depth' in l or 'resume stack' in l]
res=dict(fdump=FD,rows=st['rows'],fault=st['fault'],bad_lines=bad[:20],n_bad=len(bad),sec=time.time()-st['T'],insn=st['insn'],stats={k:(sorted(v) if isinstance(v,set) else v) for k,v in sc.stats.items()},frames=st['f'],out_tail=out[-1500:],interp_lines=[l for l in out.splitlines() if l.startswith('INTERP')][:200],cold_loads=[l for l in out.splitlines() if l.startswith('COLD')][:300])
json.dump(res,open(OUTJ,'w'))
wm=[]
_stk=s.rd(LO_STK,HI_STK-LO_STK)
for dd in range(16):
    blk_=_stk[dd*1024:(dd+1)*1024]; lowest=next((i for i in range(0,1024,4) if blk_[i:i+4]!=b'\xa5'*4),1024); wm.append(1024-lowest)
res['stack_used_bytes_per_depth']=wm; res['controlled_descriptors']={('%08x'%k):v for k,v in st.get('desc',{}).items()}; res['maps_seen']=sorted(st.get('maps',[]))
import pickle; pickle.dump(HL,open(OUTJ+'.h','wb'))
json.dump(res,open(OUTJ,'w'))
print('stack high-water bytes per depth',wm)
print('\n'.join(WLOG[-12:]));print('SOAK done frames',st['f'],'fault',st['fault'],'bad lines',len(bad),'insns %.2fG'%(st['insn']/1e9),'sec %.0f'%res['sec'])
