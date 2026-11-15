#!/usr/bin/env python3
"""simsession.py: scripted REAL-PAD session on the unicorn sim (SIM-ONLY, no GTE/GPU): the runtime's real pad driver reads a modelled DualShock, the guest (translated Payback) reacts.
No menu assist is involved in the level: the pad function below is the only input after the level clock starts.  The menu part is driven by the same pad function (no -DKPLAN build),
using Payback's own screens' timings from the stock game (the plan is passed as pad presses from this script, not compiled into the runtime).
usage: simsession.py EXE_NAME CARD.mcd OUT_PREFIX LEVEL_FRAMES [--poke-car]
Phases (guest frames since the level clock first runs): walk, turn L/R, walk+turn, reverse (B via Square and Circle), weapon next/prev (Up/Down), shoot (R1), select, pause menu (Start, Down/Up, Cross),
car (TEST-ONLY poke of the controlled entity index to a traffic car, as the stage-7 TESTTOURCAR does; walking to an enterable car is not possible in a session this short): drive, steer, brake, horn (R1), exit (L1),
then free roaming with random pad changes up to LEVEL_FRAMES.  Metrics are printed and written to OUT_PREFIX.json."""
import sys,os,json,math,random,time,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))+'/../t')
from sim13 import *
BIT=dict(SELECT=1,START=8,UP=0x10,RIGHT=0x20,DOWN=0x40,LEFT=0x80,L2=0x100,R2=0x200,L1=0x400,R1=0x800,TRIANGLE=0x1000,CIRCLE=0x2000,CROSS=0x4000,SQUARE=0x8000)
TURN=5760.0
exe,card,outp,NL=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4])
POKE='--poke-car' in sys.argv; QTAIL=900
s=Sim13('out/%s.exe'%exe,'out/%s.iso'%exe,'out/bld_%s/payback.elf'%exe,card=card)
S=s.sym
# ---- menu plan (stock game's title -> rampage path with a BLANK save, mgba padlog) pressed from this script
MENU=[(360,366,'CROSS'),(426,432,'CROSS'),(492,498,'CROSS'),(558,564,'CROSS'),(624,630,'CROSS'),(750,756,'CROSS'),(836,842,'CROSS'),(902,908,'CROSS'),(968,974,'DOWN'),(998,1004,'DOWN'),(1028,1034,'CROSS'),(1094,1100,'CROSS')]
EEW=[]   # (gframe, off, len) of EEPROM writes
def hd(uc,a,sz,ud): EEW.append((s.gframe(),uc.reg_read(UC_MIPS_REG_4),uc.reg_read(UC_MIPS_REG_5)))
s.u.hook_add(UC_HOOK_CODE,hd,None,S['sv_dirty'],S['sv_dirty'])
# guest key word as the guest reads it (io_keys at each KEYINPUT read)
gk=collections.Counter(); lastk=[0x3ff]
# the guest key word is sampled inside pad() (one call per guest frame): io_keys then still holds the word the guest read in the PREVIOUS frame
def me_ent():
    nl=s.s16(IW+0xc); ci=s.s16(EW+0x1db8)
    if not(0<=ci<=nl<=100): return None
    p=s.r32(IW+0xc60+4*ci)
    if not(EW<=p<EW+0x40000): return None
    return p
def ent_info(p):
    dp=s.r32(p+0x1c); idx=(dp-0x08354af4)//0x3c if 0x08354af4<=dp<0x08354af4+128*0x3c else -1
    cls=0 if (0<=idx<=27 or 45<=idx<=48) else 1 if (38<=idx<=44 or 49<=idx<=65) else 2 if 28<=idx<=31 else 3 if 32<=idx<=81 else -1
    return dict(x=s.s32(p+4),z=s.s32(p+8),hd=s.s16(p+0x12),hp=s.s16(p+0x68),sc=s.s32(p+0x90),idx=idx,cls=cls,b8=s.r8(p+0xb8),flag4a=s.r8(p+0x4a),flag56=s.r8(p+0x56),y=s.r16(p+0xc))
def all_ents():
    nl=s.s16(IW+0xc); out=[]
    for i in range(nl+1):
        p=s.r32(IW+0xc60+4*i)
        if EW<=p<EW+0x40000:
            d=ent_info(p); d['i']=i; out.append(d)
    return out
class Sess:
    def __init__(z):
        z.lvl=None; z.t=0; z.res={}; z.log=[]; z.keys=set(); z.ph=0; z.pt=0; z.snap={}; z.rnd=random.Random(7); z.lastclk=0; z.poked=False; z.carphase=0
        z.pause_seen=None
    def pressed(z,*k): z.keys=set(k)
    def note(z,k,v): z.res[k]=v; print('RESULT',k,v,flush=True)
sess=Sess()
def me_state():
    p=me_ent()
    return ent_info(p) if p else None
