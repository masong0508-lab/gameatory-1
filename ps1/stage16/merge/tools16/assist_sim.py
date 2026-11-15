"""mGBA model of the stage 16 assist (title gate): stock game + the blank plan, a stray Down at frame 661 (held 6 frames); --noshift = old behaviour.  Prints the guest level clock and name-screen state at the end."""
import sys,json
sys.path.insert(0,'w13'); from common import *
TAG=([a.split('=')[1] for a in sys.argv if a.startswith('--tag=')] or ['x'])[0]; SHIFT='--noshift' not in sys.argv; UPAT=int(([a.split('=')[1] for a in sys.argv if a.startswith('--up=')] or ['0'])[0]); PRE=int(([a.split('=')[1] for a in sys.argv if a.startswith('--pre=')] or ['661'])[0])
plan=json.load(open('out/pad_boot.json'))['plan']; KN=['A','B','SELECT','START','RIGHT','LEFT','UP','DOWN','R','L']
mk=lambda m:[KN[i] for i in range(10) if m>>i&1]
e=Emu(ROM); a0=0; shift=0; ups=0; c0=0; T=5; Ta=plan[T][0]
for f in range(2600):
    m=0
    if PRE<=f<PRE+6: m|=128
    if UPAT and UPAT<=f<UPAT+6: m|=64
    done=False
    if f>=Ta and (a0 or f<Ta+300):
        if a0: m|=1 if f<a0+6 else 0
        else:
            cur=e.r8(0x03007e68)
            if 0<cur<6 and f-Ta<300:
                ups+=((f-Ta)%12==0); m|=64 if (f-Ta)%12<6 else 0
            else:
                if ups and not c0: c0=f
                if ups and f<c0+36: pass
                else: a0=f; shift=f-Ta if SHIFT else 0; m|=1
    fe=f-shift
    for i,(a,b,mm) in enumerate(plan):
        if i!=T and a<=fe<b: m|=mm
    e.run(1,mk(m))
    if f in (790,860,930,1000,1060,1120): e.screenshot('/dev/shm/s15/as_%s_%d.png'%(TAG,f))
    if e.r32(0x02001e00)>0: print('level clock>0 at frame',f,'shift',shift,'a0',a0); break
else: print('NO LEVEL, clk',e.r32(0x02001e00),'a0',a0,'shift',shift)
e.screenshot('/dev/shm/s15/assist_sim_%s.png'%('shift' if SHIFT else 'noshift'))
