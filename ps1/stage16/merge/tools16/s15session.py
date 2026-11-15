#!/usr/bin/env python3
"""s15session.py: stage 16 merged-disc verification in PCSXR (EMULATOR-ONLY, HLE BIOS), one emulator, real xdotool keys (DFInput default map).
Phases (state from the runtime's log lines, never fixed sleeps for game state):
  boot   : optional pad Down at the title before the timed A (--predown: state-aware assist check), wait for the level clock (GS lines)
  keys   : idle, Cross, Left/Right, Up, Down, R1, L1 (guest key word echo from GS lines)
  weapon : Up (weapon switch) then the 3D view must come back (SF3 frame count rises); shots
  pause  : Start, screenshot while paused (3D view held?), clock frozen, Start/Cross resume, 3D back
  radio  : Select+R1, Select+Triangle
  maps   : R2 x N (city start poses, shot after each MAPCHANGE + 2 renders), L2 back
usage: s15session.py disc.cue home out_prefix [--predown] [--nomaps] [--maxs N] [--video]"""
import sys,os,time,re,json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))+'/../tools13')
import pcx
A=[a for a in sys.argv[1:] if not a.startswith('--')]; F=[a for a in sys.argv[1:] if a.startswith('--')]
cue,home,out=A[:3]; MAXS=int(A[3]) if len(A)>3 else 5400
PREDOWN='--predown' in F; NOMAPS='--nomaps' in F; VIDEO='--video' in F; NMAP=int(([f.split('=')[1] for f in F if f.startswith('--nmap=')] or ['10'])[0])
GS=re.compile(r'GS gf (\d+)\s*clk (\d+)\s*ci (\d+)\s*nl (\d+)\s*x (-?\d+)\s*z (-?\d+)\s*hd (\d+)\s*hp (-?\d+)\s*sc (-?\d+)\s*def (-?\d+)\s*cls (\d+)\s*pad ([0-9a-fA-Fx]+)\s*key ([0-9a-fA-Fx]+)')
r=pcx.Run(cue,home,out,video=VIDEO)
res={'flags':F}; ev=[]; S=dict(gs=None,pos=0,sf3=0,hist=[]); shots=[]
def pump():
    with r.lk: L=r.lines[S['pos']:]; S['pos']+=len(L)
    for t,l in L:
        m=GS.search(l)
        if m:
            g=m.groups(); S['gs']=dict(gf=int(g[0]),clk=int(g[1]),x=int(g[4]),z=int(g[5]),hd=int(g[6]),pad=int(g[11].replace('0x',''),16),key=int(g[12].replace('0x',''),16),t=t); S['hist'].append(S['gs']); continue
        if 'SF3 frame' in l: S['sf3']+=1
        if re.search(r'DOLL|MAPCHANGE|MAPFOLLOW|TEST-ONLY|sf3_ok|PANIC|FAULT|RT_MISS|ASSIST|MC |SF3|RADIO|VENEER|interp|PADRAW|deferred|guest map|IMG gf',l):
            if 'IMG gf' in l and len(ev)>400: continue
            ev.append((round(t),l.strip())); print('EV %6.0f %s'%(t,l.strip()[:200]),flush=True)
def gs(): pump(); return S['gs']
def wait_frames(n,to=1800):
    g0=gs(); t0=time.time()
    while time.time()-t0<to and r.alive():
        g=gs()
        if g and g0 and g['gf']>=g0['gf']+n: return g
        time.sleep(0.25)
    return gs()
def shot(name):
    p='%s_%s.png'%(out,name); r.shot(p); shots.append(p); return p
def hold(name,keys,n):
    a=gs(); S['hist']=[]
    for k in keys: r.down(k)
    b=wait_frames(n)
    for k in keys: r.up(k)
    c=wait_frames(2); kw=sorted(set('%03x'%(h['key']&0x3ff) for h in S['hist'])); pw=sorted(set('%04x'%h['pad'] for h in S['hist']))
    d=dict(gf=a and a['gf'],frames=(b['gf']-a['gf']) if a and b else None,guest_key_words=kw,pad_words=pw,clk=(a['clk'],c['clk']) if a and c else None,pos=(a and (a['x'],a['z']),c and (c['x'],c['z'])),hd=(a and a['hd'],c and c['hd']))
    res[name]=d; print('RESULT',name,json.dumps(d),flush=True); return d
def wait_sf3(n,to):
    """wait for n more SF3 render log lines (the log prints every PRINT_EVERY_SF3-th render and the first 3)"""
    s0=S['sf3']; t0=time.time()
    while time.time()-t0<to and r.alive():
        pump()
        if S['sf3']>=s0+n: return True
        time.sleep(1)
    return False
def luma(p):
    from PIL import Image,ImageStat
    return ImageStat.Stat(Image.open(p).convert('L').crop((160,120,640,480))).mean[0]