PHASES=[]   # (name, frames, keys-func or keys, begin(), end())
def seq():
    st=lambda: me_state()
    P=[]
    def meas(name,keys,n,fn):
        P.append(dict(name=name,keys=keys,n=n,fn=fn))
    return P
P=[]
def add(name,keys,n,check=None,begin=None): P.append(dict(name=name,keys=keys,n=n,check=check,begin=begin))
def disp(a,b): return math.hypot(b['x']-a['x'],b['z']-a['z'])
def dh(a,b): return ((b['hd']-a['hd']+TURN/2)%TURN)-TURN/2
add('settle',(),30)
add('walk (Cross=A)',('CROSS',),60,lambda a,b,k: ('disp %d raw units'%disp(a,b), disp(a,b)>300))
add('turn left (Left)',('LEFT',),30,lambda a,b,k: ('dheading %+d (1/5760 turn)'%dh(a,b), dh(a,b)>500))
add('turn right (Right)',('RIGHT',),30,lambda a,b,k: ('dheading %+d'%dh(a,b), dh(a,b)<-500))
add('walk+turn (Cross+Left)',('CROSS','LEFT'),45,lambda a,b,k: ('disp %d dheading %+d'%(disp(a,b),dh(a,b)), disp(a,b)>300 and dh(a,b)>500))
add('reverse/brake (Square=B)',('SQUARE',),30,lambda a,b,k: ('disp %d'%disp(a,b), True))
add('reverse/brake (Circle=B)',('CIRCLE',),30,lambda a,b,k: ('disp %d'%disp(a,b), True))
add('idle',(),20)
add('next weapon (Up)',('UP',),8,lambda a,b,k: ('guest key word cleared bit6: %s'%(any(not(w&0x40) for w in k)), any(not(w&0x40) for w in k)))
add('idle',(),20)
add('prev weapon (Down)',('DOWN',),8,lambda a,b,k: ('guest key word cleared bit7: %s'%(any(not(w&0x80) for w in k)), any(not(w&0x80) for w in k)))
add('idle',(),20)
add('shoot (R1=R)',('R1',),14,lambda a,b,k: ('guest key bit8 %s, entity b8 %d->%d, def %d->%d'%(any(not(w&0x100) for w in k),a['b8'],b['b8'],a['idx'],b['idx']), any(not(w&0x100) for w in k) and (a['b8']!=b['b8'] or a['idx']!=b['idx'])))
add('idle',(),60)
add('select',('SELECT',),8,lambda a,b,k: ('guest key bit2 cleared %s'%any(not(w&4) for w in k), any(not(w&4) for w in k)))
add('idle',(),20)
add('enter/exit (L1=L) on foot, no car near',('L1',),8,lambda a,b,k: ('guest key bit9 %s, entity flags 4a %d->%d 56 %d->%d'%(any(not(w&0x200) for w in k),a['flag4a'],b['flag4a'],a['flag56'],b['flag56']), any(not(w&0x200) for w in k)))
add('idle',(),60)
PAUSE_AT=len(P)
add('pause (Start)',('START',),8,None)
add('paused wait',(),60,None)
add('pause menu Down',('DOWN',),6,None)
add('idle',(),20)
add('pause menu Up',('UP',),6,None)
add('idle',(),20)
add('resume (Cross on Return to game)',('CROSS',),6,None)
add('after resume',(),60,None)
CARPH=len(P)
if POKE:
    add('car: poke controlled entity (TEST-ONLY)',(),5,None)
    add('car drive (Cross)',('CROSS',),90,lambda a,b,k: ('disp %d raw units, cls %d'%(disp(a,b),b['cls']), None))
    add('car steer left',('CROSS','LEFT'),40,lambda a,b,k: ('dheading %+d disp %d'%(dh(a,b),disp(a,b)), None))
    add('car steer right',('CROSS','RIGHT'),40,lambda a,b,k: ('dheading %+d disp %d'%(dh(a,b),disp(a,b)), None))
    add('car brake/reverse (Square=B)',('SQUARE',),60,lambda a,b,k: ('disp %d'%disp(a,b), True))
    add('car horn (R1)',('R1',),12,lambda a,b,k: ('guest key bit8 %s'%any(not(w&0x100) for w in k), any(not(w&0x100) for w in k)))
    add('car drive again',('CROSS',),60,None)
    add('exit car (L1)',('L1',),10,lambda a,b,k: ('controlled cls %d -> %d'%(a['cls'],b['cls']), True))
    add('after exit',(),60,None)
