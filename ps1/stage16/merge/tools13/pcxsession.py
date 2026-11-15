#!/usr/bin/env python3
"""pcxsession.py: scripted REAL-KEY session of a Payback PS1 test disc in PCSXR (EMULATOR-ONLY, HLE BIOS; Xvfb + xdotool keys through DFInput's default keyboard map).
The disc's menu assist (stock title -> rampage path) brings the game to the level; from the level clock on the assist returns no key, every input is a pad press made here.
State comes from the runtime's PADDBG log lines (GS = controlled entity as Payback holds it, GN = nearest car / pedestrian), holds are counted in guest frames (GS gf), screenshots are taken of the emulator window.
Needs a disc built with -DPADDBG -DTESTPOKE (Select pokes the controlled entity index to the nearest traffic car: TEST-ONLY, a walk to an enterable car is not reliable).
usage: pcxsession.py disc.cue home out_prefix [max_seconds]"""
import sys,os,time,re,json,math
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import pcx
SHORT='--short' in sys.argv; A=[a for a in sys.argv[1:] if not a.startswith('--')]
cue,home,out=A[0:3]; MAXS=int(A[3]) if len(A)>3 else 5400   # --short: keys, pause and renderer-recovery checks only (no walk to entities, no TEST-ONLY car)
GS=re.compile(r'GS gf (\d+)\s*clk (\d+)\s*ci (\d+)\s*nl (\d+)\s*x (-?\d+)\s*z (-?\d+)\s*hd (\d+)\s*hp (-?\d+)\s*sc (-?\d+)\s*def (-?\d+)\s*cls (\d+)\s*pad ([0-9a-fA-Fx]+)\s*key ([0-9a-fA-Fx]+)')
GN=re.compile(r'GN cars (\d+)\s*peds (\d+)\s*(?:car (\d+)\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(-?\d+)\s*)?(?:ped (\d+)\s+(-?\d+)\s+(-?\d+))?')
r=pcx.Run(cue,home,out)
res={}; ev=[]; S=dict(gs=None,gn=None,pos=0)
def pump():
    """consume new log lines: update latest GS / GN, collect events"""
    with r.lk: L=r.lines[S['pos']:]; S['pos']+=len(L)
    n=0
    for t,l in L:
        m=GS.search(l)
        if m:
            g=m.groups(); S['gs']=dict(gf=int(g[0]),clk=int(g[1]),ci=int(g[2]),nl=int(g[3]),x=int(g[4]),z=int(g[5]),hd=int(g[6]),hp=int(g[7]),sc=int(g[8]),df=int(g[9]),cls=int(g[10]),pad=int(g[11].replace('0x',''),16),key=int(g[12].replace('0x',''),16),t=t); n+=1; S.setdefault('hist',[]).append(S['gs']); continue
        m=GN.search(l)
        if m:
            g=m.groups(); S['gn']=dict(cars=int(g[0]),peds=int(g[1]),car=g[2] and (int(g[2]),int(g[3]),int(g[4]),int(g[5]),int(g[6])),ped=g[7] and (int(g[7]),int(g[8]),int(g[9]))); continue
        if re.search(r'DOLL|MAPCHANGE|TEST-ONLY|sf3_ok|PANIC|FAULT|RT_MISS|ASSIST|MC |SF3',l): ev.append((round(t),l.strip())); print('EV %6.0f %s'%(t,l.strip()),flush=True)
    return n
def gs():
    pump(); return S['gs']
def wait_frames(n,to=1800):
    g0=gs(); t0=time.time()
    while time.time()-t0<to and r.alive():
        g=gs()
        if g and g0 and g['gf']>=g0['gf']+n: return g
        time.sleep(0.25)
    return gs()
def wait_gs(to):
    t0=time.time()
    while time.time()-t0<to and r.alive():
        if gs(): return True
        time.sleep(1)
    return False
shots=[]
def shot(name):
    p='%s_%s.png'%(out,name)
    for i in range(4):
        r.shot(p)
        try:
            from PIL import Image,ImageStat
            if ImageStat.Stat(Image.open(p).convert('L')).mean[0]>6: break
        except Exception: break
        time.sleep(1.5)
    shots.append(p)
