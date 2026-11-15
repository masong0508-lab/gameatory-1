#!/usr/bin/env python3
"""TEST-ONLY (emulator-only): scripted tour of a Payback PS1 disc in PCSXR with screenshots tagged by guest frame (gf), pad Down/Up at the title menu, level HUD, pause (Start).
usage: tour12.py disc.iso outprefix HOME [max_seconds]"""
import sys,os,subprocess,time,threading,re,random,signal
disc,out,home=sys.argv[1:4]; maxs=float(sys.argv[4]) if len(sys.argv)>4 else 1200
B=os.path.dirname(os.path.abspath(__file__))+'/../bin'
D=':%d'%random.randint(300,800); env=dict(os.environ,DISPLAY=D,HOME=home)
xs=subprocess.Popen([B+'/xs3',D,'-screen','0','800x600x24'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(1)
ff=subprocess.Popen(['ffmpeg','-loglevel','error','-y','-f','x11grab','-framerate','5','-video_size','800x600','-i',D,'-c:v','libx264','-preset','ultrafast','-crf','16',out+'_cap.mkv'],env=env)
t0=time.time()
em=subprocess.Popen(['stdbuf','-o0',B+'/sfemu3','-nogui','-psxout','-cdfile',os.path.abspath(disc),'-runcd'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,cwd=os.path.dirname(os.path.abspath(disc)))
t2=t3=0; st=dict(gf=0,lvl=False,sf3=0,raw=''); logf=open(out+'.log','w')
def rd():
    for l in iter(em.stdout.readline,b''):
        s=l.decode('latin1'); logf.write('%7.2f %s'%(time.time()-t0,s)); logf.flush()
        m=re.search(r' gf (\d+) ',s)
        if m: st['gf']=int(m.group(1))
        if 'deferred sf3_init' in s: st['lvl']=True
        if 'SF3 frame' in s: st['sf3']+=1
        if 'PADRAW' in s: st['raw']=s.strip()
threading.Thread(target=rd,daemon=True).start()
def x(*a):
    w=subprocess.run(['xdotool','search','--onlyvisible','--name','PCSXR'],env=env,capture_output=True,text=True).stdout.split()
    if w: subprocess.run(['xdotool','windowfocus',w[0]],env=env)
    subprocess.run(['xdotool']+list(a),env=env)
def tap_seen(k,code,tries=4):
    for _ in range(tries):
        st['raw']=''; x('keydown',k); t=time.time()
        while time.time()-t<12 and code not in st['raw']: time.sleep(0.2)
        seen=code in st['raw']; time.sleep(1.5); x('keyup',k)
        if seen: return True
        time.sleep(2)
    return False
def tap(k,hold=2.0): x('keydown',k); time.sleep(hold); x('keyup',k)
n=0
def shot(tag=''):
    global n; subprocess.run(['import','-window','root','%s_%03d_gf%04d%s.png'%(out,n,st['gf'],tag)],env=env); n+=1
def inwin(g): return any(a<=g<b for a,b in ((90,135),(350,450),(1090,1145)))
done=set(); last=0
try:
    while time.time()-t0<maxs and em.poll() is None:
        g=st['gf']; now=time.time()
        per=1.0 if inwin(g) else 5.0
        if now-last>=per: shot(); last=now
        if g>=660 and 'dn' not in done: done.add('dn'); shot('_pre_down'); r1=tap_seen('Down','00000040'); time.sleep(3); shot('_down'); g1=st['gf']; print('pad Down seen',r1,'gf',g1,flush=True)
        if 'dn' in done and 'up' not in done and st['gf']>=g1+12: done.add('up'); r2=tap_seen('Up','00000010'); time.sleep(3); shot('_up'); print('pad Up seen',r2,'gf',st['gf'],flush=True)
        if st['lvl'] and 'lvl' not in done:
            done.add('lvl'); t1=now
        if 'lvl' in done and 'p1' not in done and now-t1>40:
            done.add('p1'); shot('_lvl_pre_pause'); ok=tap_seen('Return','00000008',2); key='Return'
            if not ok: ok=tap_seen('v','00000008',2); key='v'
            print('Start (%s) seen by the guest:'%key,ok,'gf',st['gf'],flush=True); t2=time.time(); st['skey']=key
        if 'p1' in done and 'p2' not in done and time.time()-t2>25: done.add('p2'); shot('_pause'); time.sleep(12); shot('_pause2'); tap_seen(st['skey'],'00000008',2); t3=time.time(); print('Start again, gf',st['gf'],flush=True)
        if 'p2' in done and 'p3' not in done and time.time()-t3>25: done.add('p3'); shot('_resume')
        if 'p3' in done and time.time()-t3>150: shot('_resume_late'); break
        time.sleep(0.4)
finally:
    shot('_end'); em.kill(); ff.send_signal(signal.SIGINT); time.sleep(2); xs.kill()
    print('done wall %.0fs gf %d shots %d'%(time.time()-t0,st['gf'],n))
