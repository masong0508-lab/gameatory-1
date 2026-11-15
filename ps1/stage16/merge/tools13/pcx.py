#!/usr/bin/env python3
"""pcx.py: PCSXR driver for the Payback PS1 tests (EMULATOR-ONLY, HLE BIOS).  Own X server + emulator binary (bin/xs3, bin/sfemu3).
Run(cue, home, out): start; wait(pat,to) on the emulator log; key/hold with xdotool (DFInput default map); shot(); stop().
DFInput default keyboard map: Up/Down/Left/Right arrows, z Cross, x Circle, s Square, d Triangle, w L1, r R1, e L2, t R2, c Select, v Start."""
import os,subprocess,time,threading,re,random,signal
HERE=os.path.dirname(os.path.abspath(__file__)); B=HERE+'/../bin'
KEYS=dict(UP='Up',DOWN='Down',LEFT='Left',RIGHT='Right',CROSS='z',CIRCLE='x',SQUARE='s',TRIANGLE='d',L1='w',R1='r',L2='e',R2='t',SELECT='c',START='v')
def mkhome(path,card_src,card2_src=None):
    """HOME with .pcsxr (config copied from the stage-10 home, paths rewritten) and the given memory card image"""
    import shutil
    P=path+'/.pcsxr'; os.makedirs(P+'/memcards',exist_ok=True)
    for d in ('bios','cheats','patches','sstates'): os.makedirs(P+'/'+d,exist_ok=True)
    if not os.path.exists(P+'/plugins'): shutil.copytree(HERE+'/../../s10_boot/home1/.pcsxr/plugins',P+'/plugins')
    cfg=open(HERE+'/../../s10_boot/home1/.pcsxr/pcsxr.cfg').read().replace(HERE+'/../../s10_boot/home1',path)
    cfg=re.sub(r'/tmp/claude-0/[^\n]*?/s10_boot/home1',path,cfg)
    open(P+'/pcsxr.cfg','w').write(cfg)
    shutil.copy(card_src,P+'/memcards/card1.mcd')
    shutil.copy(card2_src or card_src,P+'/memcards/card2.mcd') if False else None
    if not os.path.exists(P+'/memcards/card2.mcd'): shutil.copy(HERE+'/../../s10_boot/home1/.pcsxr/memcards/card2.mcd',P+'/memcards/card2.mcd')
    return path
class Run:
    def __init__(s,cue,home,out,video=False,size='800x600'):
        s.out=out; s.home=home; s.cue=os.path.abspath(cue)
        s.D=':%d'%random.randint(300,900); s.env=dict(os.environ,DISPLAY=s.D,HOME=home)
        s.xs=subprocess.Popen([B+'/s15_xvfb',s.D,'-screen','0',size+'x24'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(1)
        s.ff=None
        if video: s.ff=subprocess.Popen(['ffmpeg','-loglevel','error','-y','-f','x11grab','-framerate','5','-video_size',size,'-i',s.D,'-c:v','libx264','-preset','ultrafast','-crf','22',out+'_cap.mp4'],env=s.env)
        s.t0=time.time()
        s.em=subprocess.Popen(['stdbuf','-o0',B+'/s15_pcsx','-nogui','-psxout','-cdfile',s.cue,'-runcd'],env=s.env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,cwd=os.path.dirname(s.cue))
        s.lines=[]; s.lk=threading.Lock(); s.logf=open(out+'.log','w'); s.pos=0
        threading.Thread(target=s._rd,daemon=True).start()
    def _rd(s):
        for l in iter(s.em.stdout.readline,b''):
            t=l.decode('latin1')
            with s.lk: s.lines.append((time.time()-s.t0,t))
            s.logf.write('%7.2f %s'%(time.time()-s.t0,t)); s.logf.flush()
    def now(s): return time.time()-s.t0
    def alive(s): return s.em.poll() is None
    def wait(s,pat,to,from_start=False):
        """wait for a log line matching pat among lines not yet consumed; returns the line (stripped) or None"""
        if from_start: s.pos=0
        end=time.time()+to; r=re.compile(pat)
        while time.time()<end and s.alive():
            with s.lk: n=len(s.lines)
            while s.pos<n:
                t,l=s.lines[s.pos]; s.pos+=1
                if r.search(l): return l.strip()
            time.sleep(0.3)
        return None
    def mark(s):
        with s.lk: s.pos=len(s.lines)
    def last(s,pat):
        r=re.compile(pat)
        with s.lk: L=list(s.lines)
        for t,l in reversed(L):
            if r.search(l): return l.strip()
    def x(s,*a):
        w=subprocess.run(['xdotool','search','--onlyvisible','--name','PCSXR'],env=s.env,capture_output=True,text=True).stdout.split()
        if w: subprocess.run(['xdotool','windowfocus',w[0]],env=s.env); subprocess.run(['xdotool','mousemove','300','200'],env=s.env)
        subprocess.run(['xdotool']+list(a),env=s.env)
    def down(s,k): s.x('keydown',KEYS.get(k,k))
    def up(s,k): s.x('keyup',KEYS.get(k,k))
    def tap(s,k,hold=1.0): s.down(k); time.sleep(hold); s.up(k)
    def shot(s,path):
        subprocess.run(['import','-window','root',path],env=s.env)
    def stop(s):
        try: s.shot(s.out+'_end.png')
        except Exception: pass
        s.em.kill()
        if s.ff: s.ff.send_signal(signal.SIGINT); time.sleep(2)
        s.xs.kill()
