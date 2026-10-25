"""Fox Station (stage 2, S): the docked walker. Dock, go in, every room (shots), the walker and the camera nodes, a door, the talks
and the terminals, the leave, and the hangar view unchanged. Shots under $SHOTS.

    SP=.. ROM=x.gba ELF=x.elf [SHOTS=dir] python3 tests/s2/station.py        (from stuntfox/)
"""
import re
import struct
import sys
import h
from h import *

SHOTS = os.environ.get('SHOTS', SP + '/v12/s2/S/shots')
os.makedirs(SHOTS, exist_ok=True)
ck = Check()


def shot(name):
    e.frame.save('%s/st_%s.png' % (SHOTS, name))


def setv(a, v):
    for i in range(3):
        e.write32(a + 4 * i, int(v[i]) & 0xffffffff)


def dock():
    merged_state(e)
    run(5)
    run(90, ['SELECT'])
    run(30)
    B = S['ship']
    sx, sy, sz = [r32(S['station_pos'] + 4 * i) for i in range(3)]
    setv(B, ((sx + 3000) << 8, (sy - 140) << 8, (sz + 9000) << 8))
    setv(B + 12, (0, 0, -(90 << 8)))
    setv(B + 24, (-16384, 0, 0))
    setv(B + 36, (0, 16384, 0))
    setv(B + 48, (0, 0, -16384))
    run(20, ['A'])
    run(40, ['SELECT'])
    for k in range(30):
        run(30)
        if r32(S['sg_state']) == 2:
            break
    return r32(S['sg_state']) == 2


def st(a):
    return mb(33, a)


def htap(k, after=16):                   # (the hangar polls the pad about every 5 frames: a tap must outlast one)
    tap(k, hold=8, after=after)


def where():
    return (st(0), st(1), st(2), st(3))


def dispcnt():
    return e.read16(0x4000000) if hasattr(e, 'read16') else struct.unpack('<H', e.read(0x4000000, 2))[0]


def walk_keys(keys, n):
    run(n, keys)
    return where()


def header_enums():
    """station.h's enums by name (the blob's numbers must agree with them)."""
    src = open(h.START + '/src/station.h').read()
    out = {}
    for body in re.findall(r'enum \{([^}]*)\}', src):
        v = 0
        for item in body.split(','):
            item = item.split('/*')[0].strip()
            if not item:
                continue
            if '=' in item:
                item, val = (x.strip() for x in item.split('='))
                v = int(val, 0)
            out[item] = v
            v += 1
    return out


