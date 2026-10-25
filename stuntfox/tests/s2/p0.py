"""Probe P0: is the tail of Payback's third pool, 0x02017fc4-0x02019404 (merge.ld's scr), ever written by Payback?
A touch map of every store into it, a frame at a time, over a long run of rough play (random keys on foot, in a car
and in the Arwing, deaths, a level end and the next map, the pause menu), story and rampage; each store is Payback's,
ours (the pc is in the linked ELF's code in ROM, or in a lent IWRAM region that held the ELF's bytes at the start or the
end of that frame: our code is lent places of Payback's code there) or Payback's (any other pc, or a lent region that
held Payback's code at both ends of the frame). A control run of the same classifier on a word Payback writes every tick
(its level clock) shows it does tell them apart. Advice only: nothing in the tree moves because of it.

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/p0.py [frames-per-stretch, default 1500: about 3 minutes in all]      (from stuntfox/)
"""
import collections
import random
import re
import subprocess
import sys
import h
from h import *

LO, HI = 0x02017fc4, 0x02019404
PER = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
random.seed(7)
text = subprocess.run(['llvm-readelf', '-S', '-W', ELF], capture_output=True, text=True, check=True).stdout
elf = open(ELF, 'rb').read()
ours = []                                          # (address, end, file offset, name) of the ELF's code sections
for m in re.finditer(r'\]\s+(\S+)\s+\S+\s+([0-9a-f]{8})\s+([0-9a-f]+)\s+([0-9a-f]+)\s+\S+\s+(\S*)', text):
    if 'X' in m.group(5) and int(m.group(4), 16):
        a0 = int(m.group(2), 16)
        ours.append((a0, a0 + int(m.group(4), 16), int(m.group(3), 16), m.group(1)))
verdict = {}                                       # pc -> who, for the frame being run
resident = {}                                      # section name -> held our bytes at the start or the end of the frame


def holds(a0, b0, off):
    return e.read(a0, b0 - a0) == elf[off:off + b0 - a0]


def frame_start():
    verdict.clear()
    resident.clear()
    for a0, b0, off, n in ours:
        if a0 >= 0x03000000:
            resident[n] = holds(a0, b0, off)


def frame_end():
    for a0, b0, off, n in ours:
        if a0 >= 0x03000000 and not resident[n]:
            resident[n] = holds(a0, b0, off)


def who(pc):
    """'ours' or 'payback' (call after frame_end)."""
    if pc in verdict:
        return verdict[pc]
    v = 'payback'
    for a0, b0, off, n in ours:
        if a0 <= pc < b0:
            v = 'ours' if a0 < 0x03000000 or resident[n] else 'payback'
            break
    verdict[pc] = v
    return v


n_ours = frames = overflow = 0
pb = collections.Counter()
touched = [0] * (HI - LO)
KEYS = [['A'], ['UP'], ['A', 'LEFT'], ['A', 'RIGHT'], ['B'], ['A', 'R'], ['DOWN'], ['UP', 'LEFT'], ['A', 'UP'], ['A', 'DOWN'], [], ['A', 'L'], ['START']]


def play(n, label):
    global n_ours, frames, overflow
    keys = random.choice(KEYS)
    for i in range(n):
        if i % 20 == 0:
            keys = random.choice(KEYS)
            if keys == ['START'] and random.random() < 0.8:
                keys = ['A']
        frame_start()
        e.watch(LO, HI, 1)
        e.run(1, keys)
        frame_end()
        hits = e.hits()
        frames += 1
        if len(hits) >= 65536:
            overflow += 1
        for pc, addr, val, lr, size, write, thumb in hits:
            if who(pc) == 'ours':
                n_ours += 1
            else:
                pb[(pc, lr)] += 1
            for k in range(size):
                if LO <= addr + k < HI:
                    touched[addr + k - LO] = 1


def die():
    c = ctl() or PL
    e.write8(c + 0x68, 0), e.write8(c + 0x69, 0)


def rampage(g):
    gstate(g)
    play(PER // 3, 'foot g%d' % g)
    c = get_car(tries=3, maxd=30)
    play(PER // 3, 'car g%d' % g)
    if modename() == 'DRIVE':
        run(6, ['L'])
    if board_now() == 'FLY':
        play(PER // 3, 'arwing g%d' % g)
    die()
    play(300, 'death g%d' % g)
    run(6, ['START'])
    play(120, 'pause g%d' % g)
    run(6, ['START'])
    print('after rampage g%d: frames %d ours %d payback %d' % (g, frames, n_ours, sum(pb.values())), flush=True)


for g in (0, 4, 8):
    rampage(g)
# a level end and the next map
gstate(0)
play(120, 'g0')
e.write32(PL + 0x90, 9999999)
play(120, 'level end')
run(6, ['SELECT'])
play(900, 'next map load and start')
print('after level end: frames %d ours %d payback %d' % (frames, n_ours, sum(pb.values())), flush=True)
# story: a new game from the title
title_state()
for _ in range(1):
    tap('A', after=80)
for _ in range(11):
    tap('A', after=60)
play(PER, 'story start')
play(PER, 'story walk')
print('after story: frames %d ours %d payback %d' % (frames, n_ours, sum(pb.values())), flush=True)
words_touched = sum(touched)
print('P0: %d frames (%.1f minutes), stores into 0x%08x-0x%08x: ours %d, Payback\'s %d; %d of %d bytes touched; %d frames over the hit buffer' %
      (frames, frames / 3600.0, LO, HI, n_ours, sum(pb.values()), words_touched, HI - LO, overflow))
for (pc, lr), n in pb.most_common(12):
    print('   Payback store from pc %08x (lr %08x) x %d' % (pc, lr, n))
# the control: the same classifier on Payback's level clock, which it writes every tick
gstate(0)
run(30)
c_ours = c_pb = 0
for _ in range(120):
    frame_start()
    e.watch(0x02001e00, 0x02001e04, 1)
    run(1)
    frame_end()
    for pc, addr, val, lr, size, write, thumb in e.hits():
        if who(pc) == 'ours':
            c_ours += 1
        else:
            c_pb += 1
print('control, the level clock 0x02001e00 over 120 frames: Payback %d stores, ours %d' % (c_pb, c_ours))
print('P0 RESULT:', ('Payback never wrote it' if not pb else 'Payback WROTE it') + ('; control saw Payback\'s stores' if c_pb else '; CONTROL FAILED'))
