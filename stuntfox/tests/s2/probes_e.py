"""Probes P4, P7 and P10 of the mission engine, on the built ROM (results go into the package report):

  P4   our arrow goal (kind 4, floor 0x7f, marker byte 0): Payback's "goal reached" (0x0806c22c) never runs for it, even
       with the man standing on it; the cell table is untouched; the arrow points at it
  P7   a ringing phone still rings, is answered and finishes with our act running: the arrow is Payback's while it
       rings; our goal comes back after; Payback's goal list is the same after the act
  P10  the wanted level is the controlled record's byte +0x5a (set it: the stars follow; shoot a car: it rises)

    SP=<harness folder> ROM=x.gba ELF=x.elf python3 tests/s2/probes_e.py      (from stuntfox/)
"""
import struct

import h
from h import *

ck = Check()
merged_state(e)
run(30)
GOAL_REACHED = 0x0806c22c
NG = 0x0201a7d8


def gl():
    return [(g[0], g[1], g[2], g[3], g[4], g[5]) for g in goals()]


def ours():
    return [g for g in goals() if 0x5000 <= g[0] < 0x5100]


def table():
    p = u32(0x03000d60)
    return e.read(p, 128 * 128 * 4) if 0x02000000 <= p < 0x08000000 else b''


def grid_ptr():
    return u32(0x03000d60)


def drop_phone():
    e.write8(NG, 1)
    e.write8(NG + 1, 0)


base = e.save_state()
base_goals = [g for g in gl() if not 0x5000 <= g[0] < 0x5100]

# ---- P4 ----
t0 = table()
ck(len(t0) == 65536, 'the cell table is readable', 'at 0x%08x' % grid_ptr())
drop_phone()
mb(1, 0)
run(10)
g = ours()
ck(len(g) == 1, 'P4: the engine pushed one goal', str(gl()))
gid = g[0][0]
x, y = g[0][2], g[0][3]
e.prof_on(bps=[GOAL_REACHED, S['ms_tick'] & ~1])         # (the second is the control: it runs every frame)
run(300)
tele_man(x, y)                          # (on the goal itself: where Payback would reach any goal it could)
fm_break()
run(300, ['A'])
_, bplog, _ = e.prof_off()
hits = [b for b in bplog if b[0] == 0]
ctl = [b for b in bplog if b[0] == 1]
ck(len(ctl) > 100, 'P4: the breakpoint log works (the control, ms_tick, was seen %d times)' % len(ctl))
ck(len(hits) == 0, 'P4: Payback\'s goal-reached routine (0x0806c22c) ran 0 times in 600 frames, 300 of them standing on the goal',
   '%d breakpoint hits' % len(hits))
