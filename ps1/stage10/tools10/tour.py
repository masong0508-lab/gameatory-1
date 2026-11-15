#!/usr/bin/env python3
"""tour.py: state-aware scripted tour of a Payback PS1 disc in PCSXR (EMULATOR-ONLY, test tool).  The driver reads the emulator's log and presses pad keys (xdotool, DFInput default map)
only when the guest has reached the state the next step needs: title -> menus -> level -> L2 (map change) -> L2 -> R2 -> R2 -> radio (Select+R1, Select+Triangle) -> walk.
usage: tour.py disc.cue outprefix HOME_WITH_.pcsxr [max_seconds]"""
import sys,os,subprocess,time,threading,re,random,signal
cue,out,home=sys.argv[1:4]; maxs=float(sys.argv[4]) if len(sys.argv)>4 else 1500
B=os.path.dirname(os.path.abspath(__file__))+'/../bin'
D=':%d'%random.randint(300,800); env=dict(os.environ,DISPLAY=D,HOME=home)
xs=subprocess.Popen([B+'/xs3',D,'-screen','0','800x600x24'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(1)
ff=subprocess.Popen(['ffmpeg','-loglevel','error','-y','-f','x11grab','-framerate','5','-video_size','800x600','-i',D,'-c:v','libx264','-preset','ultrafast','-crf','20',out+'_cap.mp4'],env=env)
t0=time.time()
em=subprocess.Popen(['stdbuf','-o0',B+'/sfemu3','-nogui','-psxout','-cdfile',os.path.abspath(cue),'-runcd'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,cwd=os.path.dirname(os.path.abspath(cue)))
lines=[]; lk=threading.Lock(); logf=open(out+'.log','w')
def rd():
    for l in iter(em.stdout.readline,b''):
        s=l.decode('latin1'); 
        with lk: lines.append((time.time()-t0,s))
        logf.write('%7.2f %s'%(time.time()-t0,s)); logf.flush()
threading.Thread(target=rd,daemon=True).start()
pos=0
def wait(pat,to):
    """wait for a log line matching pat (searching new lines only); returns the line or None"""
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
HOLD=14.0   # the guest presents once per 16 GBA frames (2-8 s wall in the level): a key must be held across at least two presents
def tap(k,hold=0.5): x('keydown',k); time.sleep(hold); x('keyup',k)
res=[]
def step(name,pat,to,action=None):
    t=time.time()-t0
    if action: action()
    r=wait(pat,to) if pat else 'n/a'
    ok=r is not None; res.append((name,ok,round(time.time()-t0,1),r)); print('%-28s %s  t=%.0fs  %s'%(name,'OK  ' if ok else 'FAIL',time.time()-t0,(r or '')[:110]),flush=True)
    return ok
try:
    ok=step('boot to level (title->menus->level)',r'deferred sf3_init',maxs)
    if ok:
        step('first renders',r'SF3 frame 3 ',300); time.sleep(10)
        step('L2 -> map 10',r'MAPCHANGE to 10 rc 0',200,lambda:tap('e',HOLD)); time.sleep(10)
        step('L2 -> map 9',r'MAPCHANGE to 9 rc 0',200,lambda:tap('e',HOLD)); time.sleep(10)
        step('R2 -> map 10',r'MAPCHANGE to 10 rc 0',200,lambda:tap('t',HOLD)); time.sleep(10)
        step('R2 -> map 0',r'MAPCHANGE to 0 rc 0',200,lambda:tap('t',HOLD)); time.sleep(10)
        def radio(): x('keydown','c'); time.sleep(1.2); tap('r',HOLD); x('keyup','c')
        step('radio Select+R1 play',r'CDDA play cmd 0x03',120,radio); time.sleep(4)
        def stop(): x('keydown','c'); time.sleep(1.2); tap('d',HOLD); x('keyup','c')
        step('radio Select+Triangle',r'RADIO stop|RADIO .*stop|CDDA stop|CDDA pause',120,stop); time.sleep(4)
        step('pad Up held (walk)',r'PADRAW 0000[0-9a-f]*[1-9a-f]',60,lambda:tap('Up',20.0)); time.sleep(3)
        step('pad Cross (A)',r'PADRAW',60,lambda:tap('x',HOLD)); time.sleep(10)
finally:
    time.sleep(2); subprocess.run(['import','-window','root',out+'_end.png'],env=env)
    em.kill(); ff.send_signal(signal.SIGINT); time.sleep(2); xs.kill()
    print('RESULT',sum(1 for r in res if r[1]),'/',len(res),'steps ok; wall %.0fs'%(time.time()-t0))
