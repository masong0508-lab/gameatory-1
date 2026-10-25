"""fps of the grown Killing Zone: 40 sample points spread over all of it, on foot, against Freedom City's 40 by the
same script (stage2.md 9.2: median >= 18, min >= 12, median at most 1 fps below Freedom's).

    SP=<harness folder> python3 tests/s2/fps_arena.py ROM ELF [points] [windows]      (run from the repo's stuntfox/ folder)

Points: the open flat cells of the grid Payback holds in RAM (street-level floor, nothing on it or above it, off the
border), picked farthest-first from one another, so each district gets its share. At each the man is put down, the
game runs 25 frames to draw and populate round him, and the frames Stunt Fox draws in the next 90 are counted
(key_calls, as fps3.py does). A grid whose savestate is not cached is reached through Payback's own rampage menu.
Prints one line per point and the summary; the exit status is 1 when a floor is missed."""
import json
import os
import struct
import subprocess
import sys

START = os.getcwd()
SP = os.environ['SP']
rom, elf = (os.path.join(START, a) for a in sys.argv[1:3])
NPOINTS = int(sys.argv[3]) if len(sys.argv) > 3 else 40
FRAMES = int(sys.argv[4]) if len(sys.argv) > 4 else 90
PLAN = os.path.join(START, 'content', 'arena', 'killzone.json')
sys.path[:0] = [SP + '/work', SP + '/v12/s1play5']
os.chdir(SP + '/work')
from retro import Emu                      # noqa: E402
import gridstate                           # noqa: E402

gridstate.ST = os.environ.get('GRID_ST', gridstate.ST)
S = {l.split()[2]: int(l.split()[0], 16) for l in subprocess.run(['llvm-nm', elf], capture_output=True, text=True).stdout.splitlines()
     if len(l.split()) == 3}
GRID_PTR = 0x03000d60              # Payback's pointer to its 128 x 128 table of column pointers (x * 128 + y)
MAN = 0x02009394
POS = (0x2008df8, 0x2009398, 0x2009478, 0x2009484)


def label(plan, x, y):
    """The plan's name for the district or road at (x, y)."""
    for n, d in plan['districts'].items():
        r = d['rect']
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return n
    for n, r in plan['roads'].items():
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return n
    px0, py0, px1, py1 = plan['pit']
    return 'PIT' if px0 <= x <= px1 and py0 <= y <= py1 else 'GROUND'


def open_cells(e):
    g = struct.unpack('<I', e.read(GRID_PTR, 4))[0]
    ptrs = struct.unpack('<%dI' % (128 * 128), e.read(g, 4 * 128 * 128))
    seen, out = {}, []
    for i, p in enumerate(ptrs):
        if p not in seen:
            c = e.read(p, 60)
            r0, r1, r2 = c[0:20], c[20:40], c[40:60]
            h0 = struct.unpack_from('<H', r0, 4)[0]
            seen[p] = (r0[8] == 1 and h0 == 0x100 and not r1[8] and not r2[8] and not r0[1] and (r0[11] & 0x70) != 0x40)
        x, y = divmod(i, 128)
        if seen[p] and 2 <= x <= 125 and 2 <= y <= 125:
            out.append((x, y))
    return out


def farthest(cells, n):
    """n cells picked one after another, each the farthest from those picked (the first nearest the middle)."""
    pts = [min(cells, key=lambda c: (c[0] - 64) ** 2 + (c[1] - 64) ** 2)]
    dist = {c: (c[0] - pts[0][0]) ** 2 + (c[1] - pts[0][1]) ** 2 for c in cells}
    while len(pts) < n:
        nxt = max(cells, key=lambda c: (dist[c], c))
        pts.append(nxt)
        for c in cells:
            d = (c[0] - nxt[0]) ** 2 + (c[1] - nxt[1]) ** 2
            if d < dist[c]:
                dist[c] = d
    return pts


def run(grid, plan):
    e = Emu('gba', rom)
    gridstate.grid_state(e, grid)
    e.run(1)
    cells = open_cells(e)
    pts = farthest(cells, NPOINTS)
    res = []
    for x, y in pts:
        for a in POS:
            e.write32(a, int((x + .5) * 2048))
            e.write32(a + 4, int((y + .5) * 2048))
        e.write32(MAN + 4, int((x + .5) * 2048))
        e.write32(MAN + 8, int((y + .5) * 2048))
        e.run(25)
        k0 = struct.unpack('<i', e.read(S['key_calls'], 4))[0]
        e.run(FRAMES)
        k1 = struct.unpack('<i', e.read(S['key_calls'], 4))[0]
        res.append(((x, y), label(plan, x, y) if grid == 3 else '', (k1 - k0) * 60 / FRAMES))
    return res


def summary(name, res):
    v = sorted(r[2] for r in res)
    med = (v[len(v) // 2] + v[(len(v) - 1) // 2]) / 2
    print('%-13s points %d  median %.2f  mean %.2f  min %.1f  max %.1f' % (name, len(v), med, sum(v) / len(v), v[0], v[-1]))
    return med, v[0]


plan = json.load(open(PLAN))
out = {}
for grid, name in ((3, 'Killing Zone'), (0, 'Freedom City')):
    res = run(grid, plan)
    for (x, y), lab, f in res:
        print('  g%d (%3d,%3d) %-12s %5.1f' % (grid, x, y, lab, f))
    out[grid] = summary(name, res)
(kmed, kmin), (fmed, _) = out[3], out[0]
ok = kmed >= 18 and kmin >= 12 and kmed >= fmed - 1
print('floors: median >= 18 %s, min >= 12 %s, within 1 of Freedom (%.2f) %s' % (
    'ok' if kmed >= 18 else 'MISSED', 'ok' if kmin >= 12 else 'MISSED', fmed, 'ok' if kmed >= fmed - 1 else 'MISSED'))
print('ALL OK' if ok else 'FLOORS MISSED')
sys.exit(0 if ok else 1)
