#!/usr/bin/env python3
"""TEST-ONLY: boot a disc in PCSXR (HLE BIOS, headless Xvfb), screenshot at given times. usage: shots.py disc.(iso|cue) HOME outprefix t1,t2,... [fresh_card=1]"""
import sys,os,subprocess,time,random,signal,threading,shutil
disc,home,out=sys.argv[1:4]; ts=[float(x) for x in sys.argv[4].split(',')]
B=os.path.dirname(os.path.abspath(__file__))+'/../bin'
if len(sys.argv)<6 or sys.argv[5]=='1':
    for c in ('card1.mcd','card2.mcd'):
        open(home+'/.pcsxr/memcards/'+c,'wb').write(b'MC'+b'\0'*126+b'\0'*(131072-128)) if False else None
D=':%d'%random.randint(300,800); env=dict(os.environ,DISPLAY=D,HOME=home)
xs=subprocess.Popen([B+'/xs3',D,'-screen','0','800x600x24'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(1)
t0=time.time()
em=subprocess.Popen(['stdbuf','-o0',B+'/sfemu3','-nogui','-psxout','-cdfile',os.path.abspath(disc),'-runcd'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,cwd=os.path.dirname(os.path.abspath(disc)))
logf=open(out+'.log','w')
def rd():
    for l in iter(em.stdout.readline,b''): logf.write('%7.2f %s'%(time.time()-t0,l.decode('latin1'))); logf.flush()
threading.Thread(target=rd,daemon=True).start()
try:
    for i,t in enumerate(ts):
        while time.time()-t0<t: time.sleep(0.5)
        subprocess.run(['import','-window','root','%s_%02d_%04d.png'%(out,i,int(t))],env=env)
finally:
    em.kill(); xs.kill()