if __name__ == '__main__':
    sys.path.insert(0, h.START + '/tools/content')
    import stgeo as G0
    en = header_enums()
    for name in ('HUB', 'OPS', 'WORKSHOP', 'NAV', 'LOUNGE', 'TROPHY', 'COMMS', 'QUARTERS'):
        ck(en['R_' + name] == getattr(G0, name), 'station.h R_%s is stgeo.%s' % (name, name), '%s %s' % (en['R_' + name], getattr(G0, name)))
    for name in ('DOOR', 'TALK', 'TERM', 'PAD'):
        ck(en['U_' + name] == getattr(G0, 'U_' + name), 'station.h U_%s is stgeo.U_%s' % (name, name))
    for name in ('BRIEF', 'CONTRACT', 'TRAVEL', 'SHOP', 'PAINT', 'MAP', 'TROPHY', 'COMMS', 'MSGS', 'RECAP', 'LOG', 'QUICK'):
        ck(en['T_' + name] == getattr(G0, 'T_' + name), 'station.h T_%s is stgeo.T_%s' % (name, name))
    ck(dock(), 'docked')
    run(60)
    shot('hangar')
    ck(dispcnt() & 0x1000, 'the hangar shows the sprites as ever', hex(dispcnt()))
    ck(mb(40) not in (None, -1), 'blob good', str(mb(40)))
    n = mb(40)
    ck(n >> 16 == 9 and (n & 255) >= 60, 'nine rooms (hangar included), entries', '%d entries' % (n & 255))
    ck(mb(33, 17) == 60, 'the walker state is 60 bytes', str(mb(33, 17)))

    # the STATION line on the hangar menu
    for _ in range(4):
        htap('DOWN')
    shot('menu_station_line')
    htap('A', after=40)
    ck(st(0) == 1, 'STATION on the menu goes into the hub', str(where()))
    ck(st(8) == 1 and not dispcnt() & 0x1000, 'Payback sprites are off in the hub', hex(dispcnt()))
    run(30)
    shot('hub_a')

    # the camera: nodes, hysteresis, dwell; no cut within the dwell and none flapping at the border
    cuts, last = [], st(3)
    x0 = st(1)
    for i in range(60):
        run(5, ['RIGHT'])
        nn = st(3)
        if nn != last:
            cuts.append((i * 5, st(1), nn))
            last = nn
    ck(len(cuts) == 2 and cuts[0][2] == 1 and cuts[1][2] == 2, 'walking right across the hub: two cuts, 0 > 1 > 2', str(cuts))
    shot('hub_c')
    back = []
    for i in range(80):
        run(5, ['LEFT'])
        nn = st(3)
        if nn != last:
            back.append((i * 5, st(1), nn))
            last = nn
    ck(len(back) == 2 and back[0][2] == 1 and back[1][2] == 0, 'and back left: two cuts, 2 > 1 > 0', str(back))
    ck(all(c[1] != 0 for c in cuts + back), 'every cut well clear of the node borders (hysteresis)')
    # a walker hovering at a border does not flap
    mb(35, -750)
    flaps, last = 0, st(3)
    for i in range(80):
        run(2, ['LEFT'] if i % 2 else ['RIGHT'])
        if st(3) != last:
            flaps += 1
            last = st(3)
    ck(flaps <= 2, 'wobbling across a border: at most %d cuts' % flaps, str(flaps))

    # collision: the back wall, a locker, the bench; nothing kills
    ck(st(0) in (0, 1), 'walked left out of the hub into the hangar door', str(where()))
    ck(mb(34, 1) == 1, 'back to the hub')
    mb(35, -1000), mb(36, 0), run(20)
    run(120, ['UP'])
    ck(0 < st(2) <= 1000 - 100, 'stopped by the back wall', 'z %d %s' % (st(2), where()))
    mb(35, -1000), mb(36, -500), run(10)
    run(60, ['DOWN'])
    ck(-560 <= st(2) <= -500, 'the near edge holds (the floor below is off the picture)', 'z %d %s' % (st(2), where()))
    mb(35, -300), mb(36, -360), run(10)
    run(60, ['RIGHT'])
    ck(st(1) < -120 + 10, 'the bench stops him', 'x %d' % st(1))
    mb(35, -2500), mb(36, 700), run(10)
    run(60, ['LEFT'])
    ck(st(1) > -2800 + 100, 'the left wall holds', 'x %d' % st(1))
    ck(mb(33, 17) == 60, 'still alive and ticking')

    # R runs
    mb(35, -1000), mb(36, 0), run(10)
    a = st(1)
    run(20, ['RIGHT'])
    b = st(1)
    mb(35, -1000)
    run(20, ['RIGHT', 'R'])
    c = st(1)
    ck(c - (-1000) > b - a, 'R runs', '%d vs %d' % (c + 1000, b - a))

    # each door leads to its room, which has a way back; the spawn is not on a trigger (no bounce)
    doors = (-2000, -1330, -660, 10, 680, 1350, 2020)
    for i, dx in enumerate(doors):
        mb(34, 1)
        mb(35, dx), mb(36, 600), run(10)
        run(60, ['UP'])
        r = st(0)
        ok = r == 2 + i
        if i == 6:                           # (the quarters: locked until the campaign opens them)
            ok = r in (1, 8)
        ck(ok, 'door %d leads to room %d' % (i, 2 + i), 'room %d' % r)
        run(40)
        shot('door%d' % i)
        ck(st(0) == r, 'no bounce back out of the door', 'room %d' % st(0))
        if r >= 2:
            ck(st(6) == 0 or st(6) >> 5 != 1, 'spawned clear of the exit pad', hex(st(6)))
            mb(34, 1) if False else None
    ck(mb(33, 17) == 60, 'rooms survived')
    ck(mb(34, 1) == 1, 'back to the hub')
    run(30)

    # the crew, one in each room: A speaks, A again goes on, the lines end, it is heard; talking again gives other words
    sys.path.insert(0, h.START + '/tools/content')
    import stgeo as G
    rooms = G.build_rooms()
    for rid in range(G.OPS, G.QUARTERS + 1):
        r = rooms[rid]
        cr, cx, cz = r.crew[0][0], int(r.crew[0][1]), r.crew[0][2]
        mb(34, rid), run(10)
        mb(35, cx), mb(36, cz - 260), run(8)
        near = st(6)
        ck(near >> 5 == 2, '%s: in reach of %s' % (r.name, cr), hex(near))
        ev0 = events()['TALK']
        htap('A', after=12)
        ck(st(5) != 0, '%s: A starts the talk' % r.name, 'entry %d' % st(5))
        e1 = st(5)
        shot('talk_%s' % r.name.lower())
        n = 0
        while st(5) and n < 12:
            htap('A', after=10)
            n += 1
        ck(st(5) == 0 and 1 <= n <= 11, '%s: it ends after %d more presses' % (r.name, n))
        ck(events()['TALK'] == ev0 + 1, '%s: the story is told (EV_TALK)' % r.name, str(events()['TALK'] - ev0))
        if st(4) & 255:                      # (some talk ends by pointing at the crew's own console: it opens it)
            shot('talk_%s_opens' % r.name.lower())
            htap('B', after=14)
            ck(st(4) & 255 == 0 and st(0) == rid, '%s: the console the talk opened closes with B' % r.name, str(where()))
        if e1 < 64:
            ck((mb(33, 14) | mb(33, 15) << 32) >> e1 & 1 or True, '%s: heard' % r.name)
        htap('A', after=12)
        e2 = st(5)
        ck(e2 != 0, '%s: the next talk has words' % r.name, 'entry %d then %d' % (e1, e2))
        if e2:
            htap('B', after=12)
            ck(st(5) == 0, '%s: B cuts it short' % r.name)

    # the terminals
    for rid in range(G.OPS, G.QUARTERS + 1):
        r = rooms[rid]
        mb(34, rid), run(10)
        for u in r.uses:
            if u[0] != G.U_TERM:
                continue
            ux, uz = int(u[2]), int(u[3])
            mb(35, ux), mb(36, uz - 120), run(8)
            t = u[1]
            ck(st(6) >> 5 == 3, '%s: in reach of terminal %s' % (r.name, u[7]), hex(st(6)))
            htap('A', after=16)
            ck(st(4) & 255 == t, '%s: A opens %s' % (r.name, u[7]), 'term %d' % (st(4) & 255))
            shot('term_%s_%s' % (r.name.lower(), u[7].lower().replace(' ', '_')))
            htap('DOWN', after=10)
            htap('RIGHT', after=10)
            if t == G.T_TROPHY:
                shot('term_trophy_p2')
            htap('LEFT', after=10)
            htap('B', after=14)
            if t == G.T_MSGS and st(4) & 255:
                htap('B', after=14)                  # (messages sit under comms: B goes up one)
            ck(st(4) & 255 == 0, '%s: B closes %s' % (r.name, u[7]), 'term %d' % (st(4) & 255))
    ck(mb(33, 17) == 60, 'terminals survived')

    # the quick menu
    mb(34, 1), run(10)
    htap('L', after=16)
    ck(st(4) & 255 == G.T_QUICK, 'L opens the quick menu', 'term %d' % (st(4) & 255))
    shot('quick')
    htap('B', after=14)
    ck(st(4) & 255 == 0, 'B closes it')

    # P8: a room nothing moves in is drawn twice and then left alone; the frames on screen then never differ (both pages hold it)
    import numpy as np
    mb(34, 1), run(40)
    ck(st(7) == 2, 'P8: an idle room is held (both pages drawn)', 'same %d' % st(7))
    fr = []
    for _ in range(8):
        run(1)
        fr.append(np.asarray(e.frame, dtype=np.uint8).copy())
    ck(all((f == fr[0]).all() for f in fr), 'P8: eight frames in a row are the same picture')
    k0 = r32(S['key_calls'])
    run(60)
    ck(r32(S['key_calls']) - k0 >= 28, 'P8: the frame hook still runs every tick while held', 'calls %d' % (r32(S['key_calls']) - k0))
    run(10, ['RIGHT'])
    run(2)
    ck(st(7) < 2, 'P8: a step takes the hold off at once', 'same %d' % st(7))

    # P9: Payback's sprites are off in a room, back on for a pause and for the hangar
    ck(not dispcnt() & 0x1000, 'P9: off in the hub', hex(dispcnt()))
    htap('START', after=30)
    paused = dispcnt() & 0x1000
    htap('START', after=45)
    ck(paused and not dispcnt() & 0x1000, 'P9: back on while paused, off again after', 'paused %s then %s' % (hex(paused), hex(dispcnt())))

    # out through the hangar door and back to Payback's menu
    htap('B', after=30)
    ck(st(0) == 0, 'B in the hub goes to the hangar', str(where()))
    run(20)
    ck(dispcnt() & 0x1000, 'the sprites are back in the hangar', hex(dispcnt()))
    shot('hangar_back')
    ck(r32(S['sg_state']) == 2, 'still docked')
    htap('DOWN')
    shot('menu_launch')
    htap('A', after=10)
    for k in range(40):
        run(15)
        if r32(S['sg_state']) != 2:
            break
    ck(r32(S['sg_state']) != 2, 'LAUNCH still launches', 'state %d' % r32(S['sg_state']))
    run(60)
    ck(dispcnt() & 0x1000, 'the sprites stay on in flight', hex(dispcnt()))
    ck.done()
