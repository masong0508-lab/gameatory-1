"""Combat's events with their arguments (package K), on the override build (the dummy entry points keep the last arguments of
each event): EV_FOE_DOWN has the foe's tag and kind (a plain pirate, a boss's body), EV_PICKUP the pod's tag, and EV_DOCK,
EV_LAUNCH and EV_ARWING_DOWN come once each.

    S2_EXTRA_SRC=tests/s2/override/s2dummy.c python3 build.py "$PAYBACK_ROM" --merge -o override.gba
    SP=.. ROM=override.gba ELF=build/merge/stuntfox-merge.elf python3 tests/s2/combat_ev.py      (from stuntfox/)
"""
import h
from h import *

ck = Check()
merged_state(e)
run(30)
ck(board_now() == 'FLY', 'in the Arwing')
e.write8(S['sg_shield_k'], 255)
me = epos(PL)
X, Z = int(me[0] * 1024), int(me[1] * 1024)
FOE_DOWN, PICKUP = 9, 11
F_RAIDER, F_ACE, F_HULL = 1, 4, 6


def ev(i):
    return r32(S['dummy_cp_ev'] + 4 * i), r32(S['dummy_ev_a'] + 4 * i), r32(S['dummy_ev_b'] + 4 * i)


tele_ship([X, 2400, Z - 2000], f=(0, -3000, 15900))
run(2)
mb(58, 0)
n0 = ev(FOE_DOWN)[0]
mb(51, F_RAIDER)
mb(49)
run(3)
n, a, b = ev(FOE_DOWN)
ck(n - n0 == 1 and a == 0x5f00 + F_RAIDER and b == F_RAIDER, 'EV_FOE_DOWN for a raider: its tag and kind', 'x%d a %#x b %d' % (n - n0, a, b))
mb(58, 0)
n0 = ev(FOE_DOWN)[0]
mb(48, 8)
for t in range(4):                                    # (the guns first, then the bays: the core is shielded till then)
    mb(56, 1 << 8 | 255)
mb(56, 2 << 8 | 255), mb(56, 2 << 8 | 255)
r = mb(56, 255)
run(3)
n, a, b = ev(FOE_DOWN)
ck(r == 1 and n > n0 and a == 0x5ff8 and b == F_HULL, 'EV_FOE_DOWN for the mothership\'s body: the boss tag, kind hull', 'x%d a %#x b %d' % (n - n0, a, b))
px, py, pz = mb(61, 1), mb(61, 2), mb(61, 3)
p0 = ev(PICKUP)[0]
tele_ship([px, py, pz], f=(0, 0, 16384))
run(4)
n, a, b = ev(PICKUP)
ck(n - p0 == 1 and a == 0x5ff8, 'EV_PICKUP: the boss\'s pod, with the boss\'s tag', 'x%d a %#x' % (n - p0, a))
ck.done()
