"""A soak of the station in the emulator: on each map a few minutes of cycles, board the Arwing, fly to the station, dock, walk
into the hub and a few rooms (talks, consoles, the quick menu, doors), out to the hangar, LAUNCH, fly: with the frame hook running
every cycle, Payback's sprites back on after each launch, the station back at the hangar, the state not grown, no hang.

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/soak_station.py [frames per map] [maps...]        (from stuntfox/)
"""
import random
import struct
import sys
import h
from h import *

ck = Check()
FRAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 18000          # five minutes at 60 Hz
MAPS = [int(a) for a in sys.argv[2:]] or [0, 4, 8]
random.seed(7)


def setv(a, v):
    for i in range(3):
        e.write32(a + 4 * i, int(v[i]) & 0xffffffff)


def dispcnt():
    return struct.unpack('<H', e.read(0x4000000, 2))[0]


def htap(k, hold=8, after=14):
    tap(k, hold=hold, after=after)


def goto_line(n):
    for _ in range(8):
        if r8(S['menu']) == 0 and r8(S['cursor']) == n:
            return True
        htap('DOWN')
    return False


def dock_here():
    B = S['ship']
    sx, sy, sz = [r32(S['station_pos'] + 4 * i) for i in range(3)]
    setv(B, ((sx + 3000) << 8, (sy - 140) << 8, (sz + 9000) << 8))
    setv(B + 12, (0, 0, -(90 << 8)))
    setv(B + 24, (-16384, 0, 0))
    setv(B + 36, (0, 16384, 0))
    setv(B + 48, (0, 0, -16384))
    run(20, ['A'])
    run(40, ['SELECT'])
    for k in range(40):
        run(30)
        if r32(S['sg_state']) == 2:
            return True
    return False


for g in MAPS:
    gstate(g)
    run(60)
    cycles, kc0, bad = 0, r32(S['key_calls']), 0
    fc0 = r32(S['frame_count'])
    t0 = hooks()['DRAW3D']
    frames = 0
    while frames < FRAMES:
        if modename() != 'FLY' and board_now() != 'FLY':
            bad += 1
            print('map %d cycle %d: no Arwing (mode %s)' % (g, cycles, modename()))
            gstate(g)
            run(60)
            continue
        if not dock_here():
            bad += 1
            print('map %d cycle %d: did not dock (state %d)' % (g, cycles, r32(S['sg_state'])))
            gstate(g)
            run(60)
            continue
        run(60)
        goto_line(4)
        htap('A', after=40)
        if mb(33, 0) != 1:
            bad += 1
            print('map %d cycle %d: STATION did not open the hub (room %s)' % (g, cycles, mb(33, 0)))
        for step in range(random.randint(6, 10)):
            what = random.randint(0, 5)
            if what == 0:
                run(random.randint(20, 90), [random.choice(['LEFT', 'RIGHT', 'UP', 'DOWN'])])
            elif what == 1:
                mb(34, random.randint(1, 8))
                run(30)
            elif what == 2:
                htap('A', after=12)
                for _ in range(4):
                    htap('A', after=10)
                if mb(33, 4) & 255:
                    htap('B', after=14)
            elif what == 3:
                htap('L', after=20)
                htap('B', after=20)
            elif what == 4:
                run(random.randint(20, 60), ['R', random.choice(['LEFT', 'RIGHT'])])
            else:
                htap('B', after=30)
                if mb(33, 0) == 0:
                    run(50)
                    goto_line(4)
                    htap('A', after=40)       # (in the hangar: the STATION line again, once the hold is over)
        mb(34, 1), run(10)
        htap('B', after=60)                    # (the hold on the way out: the hub's B waits it out)
        run(40)
        htap('B', after=60)
        run(60)
        if mb(33, 0) != 0:
            bad += 1
            print('map %d cycle %d: not at the hangar (room %s)' % (g, cycles, mb(33, 0)))
        if not dispcnt() & 0x1000:
            bad += 1
            print('map %d cycle %d: sprites still off in the hangar' % (g, cycles))
        goto_line(5)
        htap('A', after=10)
        for k in range(40):
            run(15)
            if r32(S['sg_state']) != 2:
                break
        run(200)
        if r32(S['sg_state']) == 2 or not dispcnt() & 0x1000:
            bad += 1
            print('map %d cycle %d: launch left state %d dispcnt %s' % (g, cycles, r32(S['sg_state']), hex(dispcnt())))
        cycles += 1
        frames = (r32(S['frame_count']) - fc0) & 0xffffffff
    ck(bad == 0 and cycles >= 3, 'map %d: %d cycles over %d frames, nothing wrong' % (g, cycles, frames), 'bad %d' % bad)
    ck(r32(S['key_calls']) > kc0 and mb(33, 17) == 52, 'map %d: the frame hook still runs, the state is as big as it was' % g)
ck.done()
