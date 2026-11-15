import sys,time; sys.path.insert(0,'t')
from sim4 import *
V=sys.argv[1]; N=int(sys.argv[2])
s=Sim('out/%s.exe'%V,'out/%s.iso'%V,'out/bld_%s/payback.elf'%V)
sym=s.sym; CY=sym['io_cyc']; SK=sym['sim_keys']; T=time.time()
def cb(s):
    s.u.mem_write(SK&0x1fffffff,struct.pack('<I',0x3ff)); return s.r32(CY)//280896>=N
s.cb=cb; s.run(count=40000000000)
print('sec %.0f'%(time.time()-T),'gba frames',s.r32(CY)//280896)
print(s.out.decode('latin1')[-1500:])
for n in ('ip_enters','ip_swis','ip_depth_max','cold_loads','cold_calls'):
    if n in sym: print(n,s.r32(sym[n]))