now = ours()
ck(len(now) == 1, 'P4: our goal is still the one goal of ours (standing on it did not end it; the act moved it on: %x -> %x)' % (gid, now[0][0] if now else 0), str(gl()))
ck(table() == t0 and grid_ptr() == u32(0x03000d60), 'P4: the cell table is byte for byte what it was', '%d bytes compared' % len(t0))
cells = struct.unpack('<%dI' % (len(t0) // 4), t0)
cx, cz = int(x), int(y)
ck(cells[(cx << 7) + cz] >= 0x08000000, 'P4: the goal sits on a cell that is still in the ROM (no RAM copy)', '0x%08x' % cells[(cx << 7) + cz])
ck(now and abs(r32(0x020025f0) - int(now[0][2] * 2048)) < 8 and abs(r32(0x020025f4) - int(now[0][3] * 2048)) < 8,
   'P4: the arrow (0x020025f0) points at it', 'arrow %d,%d goal %d,%d' % (r32(0x020025f0), r32(0x020025f4), now[0][2] * 2048, now[0][3] * 2048))
mb(9)
run(10)
ck(not ours() and len(gl()) == 1, 'P4: dropped, the list is Payback\'s own', str(gl()))

# ---- P7 ----
e.load_state(base)
run(2)
mb(1, 0)
run(20)
ph = [g for g in goals() if g[1] == 1]
ck(len(ph) == 1 and not ours(), 'P7: a green phone rings: we push nothing and the arrow stays Payback\'s', str(gl()))
arrow = (r32(0x020025f0), r32(0x020025f4))
ck(abs(arrow[0] - int(ph[0][2] * 2048)) < 8 and abs(arrow[1] - int(ph[0][3] * 2048)) < 8, 'P7: the arrow is on the phone', str(arrow))
ck(mb(8, 13) == 1, 'P7: the engine knows a phone rings (cmd 8, 13)')
s_run = e.save_state()
answered = False
for (dx, dy), hd in zip(((0, 1.5), (1.5, 0), (-1.5, 0), (0, -1.5)), (2880, 4320, 1440, 0)):
    s0 = e.save_state()
    tele_man(ph[0][2] + dx, ph[0][3] + dy)
    e.write8(PL + 0x12, hd & 255)
    e.write8(PL + 0x13, hd >> 8)
    run(5)
    for _ in range(10):
        run(15, ['A'])
        if r16(0x02007134) != 0:
            answered = True
            break
    if answered:
        break
    e.load_state(s0)
run(20)
ck(answered, 'P7: the phone is answered while our act runs (Payback\'s mission %d starts)' % r16(0x02007134))
lag = 0
while (mb(7) & 255) != 5 and lag < 90:               # (it pauses when the phone mission's own goals are in the list: a few frames after it began)
    run(3)
    lag += 3
sv = mb(7)
ck((sv & 255) == 5, 'P7: our act waits (paused), %d frames after the mission began' % lag, hex(sv))
ck(not ours(), 'P7: and holds no goal', str(gl()))
# the phone mission ends the way Payback ends it: its goals leave, the current mission clears
n = r16(NG)
keep = [gl()[0]]
e.write8(NG, 1)
e.write8(NG + 1, 0)
e.write8(0x02007134, 0)
e.write8(0x02007135, 0)
run(30)
ck((mb(7) & 255) == 2, 'P7: the phone mission over, our act runs on', hex(mb(7)))
mb(4, 1)
run(900)
ck(mb(8, 2) == 1, 'P7: and finishes', 'ndone %d' % mb(8, 2))
ck(not ours(), 'P7: nothing of ours left in the goal list', str(gl()))

# ---- P10 ----
e.load_state(base)
run(2)
mb(6, 0)
run(6)
ck(mb(7) & 255 == 1, 'P10: with the act armed (its line up)')
w0 = e.read(PL + 0x5a, 1)[0]
ck(w0 == 0, 'P10: no wanted level at the start', str(w0))
e.write8(PL + 0x5a, 3)
run(6)
e.frame.save(os.path.join(START, 'build', 'p10_three_stars.png')) if os.path.isdir(os.path.join(START, 'build')) else None
print('   (stars with +0x5a = 3: see build/p10_three_stars.png)')
e.write8(PL + 0x5a, 0)
board_now()
n = r16(0x0300000c)
ents0 = [e.r32(0x03000c60 + 4 * i) & 0xffffffff for i in range(n + 1)]
cars = [p for p in ents0 if 0x08354af4 <= (e.r32(p + 0x1c) & 0xffffffff) < 0x08354ef0 and e.read(p + 0x10f, 1)[0] in (3, 4)]
rose = 0
for car in cars[:3]:
    for _ in range(14):
        v = struct.unpack('<15i', e.read(S['ship'], 60))
        sx, sz, f = v[0] >> 8, v[2] >> 8, v[12:15]
        cxx, czz = sx + f[0] * 1800 // 16384, sz + f[2] * 1800 // 16384
        e.write32(car + 4, cxx * 2)
        e.write32(car + 8, czz * 2)
        run(6, ['R'])
        run(6)
    rose = max(rose, e.read(PL + 0x5a, 1)[0])
ck(rose >= 1, 'P10: shooting cars raises the byte at +0x5a of the player record', 'it reached %d' % rose)
ck.done()
