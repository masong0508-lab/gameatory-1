#!/usr/bin/env python3
"""TEST-ONLY: run the full-cold sim build through the menus into the level (pad plan compiled into the guest runtime, KPLAN), capture the guest state at the
first h_vbl (SWI 5) call at/after a given frame after the level clock starts, write SNAPST.BIN for the PS1 disc, and record the executed guest functions.
usage: snapdump.py VARIANT(f2) SNAP_AFTER_LEVEL_FRAMES TOTAL_FRAMES OUT_SNAP OUT_TOUCHED"""
import sys,struct,pickle,bisect,time
sys.path.insert(0,'t')
from sim4 import *
from unicorn.mips_const import *
V=sys.argv[1]; AFTER=int(sys.argv[2]); TOTAL=int(sys.argv[3]); OUT=sys.argv[4]; OUTT=sys.argv[5]
s=Sim('out/%s.exe'%V,'out/%s.iso'%V,'out/bld_%s/payback.elf'%V)
sym=s.sym; CY=sym['io_cyc']
M=sorted((int(h,16),int(a,16)) for a,h in (l.split() for l in open('out/pr_%s/payback_P.map'%V)))
HS=[x for x,_ in M]
state=dict(armed=False,snap=None,lvl=None,touched=set(),touch_on=False)
ST=['io_vc','io_nread','io_nd','io_cyc','io_acc','g_gframes','g_nvbl']
def collect(uc):
    regs=[uc.reg_read(UC_MIPS_REG_0+i) for i in range(32)]
    g=lambda n,k=1:[s.r32(sym[n]+4*i) for i in range(k)]
    st=[]
    for n in ST: st+=g(n)
    for n in ('tm_t0','tm_rl','tm_ovb','tm_en' if 'tm_en' in sym else 'tm_en.0'): st+=g(n,4)    # the linker may name the split array tm_en.0 (4 consecutive words)
    st+=g('ee_init'); st+=g('lvl_f0')
    return regs,st,s.rd(0x801fff00,256)
def snap(uc,rec,target):
    regs,st,stack=rec
    hdr=bytearray(2048); struct.pack_into('<I',hdr,0,0x534e4150)
    for i,v in enumerate(regs): struct.pack_into('<I',hdr,4+4*i,v)
    struct.pack_into('<I',hdr,0x88,target)       # resume target: 0 = present(), 1 = h_memrd() (the level polls VCOUNT; the snapshot is taken at the h_memrd entry of the poll that leads to present())
    for i,v in enumerate(st): struct.pack_into('<I',hdr,0xa0+4*i,v)
    hdr[0x200:0x300]=stack
    out=bytes(hdr)+s.rd(EW,0x40000)+s.rd(IW,0x8000)+s.rd(VRAM,0x18000)+s.rd(PAL,0x400)+s.rd(PAL+0x400,0x400)+s.rd(sym['io'],0x400)+b'\0'*1024+s.rd(sym['ee'],8192)
    assert len(out)==2048*(1+128+16+48+1+1+4),len(out)
    # sectors: 0 hdr,1..128 EW,129..144 IW,145..192 VRAM,193 PAL+OAM,194 io,195..198 ee
    return out,regs,st
IOR=(sym['io_read'],sym['io_read']+0x900)
def hm(uc,a,sz,ud):
    if state['armed'] and state['snap'] is None: state['rec']=collect(uc)
s.u.hook_add(UC_HOOK_CODE,hm,None,sym['h_memrd'],sym['h_memrd'])
def hv(uc,a,sz,ud):
    if state['armed'] and state['snap'] is None and state.get('rec') and IOR[0]<=uc.reg_read(UC_MIPS_REG_31)<IOR[1]:
      try:
        out,regs,st=snap(uc,state['rec'],1); state['snap']=(out,regs,st); state['touch_on']=True
        state['f']=s.r32(CY)/280896; print('SNAPSHOT at gba frame %.1f'%state['f'],'regs sp',hex(regs[29]),'ra',hex(regs[31]),'a0',hex(regs[4]),flush=True)
      except Exception as e:
        import traceback; traceback.print_exc(); state['armed']=False; state['snap']=0
s.u.hook_add(UC_HOOK_CODE,hv,None,sym['present'],sym['present'])      # present() is entered from h_vbl (SWI 5 waits) and from io_read (VCOUNT polling, the level's frame loop); both resume the same way
rompg={}
def hrm(uc,a,sz,ud):
    if state['touch_on']:
        ea=uc.reg_read(UC_MIPS_REG_4)
        if (ea>>24) in (8,10,12): p=(ea&0x1ffffff)>>12; rompg[p]=rompg.get(p,0)+1
s.u.hook_add(UC_HOOK_CODE,hrm,None,sym['h_memrd'],sym['h_memrd'])      # ROM pages read at run time after the snapshot point (resident set for the disc)
def blk(uc,a,sz,ud):
    if state['touch_on']: state['touched'].add(a|0x80000000)
s.u.hook_add(UC_HOOK_BLOCK,blk)
T0=time.time()
def cb(s):
    f=s.r32(CY)//280896
    if s.r32(EW+0x1e00) and state['lvl'] is None: state['lvl']=f; print('LEVEL clock runs at gba frame',f,'map',s.r16(EW+0x1d40),flush=True)
    if state['lvl'] is not None and f>=state['lvl']+AFTER: state['armed']=True
    if f%250==0 and state.get('pf')!=f: state['pf']=f; print('frame',f,'t %.0f'%(time.time()-T0),'clk',s.r32(EW+0x1e00),'nent',s.r16(IW+0xc),flush=True)
    return f>=TOTAL
s.cb=cb; s.run(count=30000000000)
pickle.dump(rompg,open(OUTT+'.rompages','wb'))
open(OUT+'.psxout','wb').write(bytes(s.out))
print('done frame',s.r32(CY)/280896,'out tail:',s.out.decode('latin1')[-300:])
if state['snap']:
    open(OUT,'wb').write(state['snap'][0])
    # touched host blocks -> guest functions
    res,funcs=pickle.load(open('out/s2/resident.pkl','rb'))
    fo=lambda a: funcs[bisect.bisect_right(funcs,a)-1]
    gs=set()
    for h in state['touched']:
        j=bisect.bisect_right(HS,h)-1
        if j>=0 and M[j][1]: gs.add(M[j][1])
    pickle.dump(gs,open(OUTT,'wb')); print('touched guest instr-labels',len(gs))