def disp(a,b): return math.hypot(b['x']-a['x'],b['z']-a['z'])
def dh(a,b): return ((b['hd']-a['hd']+2880)%5760)-2880
def hold(name,keys,n,check=None,snap=False):
    """press keys, wait n guest frames, release; the GS lines in between give the guest's key word echo"""
    a=gs(); S['hist']=[]; h0=len(S.get('hist',[]))
    for k in keys: r.down(k)
    b=wait_frames(n)
    for k in keys: r.up(k)
    if snap: shot(name.replace(' ','_').replace('/','-').replace('(','').replace(')','').replace('=','')[:24])
    c=wait_frames(2)
    hist=list(S['hist'])
    kw=[h['key'] for h in hist]; pw=[h['pad'] for h in hist]
    d=dict(frames=(b['gf']-a['gf']) if a and b else None,disp=disp(a,c) if a and c else None,dheading=dh(a,c) if a and c else None,cls=(a['cls'],c['cls']) if a and c else None,df=(a['df'],c['df']) if a and c else None,
           pad_words=sorted(set('%04x'%x for x in pw)),guest_key_min=('%03x'%min(kw)) if kw else None,guest_key_words=sorted(set('%03x'%(x&0x3ff) for x in kw)),clk=(a['clk'],c['clk']) if a and c else None,gf=a and a['gf'])
    if check: d['ok']=bool(check(a,c,d));
    res[name]=d; print('RESULT',name,json.dumps(d),flush=True); return d
