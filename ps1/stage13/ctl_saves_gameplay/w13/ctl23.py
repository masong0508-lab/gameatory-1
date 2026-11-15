from common import *
e=Emu(ROM); scenes.boot_to_level(e)
e.run(60,[])
e.tap('START',hold=6,after=40); e.tap('DOWN',hold=6,after=30); e.tap('A',hold=6,after=40)
e.tap('LEFT',hold=6,after=30)
e.tap('A',hold=6,after=60)
print(state(e)); e.screenshot('w13/quit0.png',2)
for i in range(4):
    e.run(150,[]); print(i,state(e)['clk'],state(e)['map'],e.frames)
e.screenshot('w13/quit1.png',2)
