import sys,os,collections,time,pickle
sys.path.insert(0,'.')
from gbaenv import *
import prune,cg
SP='/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
rom=open(SP+'/roms/Payback (Europe) (En,Fr,De,Es,It).gba','rb').read()
PAD=eval(os.environ.get('PAD','[0x3ff]')); NS=int(sys.argv[1]); K=int(sys.argv[2]); USE=os.environ.get('STUBS','')
stubs={prune.STUBS[int(i)][0]:int(i) for i in USE.split(',') if i}
class SIo(Io):
    def __init__(s): super().__init__(); s.nd=0
    def read(s,off,size):
        if off in(0x130,0x131): s.keys=PAD[(s.nd//30)%len(PAD)]
        return super().read(off,size)
    def vblank(s): super().vblank(); s.nd+=1
    def write(s,off,size,val):
        super().write(off,size,val)
        if off==0 and size>=2: s.nd+=1
io=SIo(); A=ArmSide(rom,io,stubs=stubs)
def isret(v):
    return v>>24==8 and v&1 and ((v-5) in cg.P.ins and cg.P.ins[v-5].op=='bl' or (v-3) in cg.P.ins and cg.P.ins[v-3].op=='bl')
def isret_arm(v): return v>>24==3 and (v-4) in cg.P.ins and cg.P.ins[v-4].op=='bl'
incl=collections.Counter(); excl=collections.Counter(); tot=0
pc=0x08000000; t0=time.time(); stime=float(os.environ.get('TLIM','90'))
def fn(a): 
    a&=~1
    return cg.fo(a) if a in cg.P.ins else a
while tot<NS and time.time()-t0<stime:
    A.u.emu_start(pc,0,count=K)
    pc=A.u.reg_read(UC_ARM_REG_PC)|(1 if A.u.reg_read(UC_ARM_REG_CPSR)&0x20 else 0)
    tot+=1
    chain={fn(pc)}; excl[fn(pc)]+=1
    lr=A.u.reg_read(UC_ARM_REG_LR)
    if isret(lr): chain.add(fn(lr-1))
    sp=A.u.reg_read(UC_ARM_REG_SP)
    if 0x03000000<=sp<0x03008000:
        for k in range(min(120,(0x03008000-sp)//4)):
            v=int.from_bytes(A.u.mem_read(sp+4*k,4),'little')
            if isret(v): chain.add(fn(v-1))
    for f in chain: incl[f]+=1
print('samples',tot,'nd',io.nd,'swis',A.nswi,'instrs',tot*K)
print('func      incl%   excl%  callers')
for f,c in incl.most_common(45):
    print('%08x %6.1f %6.1f  %s'%(f,100*c/tot,100*excl[f]/tot,[hex(x) for x in sorted(cg.callers[f])][:5]))
pickle.dump((incl,excl,tot),open('out/samp.pkl','wb'))
