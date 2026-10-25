"""The orbital drop (stage2.md 5.3) in the emulator with the flash monitor on every frame: a chapter after the first opens with the Arwing
docked at the station; launching and diving to the city ends the drop (EV_SPACE a==0, the drop flag off, pl_drop_end called); no frame of
the dock, the launch or the dive flashes. Planet drawing is not ours (the weak pl_* stubs), so the city is the world once the Arwing is down.

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/drop.py      (from stuntfox/)
"""
import h
from h import *

ck = Check()
fm_start('drop')
gstate(3)
fm_break()
run(40)
ck(mb(16, 0) == 1 and mb(24, 3) == 3 and mb(16, 3) == 1, 'campaign on in map 3, chapters up to 3 open')
was = (r16(0x02001d40), r8(0x02001d39))
ck(mb(19, 3) == 1, 'travel to chapter 3 is taken')
for _ in range(60):
    run(20, [])
    if r16(0x02001e08) == 0 and u32(0x02001e00) < 400 and r16(0x02001d40) == 4:
        break
run(30)
ck(mb(17, 1) == 3 and mb(17, 4) & 0x20 and s2f()['docked'] == 1, 'chapter 3 opens docked, the drop flag is on', 'state %x docked %s' % (mb(17, 4), s2f()['docked']))
e.frame.save(os.path.join(os.environ.get('OUT', '/tmp'), 'drop_0_dock.png'))
tap('UP', hold=6, after=20)                           # (the last row of the hangar menu is the launch)
tap('A', hold=6, after=60)
out = False
for _ in range(40):
    run(15)
    if s2f()['docked'] == 0:
        out = True
        break
ck(out, 'launched: no longer docked', 'docked %s' % s2f()['docked'])
e.frame.save(os.path.join(os.environ.get('OUT', '/tmp'), 'drop_1_out.png'))
ck(mb(17, 4) & 0x20, 'the drop is still on after launch')
ys, down = [], None
for n in range(900):                                  # (dive: Up is nose down, A is thrust)
    run(8, ['UP', 'A'] if n < 150 else ['UP'])
    f = s2f()
    ys.append(f['pos'][1])
    if n in (60, 200, 400):
        e.frame.save(os.path.join(os.environ.get('OUT', '/tmp'), 'drop_2_dive%d.png' % n))
    if not mb(17, 4) & 0x20:
        down = n
        break
ck(down is not None, 'the drop ends on the way down (flag off)', 'after %s steps, y %s -> %s, mode %s' % (down, ys[0] if ys else None, ys[-1] if ys else None, s2f()['mode']))
ck(len(ys) > 3 and ys[-1] != ys[0], 'the Arwing moved on the way', '%s %s' % (ys[0], ys[-1]))
e.frame.save(os.path.join(os.environ.get('OUT', '/tmp'), 'drop_3_down.png'))
worst, worst_red = fm_report()
ck(worst <= 3 and worst_red <= 3, 'flashcheck over the dock, launch and dive: most flashes in a second %d, red %d' % (worst, worst_red))
ck.done()
