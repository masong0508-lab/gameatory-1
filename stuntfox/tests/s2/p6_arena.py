"""Probe P6 (stage2.md 1.2): the grown Killing Zone is all there. The man, a car and Payback's own traffic leave the old
arena's box (x 53-86, y 58-91) freely; the picture and the camera cover 128 x 128; rampage destinations are in the map.

    SP=<harness folder> ROM=x.gba ELF=x.elf [OUT=<shots folder>] python3 tests/s2/p6_arena.py            (from stuntfox/)

Prints one line per check and OK / FAIL at the end (exit status 1 on a FAIL)."""
import json
import struct

from arenah import *                                 # noqa: F401,F403

BOX = (53, 58, 86, 91)
inside = lambda x, y: BOX[0] <= x <= BOX[2] and BOX[1] <= y <= BOX[3]
rom = open(ROM, 'rb').read()
plan = json.load(open(os.path.join(START, 'content', 'arena', 'killzone.json')))
bad = []


def check(ok, text):
    print('%-4s %s' % ('ok' if ok else 'FAIL', text))
    if not ok:
        bad.append(text)


def open_cells():
    """The street-level floor cells of the grid Payback holds in RAM (nothing on them, no water)."""
    g = u32(0x03000d60)
    ptrs = struct.unpack('<%dI' % (128 * 128), e.read(g, 4 * 128 * 128))
    ok, out = {}, []
    for i, p in enumerate(ptrs):
        if p not in ok:
            c = e.read(p, 60)
            ok[p] = c[8] == 1 and struct.unpack_from('<H', c, 4)[0] == 0x100 and not c[28] and not c[48] and (c[11] & 0x70) != 0x40
        if ok[p] and 2 <= i // 128 <= 125 and 2 <= i % 128 <= 125:
            out.append((i // 128, i % 128))
    return out


# ---- 1. on foot: out of every gate, and to the four corners ----
start_grid(3)
base = e.save_state()
for g in plan['gates']:
    (x0, y0, x1, y1), (bx, by) = g['road'], g['block']
    out_dx = -1 if x1 < BOX[0] + 3 else 1 if x0 > BOX[2] - 3 else 0           # the way out: away from the Pit's middle
    out_dy = -1 if y1 < BOX[1] + 3 else 1 if y0 > BOX[3] - 3 else 0
    lane = ((x0 + x1) / 2 + 0.5, (y0 + y1) / 2 + 0.5)
    sx = lane[0] if out_dx == 0 else (BOX[0] + 3.5 if out_dx < 0 else BOX[2] - 3.5)
    sy = lane[1] if out_dy == 0 else (BOX[1] + 3.5 if out_dy < 0 else BOX[3] - 3.5)
    e.load_state(base)
    tele_man(sx, sy), set_heading(heading(out_dx, out_dy)), fm_break(), e.run(3)
    hp0 = r16(PL + 0x68)
    run(700, ['UP'])
    p = epos(PL)
    check(not inside(p[0], p[1]) and modename() == 'FOOT' and r16(PL + 0x68) >= hp0,
          'man walks out of %s: (%.1f, %.1f) -> (%.1f, %.1f), hp %d' % (g['name'], sx, sy, p[0], p[1], r16(PL + 0x68)))

e.load_state(base)
cells = open_cells()
corner = lambda cx, cy: min(cells, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
shots = []
for name, (cx, cy) in (('NW', (4, 4)), ('NE', (123, 4)), ('SW', (4, 123)), ('SE', (123, 123)), ('W', (4, 64)), ('E', (123, 64))):
    x, y = corner(cx, cy)
    tele_man(x + .5, y + .5), fm_break(), e.run(60)
    p = epos(PL)
    img = e.frame.copy()
    px = list(img.convert('L').tobytes())
    mean = sum(px) / len(px)
    var = sum((v - mean) ** 2 for v in px) / len(px)
    check(abs(p[0] - x - .5) < 1.5 and abs(p[1] - y - .5) < 1.5 and var > 200,
          'camera follows the man to the %s corner (%d, %d): at (%.1f, %.1f), picture variance %.0f' % (name, x, y, p[0], p[1], var))
    snap('p6_corner_' + name)

# ---- 2. a car: out of every gate, and along the whole of S3 ----
e.load_state(base)
check(bool(jack2()) and modename() == 'DRIVE', 'a car is taken at the first start')
for g in plan['gates']:
    (x0, y0, x1, y1) = g['road']
    cx, cy = (x0 + x1) / 2 + .5, (y0 + y1) / 2 + .5
    out_dx = -1 if x1 < BOX[0] + 3 else 1 if x0 > BOX[2] - 3 else 0
    out_dy = -1 if y1 < BOX[1] + 3 else 1 if y0 > BOX[3] - 3 else 0
    sx = cx if out_dx == 0 else (BOX[0] + 3.5 if out_dx < 0 else BOX[2] - 3.5)
    sy = cy if out_dy == 0 else (BOX[1] + 3.5 if out_dy < 0 else BOX[3] - 3.5)
    put_car(sx, sy, {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}[(out_dx, out_dy)])
    run(2)
    run(400, ['A'])
    c = car_cell()
    check(not inside(*c) and modename() == 'DRIVE', 'car drives out of %s: (%.1f, %.1f) -> (%.1f, %.1f)' % (g['name'], sx, sy, c[0], c[1]))
def leg(x0, y0, hd, n=40):
    put_car(x0, y0, hd)
    run(2)
    xs = []
    for k in range(n):
        run(60, ['A'])
        xs.append(car_cell()[0])
        if len(xs) > 6 and abs(xs[-1] - xs[-6]) < 1:        # (stopped: a car of Payback's ahead, or the end)
            break
    return xs


east, west = leg(6.5, 53.5, 0), leg(121.5, 54.5, 2)
check(max(east) > 78 and min(west) < 92 and max(east) > min(west) - 15,
      'car drives much of S3 (stopped only by traffic ahead): east leg x 6 -> %.0f, west leg x 122 -> %.0f, the old box is columns 53-86' % (max(east), min(west)))
# (the legs above stop for a car of Payback's in the way, so the far halves are driven from the middle as well)
east2, west2 = leg(90.5, 53.5, 0), leg(88.5, 54.5, 2)
check(max(east2) > 118 and min(west2) < 10,
      'car drives the far ends of S3: east x 90 -> %.0f (the border wall is at 125), west x 88 -> %.0f' % (max(east2), min(west2)))

# ---- 3. Payback's own traffic: seen and moving all over, and across the old box's edge ----
def watch(frames, label, step=20):
    first, last, seen = {}, {}, set()
    cross = set()
    for t in range(frames // step):
        run(step)
        for _, a, k, f, pos, hp in ents():
            if 0 <= k <= 16 and f == 3 and a != ctl():
                if a not in first:
                    first[a] = pos
                    last[a] = pos
                io, ln = inside(*last[a][:2]), inside(*pos[:2])
                if io != ln:
                    cross.add(a)
                last[a] = pos
                seen.add((int(pos[0]) // 16, int(pos[1]) // 16))
    moved = [a for a in first if math.hypot(last[a][0] - first[a][0], last[a][1] - first[a][1]) > 8]
    return first, moved, cross, seen


far = 0
allseen = set()
nmoved = 0
for name, (cx, cy) in (('R2a', (25.5, 40.5)), ('R5', (105.5, 80.5)), ('S5', (60.5, 113.5)), ('S1', (30.5, 3.5)), ('R6', (123.5, 70.5)), ('S2', (100.5, 25.5))):
    e.load_state(base)
    tele_man(cx, cy), fm_break(), e.run(5)
    first, moved, cross, seen = watch(900, name)
    outside = [a for a in first if not inside(*first[a][:2])]
    far += len(outside)
    nmoved += len(moved)
    allseen |= seen
    print('     traffic near %s (%.0f, %.0f): %d cars seen, %d outside the old box, %d moved more than 8 cells' % (name, cx, cy, len(first), len(outside), len(moved)))
check(far >= 8 and nmoved >= 3, 'traffic outside the old box: %d cars seen there, %d moving, over %d 16-cell areas' % (far, nmoved, len(allseen)))
e.load_state(base)
tele_man(65.5, 56.5), fm_break(), e.run(5)
first, moved, cross, seen = watch(1500, 'gate')
print('     traffic at the north gates: %d cars seen, %d moved, %d crossed the old box\'s edge' % (len(first), len(moved), len(cross)))
check(len(first) > 0, 'traffic appears round the gates (%d cars)' % len(first))

# ---- 4. rampage destinations: the first one is a phone of ours; all 22 phones are in the map, with a phone on them, and reachable ----
# (Payback's single-player rampage starts at the same place and names the same first phone whatever the timing or its rand's
# position, measured over 12 starts, so the other phones are checked where they stand: a phone object on the cell, a man can be
# put there and stays, and the whole table is open floor)
from gridstate import _build, _key, TROPHY, MAP_SEL      # noqa: E402
phones = [(rom[0x193940 + 4 * (22 * 3 + i)], rom[0x193940 + 4 * (22 * 3 + i) + 1]) for i in range(rom[0x193d08 + 3])]
s = bytearray(open(gridstate.RSETUP, 'rb').read())
s[16:28] = e.romdata[0xa0:0xac]
e.load_state(bytes(s)), e.run(2)
_key(e, 'B', after=40)
for i in range(6):
    e.write8(TROPHY + 2 * i, 3), e.write8(TROPHY + 2 * i + 1, 0)
_key(e, 'A', after=60), _key(e, 'UP'), _key(e, 'UP')
for i in range(3):
    _key(e, 'RIGHT', after=20)
_key(e, 'DOWN', after=20), _key(e, 'DOWN', after=20), _key(e, 'A', after=600)
for k in range(3):
    _key(e, 'A', after=60)
e.run(200)
g = [x for x in goals() if x[1] == 1]
first = (int(g[0][2]), int(g[0][3])) if grid() == 3 and g else None
check(first in phones, 'the rampage\'s first destination %s is one of the %d phones in the map' % (first, len(phones)))
G = u32(0x03000d60)
rampstate = e.save_state()
noobj, stuck = [], []
for (x, y) in phones:
    col = e.read(u32(G + 4 * (x * 128 + y)), 60)
    if not any(col[20 * k + 1] == 0x0e for k in range(3)):
        noobj.append((x, y))
    e.load_state(rampstate)
    tele_man(x + .5, y + .5), fm_break(), e.run(40)
    p = epos(PL)
    if abs(p[0] - x - .5) > 1.5 or abs(p[1] - y - .5) > 1.5 or modename() != 'FOOT':
        stuck.append((x, y))
check(len(phones) == 22 and not noobj and not stuck,
      'all %d phones in the table have a phone object on their cell (missing: %s) and a man stands on them (not: %s)' % (len(phones), noobj, stuck))

print('P6 FAIL: %s' % bad if bad else 'P6 OK')
sheet(OUT + '/p6_corners.png', [s for s in pp.shots if s[0].startswith('p6_corner')], cols=3)
sys.exit(1 if bad else 0)
