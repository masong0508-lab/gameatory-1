"""EV_KILL from a natural kill: the Arwing shoots a parked car until it burns; the event carries the car's Payback tag (+0x14c,
read before the kill: Payback sets -1 after it) and its descriptor number. Needs the override build (the dummy cp_ev keeps the
last arguments):

    S2_EXTRA_SRC=tests/s2/override/s2dummy.c python3 build.py "$PAYBACK_ROM" --merge -o override.gba
    SP=.. ROM=override.gba ELF=build/merge/stuntfox-merge.elf python3 tests/s2/kill.py      (from stuntfox/)

A crate opened by a bolt (props.c, sf_crate_fx) has no such test: Payback puts crates down only in missions.
"""
import h
from h import *

ck = Check()
merged_state(e)
run(200)
ck(board_now() == 'FLY', 'in the Arwing')
KILL = EV.index('KILL')


def dv(name, i=0):
    return u32(S[name] + 4 * i)


cars = [x for x in ents() if x[3] in (3, 4) and x[2] >= 5 and x[5] > 0]
ck(len(cars) >= 1, 'a car to shoot', '%d cars' % len(cars))
done = None
for c in cars[:6]:
    tag = r32(c[1] + 0x14c)
    k0 = dv('dummy_cp_ev', KILL)
    x, y = c[4][0], c[4][1]
    tele_ship([int(x * 1024), 900, int((y - 2.5) * 1024)], f=(0, -5000, 15600))
    for _ in range(30):
        run(10, ['R'])
        if dv('dummy_cp_ev', KILL) != k0:
            break
    if dv('dummy_cp_ev', KILL) != k0:
        done = (c, tag, dv('dummy_cp_ev', KILL) - k0)
        break
ck(done is not None, 'EV_KILL: a car shot to pieces raises it')
if done:
    c, tag, n = done
    a, b = r32(S['dummy_ev_a'] + 4 * KILL), r32(S['dummy_ev_b'] + 4 * KILL)
    ck(n == 1, 'once only', 'EV_KILL x%d' % n)
    ck(a == tag, 'a is the car\'s Payback tag, as it was before the kill', 'event %d, tag %d' % (a, tag))
    ck(b == c[2], 'b is the car\'s descriptor number', 'event %d, car %d' % (b, c[2]))
    ck(r32(c[1] + 0x14c) == -1 or tag != -1, 'Payback untags it after (the event has the tag it had)', 'now %d' % r32(c[1] + 0x14c))
ck.done()
