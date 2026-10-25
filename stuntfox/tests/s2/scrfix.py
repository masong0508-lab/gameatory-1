"""The black screen after a burst of effect records: Payback's emitter (0x08073bb0) wrote its records up to slot 99 of 0x02015bc4
(0x90 a slot, 0x24 a kind), over our scr (slots 64..99), and the renderer then followed garbage lists for ever. A car shot to
pieces is one such burst (kind 1 filled up to its cap). build.py MERGE_FX_CAP stops the emitter at slot 63.

The Arwing shoots parked cars on one map; the count of each kind, Payback's writes into scr (a write watch, one frame at a time)
and whether its frames keep coming and the picture stays are checked. On the build before the fix map 8 (and 0, 2) freeze at the
first car and 5 writes over scr; the fixed one passes on all 11 maps.

    SP=<harness folder> ROM=x.gba ELF=x.elf MAP=8 [PRESET=-1] python3 tests/s2/scrfix.py      (from stuntfox/)

PRESET is what every kind's count is set to first (-1: empty, as a level starts; 62: nearly full; above 63 is a state the fixed
build cannot reach, so it only shows what a burst finds there).
"""
import os
import struct

import numpy as np

import h
from h import *

CNT = 0x0200c41e                      # Payback: s16 count of records for each of the 4 kinds (slot = count, -1 empty)
POOL, SLOT = 0x02015bc4, 0x90
SCR_LO, SCR_HI = 0x02017fc4, 0x02019404
ck = Check()
PRESET = int(os.environ.get('PRESET', '-1'))


def counts():
    return [struct.unpack('<h', e.read(CNT + 2 * t, 2))[0] for t in range(4)]


def scr_words():
    return e.read(SCR_LO, SCR_HI - SCR_LO)


def payback_writes(frames, keys=()):
    """Run frames one at a time with a write watch over scr: the writes that come from Payback's ROM code (not ours, which
    starts at 0x081b0000 or runs from IWRAM), as {pc: n}."""
    pcs = {}
    for _ in range(frames):
        e.watch(SCR_LO, SCR_HI, 1)
        e.run(1, list(keys))
        for pc, a, v, lr, sz, w, th in e.hits():
            if w and 0x08000000 <= pc < 0x081b0000:
                pcs[pc] = pcs.get(pc, 0) + 1
    e.watch(0, 0, 0)
    return pcs


MAP = int(os.environ.get('MAP', '8'))
gstate(MAP)
e.run(60)
board_now()
ck(modename() == 'FLY', 'in the Arwing on map %d' % MAP + '', status())
cars = [x for x in ents() if x[3] in (3, 4) and x[2] >= 5 and x[5] > 0]
ck(len(cars) >= 3, 'cars to shoot', '%d' % len(cars))
for t in range(4):
    e.write8(CNT + 2 * t, PRESET & 255), e.write8(CNT + 2 * t + 1, PRESET >> 8)
k0 = kc()
bad = {}
maxc = [0] * 4
for c in cars[:8]:
    x, y = c[4][0], c[4][1]
    tele_ship([int(x * 1024), 900, int((y - 2.5) * 1024)], f=(0, -5000, 15600))
    for _ in range(40):
        a = kc()
        for pc, n in payback_writes(10, ['R']).items():
            bad[pc] = bad.get(pc, 0) + n
        maxc = [max(m, v) for m, v in zip(maxc, counts())]
        if kc() == a:                  # no Payback frame in 10 emulated frames (a frame lasts 3 to 4)
            break
    if kc() == a:
        break
alive = kc() - k0
e.run(120)
moved = kc() != k0 + alive
print('counts max', maxc, 'now', counts(), 'Payback writes into scr from', {hex(p): n for p, n in bad.items()})
print('frames of Payback seen', alive, 'black' if int(np.asarray(e.frame).max()) == 0 else 'picture', 'running again' if moved else 'STUCK')
ck(not bad, 'nothing of Payback writes into scr', 'writers %s' % {hex(p): n for p, n in bad.items()})
ck(max(maxc) <= max(63, PRESET), 'no kind past slot 63 (a preset above it is our own poke)', 'max %d' % max(maxc))
ck(alive > 20 and moved, 'the frames keep coming', '%d frames' % alive)
ck(int(np.asarray(e.frame).max()) > 0, 'the picture is not black')
ck.done()