class Walker: pass
cur=dict(i=0,t0=0,a=None,k=[])
def pad():
    f=s.gframe(); m=0
    lastk[0]=s.r32(S['io_keys'])&0x3ff; gk[lastk[0]]+=1
    if sess.lvl is None:
        if s.r32(EW+0x1e00): sess.lvl=f; sess.t0=f; print('LEVEL clock runs at gframe',f,flush=True)
        else:
            for a,b,k in MENU:
                if a<=f<b: m|=BIT[k]
            return m
    t=f-sess.lvl
    # phase machine
    if cur['i']<len(P):
        ph=P[cur['i']]
        if cur['a'] is None:
            cur['a']=me_state(); cur['t0']=f; cur['k']=[]
            if ph['name'].startswith('car: poke') and cur['a'] is not None:
                # TEST-ONLY: the controlled entity index becomes a moving traffic car (stage-7 TESTTOURCAR does the same)
                es=all_ents(); cars=[e for e in es if e['cls']==0]
                if cars:
                    best=min(cars,key=lambda e:math.hypot(e['x']-cur['a']['x'],e['z']-cur['a']['z']))
                    s.u.mem_write((EW+0x1db8)&0x1fffffff,struct.pack('<H',best['i'])); print('TEST-ONLY poke: controlled index ->',best['i'],'def',best['idx'],flush=True)
        for kk in ph['keys']: m|=BIT[kk]
        cur['k'].append(lastk[0])
        if f-cur['t0']>=ph['n']:
            b=me_state()
            if ph['check'] and cur['a'] and b:
                txt,ok=ph['check'](cur['a'],b,cur['k']); sess.note(ph['name'],dict(ok=(None if ok is None else bool(ok)),detail=txt,gf=f))
            elif ph['name'].startswith('pause') or ph['name'].startswith('resume') or ph['name'].startswith('after resume') or ph['name'].startswith('paused'):
                c=s.r32(EW+0x1e00); sess.log.append((ph['name'],c,f))
                print('  ',ph['name'],'clock',c,flush=True)
            cur['i']+=1; cur['a']=None
        return m
    if t>=NL:
        if sess.qstart is None:
            sess.qstart=f; sess.eew0=len(EEW); sess.cw0=s.sio.ncard_w; print('QUIT sequence starts gframe',f,'level clk',s.r32(EW+0x1e00),'eeprom writes so far',len(EEW),flush=True)
        q=f-sess.qstart
        if 0<=q<8: m|=BIT['START']
        elif 40<=q<46: m|=BIT['DOWN']
        elif 70<=q<76: m|=BIT['CROSS']
        elif 100<=q<106: m|=BIT['LEFT']
        elif 130<=q<136: m|=BIT['CROSS']
        return m
    # free roaming after the script: change keys every 20-70 frames, mostly walking
    if f>=sess.nextchg:
        r=sess.rnd.random(); sess.free=set(['CROSS']) if r<0.55 else set(['CROSS','LEFT']) if r<0.7 else set(['CROSS','RIGHT']) if r<0.85 else set(['SQUARE']) if r<0.9 else set(['R1','CROSS']) if r<0.95 else set(['UP','DOWN'][sess.rnd.randint(0,1):][:1])
        sess.nextchg=f+sess.rnd.randint(20,70)
    for kk in sess.free: m|=BIT[kk]
    return m
sess.nextchg=0; sess.free=set(); sess.qstart=None
s.pad=pad
T0=time.time(); last=[0]
def cb(st):
    f=st.gframe()
    if sess.qstart is not None and f-sess.qstart>=QTAIL: return True
    if f//500!=last[0]//500:
        last[0]=f; ms=me_state(); print('gf',f,'wall %.0f'%(time.time()-T0),'clk',st.r32(EW+0x1e00),'me',ms and (ms['x'],ms['z'],ms['hd'],ms['hp'],ms['sc'],ms['cls']),flush=True)
    return False
s.cb=cb
s.run(count=60000000000)
o=s.out.decode('latin1')
bad=[l for l in o.split('\n') if l.startswith(('BADRD','BADWR','RT_MISS','SF3 CONFLICT'))]
s.sio.save_card()
ee=s.rd(S['ee'],8192); open(outp+'.ee','wb').write(ee)
res=dict(quit_eeprom_writes=len(EEW)-sess.eew0 if sess.qstart is not None else None,quit_card_writes=s.sio.ncard_w-sess.cw0 if sess.qstart is not None else None,quit_start=sess.qstart,ee_nonff=sum(1 for b in ee if b!=0xff),results=sess.res,level_start=sess.lvl,end_gframe=s.gframe(),wall=round(time.time()-T0),eeprom_writes=EEW[:200],n_eeprom_writes=len(EEW),pad_polls=s.sio.npoll,card_reads=s.sio.ncard_r,card_writes=s.sio.ncard_w,
         bad_lines=bad[:10],guest_key_words={('%03x'%k):v for k,v in gk.most_common(40)},pause_log=sess.log)
json.dump(res,open(outp+'.json','w'),indent=1)
open(outp+'.psxout','wb').write(bytes(s.out))
print('DONE end gframe',s.gframe(),'level frames',s.gframe()-(sess.lvl or 0),'wall',res['wall'],'polls',s.sio.npoll,'bad',len(bad))
for k,v in sess.res.items(): print(' ',k,v)
