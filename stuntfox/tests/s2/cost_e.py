"""What the mission engine costs, in cycles per call, measured at the hook call sites (a breakpoint on each `bl s2_tick/s2_draw3d/s2_hud`
and on the instruction after it; the emulator's cycle counter at both gives the call's inclusive time, interrupts included),
and, from the PC histogram, the self time per frame of ours of every function that mission.c, hudline.c and msn_draw.c add.
The gates: s2_tick <= 8k, s2_draw3d <= 10k, s2_hud <= 4k (each with everything it calls), no added function above 5k a frame.
The worst scene counts: the ring run's first ring 5 and 3 cells ahead is the heaviest case there is.
The gate is on the typical call: the mean without the slowest 3% of the calls, because Payback's own sound interrupt (~20k
cycles) lands inside one call in about sixty and is not ours; the plain mean and the maximum are printed beside it. The scenes
are measured with the act's card gone (a card is a transient: it has its own scene and its own limit, 18k a frame for the
three seconds it is up, 18k a frame; the line is the steady cost).

    SP=<harness folder> ROM=x.gba ELF=x.elf python3 tests/s2/cost_e.py      (from stuntfox/)
"""
import collections
import subprocess

import h
from h import *
import numpy as np

OBJS = ('mission', 'hudline', 'msn_draw')
syms = []
for line in subprocess.run(['llvm-nm', '-S', '--defined-only', ELF], capture_output=True, text=True).stdout.splitlines():
    p = line.split()
    if len(p) == 4:
        syms.append((int(p[0], 16) & ~1, int(p[1], 16), p[3]))
mine = set()
for o in OBJS:
    path = os.path.join(START, 'build', 'merge', o + '.c.o')
    mine |= {l.split()[2] for l in subprocess.run(['llvm-nm', '--defined-only', path], capture_output=True, text=True).stdout.splitlines()
             if len(l.split()) == 3 and l.split()[1] in 'tT'}
HOOKS = ('s2_tick', 's2_draw3d', 's2_hud')
LIMIT = {'s2_tick': 8000, 's2_draw3d': 10000, 's2_hud': 4000}
CARD_LIMIT = 18000                                          # (s2_hud, a card up with the line: ~30 letters a line, 14 rows, 24 cycles a byte of a row)
site = {}                                                   # call site (the bl) of each hook in the merged code
for line in subprocess.run(['llvm-objdump', '-d', ELF], capture_output=True, text=True).stdout.splitlines():
    for hk in HOOKS:
        if ('<%s>' % hk) in line and '\tbl\t' in line:
            site[hk] = int(line.split(':')[0], 16)
ck = Check()
ck(set(site) == set(HOOKS), 'each hook has one call site', str(site))


def name(a):
    for lo, sz, n in syms:
        if lo <= a < lo + max(sz, 1):
            return n
    return 'payback' if a < 0x081b0000 else hex(a & ~0xff)


def measure(title, frames=300, keys=(), step=None, every=6):
    """step: called before every `every` frames (puts the player back, so a ring stays near)."""
    bps = [site[hk] + off for hk in HOOKS for off in (0, 4)]
    h0 = hooks()['TICK']
    e.prof_on(bps=bps)
    if step:
        for _ in range(frames // every):
            step()
            run(every, list(keys))
    else:
        run(frames, list(keys))
    hist, bplog, busy = e.prof_off()
    n = max((hooks()['TICK'] - h0) & 0xffff, 1)
    cost = {}
    for j, hk in enumerate(HOOKS):
        t_in, d = None, []
        for b, v in bplog:
            if b == 2 * j:
                t_in = v
            elif b == 2 * j + 1 and t_in is not None:
                d.append(v - t_in)
                t_in = None
        q = sorted(d)[:max(len(d) - len(d) * 3 // 100, 1)]
        cost[hk] = (sum(q) / max(len(q), 1), sum(d) / max(len(d), 1), max(d) if d else 0, len(d))
    tot = collections.Counter()
    for i in np.nonzero(hist)[0]:
        if i >= 0x403fff:
            continue
        a = 0x03000000 + ((i - 0x400000) << 1) if i >= 0x400000 else 0x08000000 + (i << 1)
        tot[name(a)] += int(hist[i])
    own = {k: v / n for k, v in tot.items() if k in mine}
    print('%s: %d frames of ours in %d' % (title, n, frames))
    for hk in HOOKS:
        print('   %-10s typical %7.0f  mean %7.0f  max %7d cycles a call (%d calls)' % ((hk,) + cost[hk]))
    for k, v in sorted(own.items(), key=lambda kv: -kv[1])[:6]:
        print('      %-22s %6.0f self cycles a frame of ours' % (k, v))
    return cost, own


GONE = 700                                   # (frames after a start: the title banner 440, then the card 180)


def settle(f=GONE):
    run(f)


def typ(r, hk):
    return r[0][hk][0]


res, cards = [], []
merged_state(e)
run(30)
tele_man(14.5, 52.5)                         # (6 cells before the act's beacon, facing it)
e.write8(PL + 0x12, 0)
e.write8(PL + 0x13, 0)
fm_break()
mb(10, 1)                                    # (no roaming: arm exactly the act)
mb(6, 0)
settle(120)
res.append(measure('map 0 on foot, the beacon ahead, the line up (armed)'))
mb(1, 0)
settle(480)                                  # (the banner is gone, the card is up from tick 220 to 310)
cards.append(measure('map 0 on foot, the act just begun: the card up with the line', frames=120))
settle(220)
res.append(measure('map 0 on foot, the act running (marker arrow, line)'))
mb(1, 1)
settle()
res.append(measure('map 0 on foot, a timed challenge running (clock in the line)'))
mb(9)
gstate(3)
mb(10, 1)
run(30)
board_now()
tele_ship((59 * 1024, 1700, 70 * 1024), (16384, 0, 0), (0, 0, 0))
run(4)
assert mb(1, 4) == 1
settle()
tele_ship((59 * 1024, 1700, 70 * 1024), (16384, 0, 0), (0, 0, 0))
res.append(measure('map 3 in the Arwing, the ring run (ring, bracket, line)'))

for x_cells in (59, 61):                     # ring 1 of the run is at x 64: 5 cells ahead, and 3
    def near():
        tele_ship((x_cells * 1024, 1700, 70 * 1024), (16384, 0, 0), (0, 0, 0))
        mb(11, 0)                                 # (the count held at 0: ring 1 is the one drawn, and the bracket for ring 2)
    near()
    run(6)
    res.append(measure('map 3 in the Arwing, ring 1 of the run %d cells ahead (count held at 0)' % (64 - x_cells), step=near))
for hk in HOOKS:
    worst = max(typ(r, hk) for r in res)
    ck(worst <= LIMIT[hk], '%s under %dk cycles a call, with everything it calls' % (hk, LIMIT[hk] // 1000), 'worst scene typical %.0f' % worst)
card = max(typ(r, 's2_hud') for r in cards)
ck(card <= CARD_LIMIT, 's2_hud with a card up under %dk cycles a call (it is up for three seconds)' % (CARD_LIMIT // 1000), 'typical %.0f' % card)
big = max([v for r in res for v in r[1].values()] + [0])
ck(big <= 5000, 'no function the mission adds is above 5k cycles a frame of ours', 'largest %.0f' % big)
ck.done()