def pressed_bit(bit): return lambda a,c,d: any(not(int(w,16)&bit) for w in d['guest_key_words'])
try:
    t0=time.time()
    print('waiting for the level (assist boot) ...',flush=True)
    if not wait_gs(MAXS): print('NO LEVEL within',MAXS,'s'); raise SystemExit(1)
    g=gs(); print('LEVEL up after %.0f s: %s'%(time.time()-t0,g),flush=True); res['level_up_s']=round(time.time()-t0)
    res['assist_after_level']='the disc passes key 0x3ff (none) once the level clock runs; the first GS pad/key words below come from the real keys only'
    wait_frames(6); shot('start')
    hold('idle: no key pressed',[],4,lambda a,c,d: d['guest_key_words']==['3ff'])
    hold('walk (Cross=A)',['CROSS'],10,lambda a,c,d: d['disp'] and d['disp']>100 and 0x4000 in [int(x,16) for x in d['pad_words']],snap=True)
    hold('turn left (Left)',['LEFT'],6,lambda a,c,d: d['dheading'] is not None and d['dheading']>100)
    hold('turn right (Right)',['RIGHT'],6,lambda a,c,d: d['dheading'] is not None and d['dheading']<-100)
    hold('walk+turn (Cross+Left)',['CROSS','LEFT'],8,lambda a,c,d: d['disp']>100 and d['dheading']>100)
    hold('brake/reverse (Square=B)',['SQUARE'],4,pressed_bit(2))
    hold('brake/reverse (Circle=B)',['CIRCLE'],4,pressed_bit(2))
    hold('next weapon (Up)',['UP'],3,pressed_bit(0x40))
    hold('prev weapon (Down)',['DOWN'],3,pressed_bit(0x80))
    hold('shoot (R1=R)',['R1'],5,pressed_bit(0x100),snap=True)
    hold('enter/exit vehicle key (L1=L)',['L1'],3,pressed_bit(0x200))
    hold('Start (pause)',['START'],3,pressed_bit(8))
    g=wait_frames(20); res['pause_clock']=g['clk']; c0=g['clk']; g2=wait_frames(20); res['pause_clock_after_20_frames']=g2['clk']; shot('paused')
    hold('resume (Cross on Return to game)',['CROSS'],3,pressed_bit(1))
    g=wait_frames(20); res['clock_after_resume']=g['clk']; res['pause_works']=(g2['clk']-c0)<=1 and g['clk']>g2['clk']
    # Pause loads menu-only cold code over the renderer data (SF3 CONFLICT) and the runtime restores the renderer when the level runs again
    t1=time.time(); ok=False
    while time.time()-t1<900 and r.alive():
        pump()
        if any(('sf3_ok 1' in e[1] or 'restored from the world' in e[1]) and e[0]>res['level_up_s']+5 for e in ev[-12:]) and any(('re-init' in e[1] or 'restored from the world' in e[1]) for e in ev): ok=True; break
        time.sleep(2)
    res['renderer_back_after_pause']=ok; res['renderer_back_wait_s']=round(time.time()-t1)
    wait_frames(16); shot('after_pause_view')
    # walk to the nearest car / pedestrian (state-driven steering from GS/GN), screenshots whenever one is within the renderer's gather range
    TURN=5760.0
    def steer_to(tx,tz,g):
        des=math.atan2(tx-g['x'],tz-g['z'])/(2*math.pi)*TURN; err=(des-g['hd']+TURN/2)%TURN-TURN/2
        return ('LEFT' if err>250 else 'RIGHT' if err<-250 else None),abs(err)
    seen=dict(car=0,ped=0); walked=0
    for step in range(0 if SHORT else 40):
        g=gs(); pump(); gn=S['gn']
        if not gn: wait_frames(16); continue
        tgt=gn['car'] if gn['car'] else None
        d=None
        if tgt: d=abs(tgt[1]-g['x'])+abs(tgt[2]-g['z'])
        pd=(abs(gn['ped'][1]-g['x'])+abs(gn['ped'][2]-g['z'])) if gn['ped'] else None
        print('STEP',step,'me',(g['x'],g['z'],g['hd']),'nearest car',tgt and (tgt[0],tgt[4],d),'nearest ped',gn['ped'] and (gn['ped'][0],pd),flush=True)
        if d is not None and d<18000: seen['car']+=1; shot('ent_car%d'%step)
        if pd is not None and pd<18000: seen['ped']+=1; shot('ent_ped%d'%step)
        if d is not None and d<9000: break
        if tgt:
            k,e=steer_to(tgt[1],tgt[2],g)
            if k: hold('bot: turn %s toward car'%k,[k],2,None)
            else: hold('bot: walk toward car',['CROSS'],2,None); walked+=1
        else: hold('bot: walk (no car yet)',['CROSS'],2,None)
    res['entity_screens']=seen; res['bot_walk_holds']=walked
    if SHORT: raise SystemExit(0)
    # TEST-ONLY car: Select pokes the controlled index to the nearest traffic car (within the gather range); real Cross/Left/Right/Triangle afterwards
    r.mark(); hold('Select (TEST-ONLY poke to nearest car)',['SELECT'],2,pressed_bit(4)); pump(); time.sleep(1); pump()
    g=gs(); res['car_poke_state']=dict(cls=g['cls'],df=g['df'],ci=g['ci']); print('after poke',g,flush=True)
    hold('car drive (Cross)',['CROSS'],2,None,snap=True)
    hold('car steer left',['CROSS','LEFT'],2,None)
    hold('car steer right',['CROSS','RIGHT'],2,None)
    shot('car_view'); print('GN',S['gn'],flush=True)
    for i in range(6):
        hold('drive on %d'%i,['CROSS'],2,None)
        if any('DOLL hit' in e[1] for e in ev): break
    shot('car_view2')
    hold('bail out (Triangle)',['TRIANGLE'],2,lambda a,c,d: any('DOLL bail-out' in e[1] for e in ev),snap=True)
    for i in range(3): wait_frames(2); shot('after_bail%d'%i)
    pump(); res['events']=ev[-60:]
finally:
    pump(); res['shots']=shots; res['events']=ev[-80:]; res['wall_s']=round(time.time()-t0 if 't0' in dir() else 0)
    hist=S.get('hist',[])
    res['last_gs']=S['gs']
    json.dump(res,open(out+'.json','w'),indent=1,default=str)
    r.stop()
    print('DONE',out+'.json')
