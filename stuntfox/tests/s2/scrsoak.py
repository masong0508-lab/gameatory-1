"""Random-play soak for the black-screen fix (tests/s2/scrfix.py has the cause): seeded random pad play on one map, with the
things that make Payback write effect records forced now and then (cars shot to pieces, our fox medals picked up again, bursts
on top of full kinds) and these watched all along:

  - the game's own frame counter (key_calls) keeps moving, in every window of 300 emulated frames,
  - the screen is not black for long (a fade is; 120 frames of it in a row is not),
  - no kind of effect record is ever past slot 63, and Payback writes nothing into scr (a write watch over 6 frames of every 150),
  - how often r_begin found its lowest words in bucket / bused set and cleared the lists whole (bage = 1 outside the 256th frame).

    SP=<harness folder> ROM=x.gba ELF=x.elf MAP=8 FRAMES=72000 SEED=1 python3 tests/s2/scrsoak.py      (from stuntfox/)
"""
import os
import random
import struct

import numpy as np

import h
from h import *

MAP = int(os.environ.get('MAP', '8'))
FRAMES = int(os.environ.get('FRAMES', '72000'))
rng = random.Random(int(os.environ.get('SEED', '1')))
CNT = 0x0200c41e
SCR_LO, SCR_HI = 0x02017fc4, 0x02019404
SETS = [['UP'], ['UP'], ['UP', 'A'], ['DOWN'], ['LEFT'], ['RIGHT'], ['UP', 'LEFT'], ['UP', 'RIGHT'], ['A'], ['B'], ['R'], ['L'],
        ['UP', 'R'], ['A', 'R'], ['A', 'L'], ['SELECT'], [], []]
ck = Check()
gstate(MAP)
e.run(60)
board_now()


def counts():
    return struct.unpack('<4h', e.read(CNT, 8))


def pb_writes(frames, keys):
    pcs = {}
    for _ in range(frames):
        e.watch(SCR_LO, SCR_HI, 1)
        e.run(1, list(keys))
        for pc, a, v, lr, sz, w, th in e.hits():
            if w and 0x08000000 <= pc < 0x081b0000:
                pcs[pc] = pcs.get(pc, 0) + 1
    e.watch(0, 0, 0)
    return pcs


def shoot_a_car():
    cars = [x for x in ents() if x[3] in (3, 4) and x[2] >= 5 and x[5] > 0]
    if modename() != 'FLY' or not cars:
        return 0
    c = rng.choice(cars)
    x, y = c[4][0], c[4][1]
    tele_ship([int(x * 1024), 900, int((y - 2.5) * 1024)], f=(0, -5000, 15600))
    return 1


def medals():
    """Our fox medals again: forget the ones found and fly the ship through each place (spacegame.c pickups)."""
    if modename() != 'FLY' or 'medal_at' not in S:
        return 0
    e.write8(S['medals'], 0), e.write8(S['medals'] + 1, 0)
    for i in range(12):
        v = struct.unpack('<3i', e.read(S['medal_at'] + 12 * i, 12))
        tele_ship(list(v))
        e.run(3)
    return 1


f = 0
maxc = [-1] * 4
last_k, last_chk, black_run, black_max = kc(), 0, 0, 0
stuck = 0
clears = 0
clear_at = []
bage0 = e.read(S['bage'], 1)[0]
shots = meds = 0
bad = {}
nextev, nextwatch = 400, 150
while f < FRAMES:
    r = rng.random()
    if f >= nextev:
        nextev = f + rng.randint(250, 600)
        if rng.random() < 0.8:
            if rng.random() < 0.3:                 # (a kind nearly full: the next burst has to stop at the cap, not past it)
                k = rng.randrange(4)
                v = rng.randint(40, 63)
                e.write8(CNT + 2 * k, v), e.write8(CNT + 2 * k + 1, 0)
            shots += shoot_a_car()
            n, keys = rng.randint(250, 400), ["R"]
        else:
            meds += medals()
            n, keys = 20, []
    elif r < 0.012:
        n, keys = 50, ['SELECT']
    elif r < 0.016:
        e.run(4, ['START']), e.run(24), e.run(4, ['START'])
        f += 32
        continue
    else:
        n, keys = rng.randint(8, 40), rng.choice(SETS)
    if f >= nextwatch:
        nextwatch = f + 150
        for pc, c in pb_writes(6, keys).items():
            bad[pc] = bad.get(pc, 0) + c
        n = max(0, n - 6)
        f += 6
    # r_begin clears the lists whole on the first frame, after a new level (r_reset) and when bage wraps (the sample before it
    # reads 0); a 1 after any other value is the backstop (or a level's start) acting
    for _ in range(n):
        e.run(1, list(keys))
        b = e.read(S['bage'], 1)[0]
        if b == 1 and bage0 != 0 and bage0 != 1:
            clears += 1
            clear_at.append(f)
        bage0 = b
    f += n
    maxc = [max(m, v) for m, v in zip(maxc, counts())]
    if int(np.asarray(e.frame).max()) == 0:
        black_run += n
        black_max = max(black_max, black_run)
    else:
        black_run = 0
    if f - last_chk >= 300:
        last_chk = f
        k = kc()
        if k == last_k:
            # a pause, the game menu, game over: all of them stand still; press what leaves each (a freeze does not answer)
            e.frame.save('%s/stuck_%d_%d.png' % (os.environ.get('OUT', '/tmp'), MAP, f))
            seen = status()[:90]
            back = False
            for keys2 in (['START'], ['A'], ['A'], ['START'], ['B'], ['A'], ['START']):
                e.run(4, keys2)
                e.run(90)
                f += 94
                if kc() != k:
                    back = True
                    break
            print('no Payback frame in the window ending at', f, seen, '->', 'back after a key' if back else 'NOT BACK', flush=True)
            if not back:
                stuck += 1
            k = kc()
        last_k = k
print('map %d frames %d: car shots %d, medal rounds %d, kinds max %s, stuck windows %d, black run max %d frames, '
      'unexplained whole clears by r_begin %d %s, Payback writes into scr %s' %
      (MAP, f, shots, meds, maxc, stuck, black_max, clears, clear_at[:12], {hex(p): n for p, n in bad.items()}))
ck(stuck == 0, 'no window without a Payback frame')
ck(black_max < 120, 'the screen is never black for long', '%d frames' % black_max)
ck(max(maxc) <= 63, 'no kind of effect past slot 63', str(maxc))
ck(not bad, 'nothing of Payback writes into scr')
ck.done()