t0=time.time()
try:
    if PREDOWN:
        # state-aware assist check: a real Down at the title (guest gf >= 660, before the timed A at gf 750) moves the cursor to Delete game; the assist must put it back
        t1=time.time()
        while time.time()-t1<MAXS and r.alive():
            pump()
            if any(re.search(r' gf (\d+) ',l) for _,l in r.lines[-3:]) : break
            time.sleep(1)
        while time.time()-t0<MAXS and r.alive():
            m=r.last(r' gf (\d+) ')
            g=int(re.search(r' gf (\d+) ',m).group(1)) if m else 0
            if g>=655: break
            time.sleep(1)
        r.mark(); r.down('DOWN')
        ok=r.wait(r'PADRAW|pad',1)   # best effort
        time.sleep(3.5); r.up('DOWN'); shot('predown_title'); print('real Down pressed at gf',g,flush=True); res['predown_gf']=g
    print('waiting for the level ...',flush=True)
    while time.time()-t0<MAXS and r.alive():
        if gs(): break
        time.sleep(2)
    if not S['gs']: print('NO LEVEL'); raise SystemExit(1)
    res['level_up_s']=round(time.time()-t0); print('LEVEL up after %d s gf %d'%(res['level_up_s'],S['gs']['gf']),flush=True)
    for l in list(ev):
        if 'ASSIST title cursor' in l[1]: res.setdefault('assist_title_corrections',[]).append(l[1])
    wait_sf3(2,300); wait_frames(6); shot('level_start')
    hold('idle',[],4)
    hold('walk Cross',['CROSS'],10)
    hold('turn Left',['LEFT'],6); hold('turn Right',['RIGHT'],6)
    hold('Square(B)',['SQUARE'],4)
    hold('Up (next weapon)',['UP'],3)
    # weapon switch: runs overlay code (SF3 cold group over renderer data -> interpreted now); the 3D view must keep/return
    pump(); n0=S['sf3']; wait_sf3(3,400); res['weapon_up_renders_after']=S['sf3']-n0; shot('after_weapon_up'); res['luma_after_weapon_up']=luma(shots[-1])
    hold('Down (prev weapon)',['DOWN'],3)
    wait_sf3(3,400); shot('after_weapon_down'); res['luma_after_weapon_down']=luma(shots[-1])
    hold('R1 (shoot)',['R1'],5); hold('L1 (enter/exit)',['L1'],3)
    wait_sf3(2,300)
    # pause
    c_before=gs()['clk']
    hold('Start (pause)',['START'],3)
    g=wait_frames(30); res['pause_clk1']=g['clk']; time.sleep(5); shot('paused_a'); g2=wait_frames(30); res['pause_clk2']=g2['clk']
    wait_sf3(2,200); time.sleep(3); shot('paused_b'); res['luma_paused']=luma(shots[-1]); res['luma_paused_a']=luma(shots[-2])
    res['pause_clock_frozen']=(res['pause_clk2']-res['pause_clk1'])<=1
    hold('resume (Cross)',['CROSS'],3)
    g=wait_frames(30); res['clk_after_resume']=g['clk']; res['pause_resumes']=g['clk']>res['pause_clk2']
    n0=S['sf3']; res['3d_back_after_pause']=wait_sf3(3,600); res['renders_after_pause']=S['sf3']-n0; shot('after_pause'); res['luma_after_pause']=luma(shots[-1])
    # radio
    r.mark()
    for k in ('SELECT','R1'): r.down(k)
    time.sleep(2.5)
    for k in ('SELECT','R1'): r.up(k)
    time.sleep(6); pump(); res['radio_select_r1']=[e[1] for e in ev if 'RADIO' in e[1]][-3:]
    for k in ('SELECT','TRIANGLE'): r.down(k)
    time.sleep(2.5)
    for k in ('SELECT','TRIANGLE'): r.up(k)
    time.sleep(6); pump(); res['radio_select_triangle']=[e[1] for e in ev if 'RADIO' in e[1]][-3:]
    # maps
    if not NOMAPS:
        res['maps']={}
        for i in range(NMAP):
            n0=len(ev); r.mark(); r.down('R2'); time.sleep(3.0); r.up('R2')
            line=r.wait(r'MAPCHANGE to \d+ rc',240)
            if not line: res['maps']['R2 #%d'%i]='no MAPCHANGE'; print('no MAPCHANGE'); break
            wait_sf3(3,300); time.sleep(2); p=shot('map_r2_%d'%i); res['maps']['R2 #%d'%i]=dict(line=line,shot=os.path.basename(p))
            print('MAP',i,line,flush=True)
        r.mark(); r.down('L2'); time.sleep(3.0); r.up('L2'); l2=r.wait(r'MAPCHANGE to \d+ rc',240); wait_sf3(3,300); shot('map_l2_back'); res['maps']['L2 back']=l2
finally:
    pump(); res['shots']=shots; res['events_tail']=ev[-60:]; res['wall_s']=round(time.time()-t0)
    with r.lk: L=[l for _,l in r.lines]
    res['count_RT_MISS']=sum('RT_MISS' in l and 'panic' in l.lower() for l in L); res['count_PANIC']=sum('PANIC' in l for l in L); res['count_FAULT']=sum('FAULT' in l for l in L)
    json.dump(res,open(out+'.json','w'),indent=1,default=str)
    r.stop(); print('DONE',out+'.json')
