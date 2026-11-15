import sys,os,pickle,time
sys.path.insert(0,'tools12'); sys.path.insert(0,'t')
from gsim import *
exe,iso,elf,out=sys.argv[1:5]; TOTAL=int(sys.argv[5]); FR=sorted(int(x) for x in sys.argv[6].split(',')) if len(sys.argv)>6 else []
s=GSim(exe,iso,elf); sym=s.sym; CY=sym['io_cyc']; EW=0x801b0000; nx=[0]; T0=time.time(); saved={}; st={}
def cb(s):
    f=s.r32(CY)//280896; s.np=getattr(s,'np',0)+1
    if s.np%20==0: print('present',s.np,'gf',f,'t %.0f'%(time.time()-T0),'quads',s.gpu.nq,flush=True)
    while nx[0]<len(FR) and f>=FR[nx[0]]:
        # the frame most recently displayed by the GPU model
        if s.gpu.frames:
            im=to_rgb(s.gpu.frames[-1]); Image.fromarray(im).save('%s_f%04d.png'%(out,FR[nx[0]])); saved[FR[nx[0]]]=s.gpu.frames[-1].copy(); st[FR[nx[0]]]=dict(vr=s.rd(VRAM,0x18000),pal=s.rd(PAL,0x400),oam=s.rd(PAL+0x400,0x400),io=s.rd(sym['io'],0x400),nobj=s.r32(sym['pp_nobj']),bright=s.r32(sym['pp_bright']))
        print('cmds last frames',[{hex(k):v for k,v in d.items()} for d in s.gpu.fc[-3:]])
        print('shot',FR[nx[0]],'at',f,'t %.0f'%(time.time()-T0),'frames',len(s.gpu.frames),'quads',s.gpu.nq,flush=True); nx[0]+=1
    if f>=470 and f<472: s.gpu.dump=1
    elif f>=472: s.gpu.dump=0
    if len(s.gpu.frames)>3: del s.gpu.frames[:-2]
    return f>=TOTAL
s.cb=cb; s.run(count=30000000000)
pickle.dump(saved,open(out+'_frames.pkl','wb')); pickle.dump(st,open(out+'_state.pkl','wb')); print('done unknown cmds',s.gpu.unk, getattr(s.gpu,'unkh',[])[:6])
