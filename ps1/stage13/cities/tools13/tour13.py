#!/usr/bin/env python3
"""tour13.py: state-aware scripted test of the map follow + the L2/R2 switch in PCSXR (EMULATOR-ONLY, test tool).
Disc: a title-boot build with the city-K pad plan (TESTUNLOCK) and -DTG_LOADS=4 -DTG_TO=7.  Steps (each waits for the guest's log line):
 boot to level on map K (renderer starts on K) -> L2 (K-1, viewer override) -> R2 (back to K = the guest's own map) -> R2 (K+1) -> [test hook: guest grid id := 7, the renderer must follow (MAPFOLLOW to 7)] -> L2 (6) -> R2 (7).
usage: tour13.py disc.iso outprefix HOME_WITH_.pcsxr K [max_seconds]"""
import sys,os,subprocess,time,threading,re,random,signal
iso,out,home,K=sys.argv[1:5]; K=int(K); maxs=float(sys.argv[5]) if len(sys.argv)>5 else 1500
B=os.path.dirname(os.path.abspath(__file__))+'/../bin'
D=':%d'%random.randint(1000,4000); env=dict(os.environ,DISPLAY=D,HOME=home)
xs=subprocess.Popen([B+'/c13_xvfb',D,'-screen','0','800x600x24'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(1)
t0=time.time()
em=subprocess.Popen(['stdbuf','-o0',B+'/c13_pcsx','-nogui','-psxout','-cdfile',os.path.abspath(iso),'-runcd'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,cwd=os.path.dirname(os.path.abspath(iso)))
lines=[]; lk=threading.Lock(); logf=open(out+'.log','w')
def rd():
    for l in iter(em.stdout.readline,b''):
        s=l.decode('latin1')
        with lk: lines.append((time.time()-t0,s))
        logf.write('%7.2f %s'%(time.time()-t0,s)); logf.flush()
threading.Thread(target=rd,daemon=True).start()
pos=0
def wait(pat,to):
    global pos; end=time.time()+to; r=re.compile(pat)
    while time.time()<end and em.poll() is None:
        with lk: n=len(lines)
        while pos<n:
            t,s=lines[pos]; pos+=1
            if r.search(s): return s.strip()
        time.sleep(0.5)
    return None
def x(*a):
    w=subprocess.run(['xdotool','search','--onlyvisible','--name','PCSXR'],env=env,capture_output=True,text=True).stdout.split()
    if w: subprocess.run(['xdotool','windowfocus',w[0]],env=env); subprocess.run(['xdotool','mousemove','300','200'],env=env)
    subprocess.run(['xdotool']+list(a),env=env)
HOLD=50.0
def tap(k,hold=0.5): x('keydown',k); time.sleep(hold); x('keyup',k)
def shot(n): subprocess.run(['import','-window','root',out+'_'+n+'.png'],env=env)
res=[]
def step(name,pat,to,action=None):
    # the key is only seen at the guest's present (every 2-40 s wall in the emulator): press again (up to 4 times) until the log line shows
    r=None
    for tries in range(4 if action else 1):
        if action: action()
        r=wait(pat,to if not action else to/2)
        if r: break
    r=r; ok=r is not None; res.append((name,ok,round(time.time()-t0,1),r)); print('%-34s %s  t=%.0fs  %s'%(name,'OK  ' if ok else 'FAIL',time.time()-t0,(r or '')[:150]),flush=True); return ok
try:
    ok=step('boot to level, renderer on map %d'%K,r'SF3 frame 3 map %d gmap %d '%(K,K),maxs)
    if ok:
        time.sleep(8); shot('a_map%d'%K)
        p=(K+10)%11; n=(K+1)%11
        step('L2 -> map %d (override)'%p,r'MAPCHANGE to %d rc 0'%p,240,lambda:tap('e',HOLD)); time.sleep(12); shot('b_override%d'%p)
        step('R2 -> map %d (guest own map)'%K,r'MAPCHANGE to %d rc 0'%K,240,lambda:tap('t',HOLD)); time.sleep(12); shot('c_back%d'%K)
        step('R2 -> map %d (override)'%n,r'MAPCHANGE to %d rc 0'%n,240,lambda:tap('t',HOLD)); time.sleep(8)
        step('test hook: guest grid id -> 7',r'guest grid id set to 7',240)
        step('renderer follows to map 7',r'MAPFOLLOW to 7 rc 0',240); time.sleep(12); shot('d_follow7')
        step('L2 -> map 6 (override of 7)',r'MAPCHANGE to 6 rc 0',240,lambda:tap('e',HOLD)); time.sleep(10)
        step('R2 -> map 7 (guest own map)',r'MAPCHANGE to 7 rc 0',240,lambda:tap('t',HOLD)); time.sleep(10); shot('e_back7')
finally:
    time.sleep(2); shot('end'); em.kill(); time.sleep(1); xs.kill()
    print('RESULT',sum(1 for r in res if r[1]),'/',len(res),'steps ok; wall %.0fs'%(time.time()-t0))
