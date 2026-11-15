"""mGBA: replay each city plan, read the guest player's position at the level start (+N frames) and compare to the SF3M start point"""
import sys,json,struct
sys.path.insert(0,'mgba'); sys.dont_write_bytecode=True
from emu import Emu
ROM=sys.argv[1]
d=open('out/SF3M.BIN','rb').read(2048)
for K in range(11):
    pl=json.load(open('w/pl/city%d.json'%K)); plan=pl['plan']; poke0=pl['poke0']
    e=Emu(ROM); f=0; end=pl['frames']
    out=[]
    while f<end+130:
        m=0
        for a,b,mk in plan:
            if a<=f<b: m|=mk
        e.set_keys(m)
        if poke0 and f>=poke0 and e.r32(0x02001e00)==0:
            for i in range(16): e.w16(0x020026d0+2*i,5)
        e.run(1); f+=1
        if f in (end,end+30,end+120):
            ci=struct.unpack('<h',e.read(0x02001db8,2))[0]; nl=struct.unpack('<h',e.read(0x0300000c,2))[0]
            tab=e.r32(0x03000c60+4*ci)
            x=e.s32(tab+4); z=e.s32(tab+8); h=e.r16(tab+0xc)
            out.append((f,'map',e.r16(0x02001d40),'clk',e.r32(0x02001e00),'ci',ci,'nl',nl,'pos',x>>1,z>>1,'y',(19904-h)>>1))
    sx=struct.unpack_from('<8i',d,8+32*K)
    print(K,'start(SF3M)',sx[4],sx[5],sx[6],'|',out[-1],flush=True)
