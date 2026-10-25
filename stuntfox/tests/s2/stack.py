"""The stack's depth in the city fight (package K): the deepest IWRAM write above the stack's floor (0x03007388, where the
globals end) over close-up views of every boss with raiders and aces round it, at four distances and three sides (the clipper
recurses when a face crosses the view). The margin to the floor has to stay at 400 bytes or more.

    SP=<harness folder> ROM=x.gba ELF=x.elf python3 tests/s2/stack.py        (from stuntfox/)
"""
import h
from h import *

merged_state(e)
run(30)
assert board_now() == 'FLY'
e.write8(S['sg_shield_k'], 255)
me = epos(PL)
X, Z = int(me[0] * 1024), int(me[1] * 1024)
FOE = 48
LO = 0x03007390                                       # (the watch starts a little over the floor)
worst = (0x03008000, None)
ck = Check()
FLOOR, NEED = 0x03007388, 400


def foe(i):
    b = e.read(S['sg_foes'] + FOE * i, FOE)
    p = struct.unpack_from('<3i', b, 0)
    hp, kind, cool, ai, fl, tag = struct.unpack_from('<hBBBBH', b, 36)
    return dict(p=p, hp=hp, kind=kind, fl=fl)


def place(y=2400):
    tele_ship([X, y, Z - 2000], f=(0, -3000, 15900))
    run(2)


for boss in range(9):
    place()
    mb(58, 0)
    mb(49)
    run(2)
    place()
    mb(48, boss)
    for k in (1, 4, 1, 4):
        mb(51, k)
    mb(57, 1)
    run(6)
    body = [i for i in range(8) if foe(i)['kind'] and foe(i)['fl'] >> 4 and foe(i)['kind'] not in (3, 7)][0]
    bp = foe(body)['p']
    res = []
    for dist_ in (500, 1200, 2500, 5000):
        for side in (0, 1500, -1500):
            for look in (0, 1):
                f = (0, -1000, 16384) if not look else (side * -1, 0, 16384)
                tele_ship([bp[0] + side, bp[1] + 200, bp[2] - dist_], f=f)
                mn = 0x03008000
                for fr in range(5):
                    e.watch(LO, 0x03007f00, 1)
                    e.run(1)
                    for (pc, addr, val, lr, size, wr, th) in e.hits():
                        if addr < mn:
                            mn = addr
                res.append(mn)
                if mn < worst[0]:
                    worst = (mn, (boss, dist_, side, look))
    e.watch(0, 0, 0)
    ck(min(res) - FLOOR >= NEED, 'boss %d: stack margin to the floor' % boss, 'lowest write 0x%08x, margin %d' % (min(res), min(res) - FLOOR))
ck(worst[0] - FLOOR >= NEED, 'the worst of all, boss %d at distance %d, side %d, look %d' % ((worst[1][0],) + worst[1][1:]), 'margin %d bytes (need %d)' % (worst[0] - FLOOR, NEED))
ck.done()
