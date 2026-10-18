#!/usr/bin/env python3
"""The ragdoll solver (src/ragdoll.c) on the PC, on the worlds tools/mkworld.py builds: standard
throws (a car at full speed, a blast, a fall off a roof, into a wall, down a ramp), and a soak of
random throws all over a map. Reports bounces, the worst stretch of a stick, any point under a
floor or inside a building, steps to rest and the time a step takes; draws side views.

    python3 tools/ragcheck.py ROM [--grids 0,4] [--soak 400] [--out DIR] [--rigid]

--rigid runs the same throws with a rigid tumbling figure instead (the cheaper way it was
compared with). Nothing here goes into the ROM.
"""
import argparse
import ctypes
import math
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SF = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(SF, '..', 'payback-mod'))

# the sticks of src/ragdoll.c (point indices; 'hl'/'hr' the hips) and their lengths (units)
STICKS = [(0, 1, 83.3), (0, 2, 83.3), (1, 2, 68.0), (3, 1, 45.3), (3, 2, 45.3), (3, 0, 106.0),
          (1, 4, 36.6), (4, 5, 38.5), (2, 6, 36.6), (6, 7, 38.5), ('hl', 8, 48.1), (8, 9, 46.3),
          ('hr', 10, 48.1), (10, 11, 46.3)]
RADIUS = [14, 12, 12, 16, 7, 6, 7, 6, 8, 5, 8, 5]
TICKS = 3                                      # a game frame (about 20 a second)


def build(tmp):
    src = os.path.join(SF, 'src')
    import mkassets
    tables = os.path.join(tmp, 'tables.c')
    mkassets.main(tables)
    t = open(tables).read().replace('"../../src/gba.h"', '"gba.h"')
    open(tables, 'w').write(t)
    lib = os.path.join(tmp, 'librag.so')
    subprocess.check_call(['gcc', '-O2', '-shared', '-fPIC', '-fno-builtin', '-w', '-DRAG_HOST', '-I' + src] + os.environ.get('RAG_CFLAGS', '').split() +
                          [os.path.join(src, f) for f in ('fx.c', 'world.c', 'physics.c', 'ragdoll.c')] +
                          [tables, os.path.join(HERE, 'raghost.c'), '-o', lib])
    L = ctypes.CDLL(lib)
    L.rh_time.restype = ctypes.c_double
    L.rb_time.restype = ctypes.c_double
    return L


def world_file(rom_bytes, g, tmp):
    import mkworld
    from paybackmod.rom import PaybackRom
    import mksolo
    rom = PaybackRom(rom_bytes)
    mksolo.offer_every_map(rom.d)
    mksolo.add_phones(rom)
    data, _ = mkworld.build(rom_bytes, merge=True, level=g, rom=rom, limits=False)
    path = os.path.join(tmp, 'world%02d.bin' % g)
    open(path, 'wb').write(data)
    return path


class Sim:
    def __init__(self, L, rigid=False):
        self.L, self.rigid = L, rigid
        self.buf = (ctypes.c_int * 40)()

    def throw(self, at, yaw, vel, spin=(0, 0, 0)):
        f = self.L.rb_throw if self.rigid else self.L.rh_throw
        f(int(at[0]), int(at[1]), int(at[2]), int(yaw), *[int(v) for v in vel], *[int(s) for s in spin])

    def tick(self, n=TICKS):
        (self.L.rb_tick if self.rigid else self.L.rh_tick)(n)

    def get(self, k=0):
        st = self.L.rb_get(self.buf) if self.rigid else self.L.rh_get(k, self.buf)
        pts = [(self.buf[3 * i] / 8, self.buf[3 * i + 1] / 8, self.buf[3 * i + 2] / 8) for i in range(12)]
        return st, pts, self.buf[36]


def hips(p):
    l, r, pv = p[1], p[2], p[0]
    return ([pv[a] + (l[a] - r[a]) * 7 / 32 for a in range(3)], [pv[a] + (r[a] - l[a]) * 7 / 32 for a in range(3)])


def stretch(p):
    hl, hr = hips(p)
    worst = 0
    for a, b, l in STICKS:
        A = hl if a == 'hl' else hr if a == 'hr' else p[a]
        d = math.dist(A, p[b])
        worst = max(worst, abs(d - l) / l)
    return worst


def run(sim, L, at, yaw, vel, spin, frames=160):
    """one throw: the track and its measures"""
    sim.throw(at, yaw, vel, spin)
    track, worst, under, inside, rest, walls = [], 0, 0, 0, None, 0
    prev = None
    for f in range(frames):
        sim.tick()
        st, p, b = sim.get()
        track.append(p)
        worst = max(worst, stretch(p))
        for i, q in enumerate(p):
            s = L.rh_surface(int(q[0]), int(q[1]) + 40, int(q[2]))
            if q[1] < s - 16:                      # (under the floor it is over, more than a little: not floating)
                under = max(under, s - q[1])
            d = L.rh_solid(int(q[0]), int(q[1]), int(q[2]))
            if d > 6:
                inside = max(inside, d)
            if prev and L.rh_wallx(int(prev[i][0]), int(prev[i][1]) - RADIUS[i], int(prev[i][2]), int(q[0]), int(q[1]) - RADIUS[i], int(q[2])):
                walls += 1
        prev = p
        if st == 2 and rest is None:
            rest = f
    return dict(track=track, stretch=worst, under=under, inside=inside, rest=rest, bounces=b, walls=walls)


def hops(track, L):
    """the pelvis' rises after it first comes down: (count of rises over 12 units, their heights)"""
    h = [p[0][1] - L.rh_ground(int(p[0][0]), int(p[0][2])) for p in track]
    out, i, landed = [], 1, False
    while i < len(h) - 1:
        if h[i] < h[i - 1] and h[i] <= h[i + 1]:
            landed = True
            lo = h[i]
            j = i + 1
            while j < len(h) - 1 and h[j + 1] >= h[j]:
                j += 1
            if h[j] - lo > 12:
                out.append(round(h[j] - lo))
            i = j
        i += 1
    return out


def flat_spot(L, rng, need=4, tries=4000):
    """a street cell with `need` flat street cells on from it along +x"""
    for _ in range(tries):
        cx, cz = rng.randrange(6, 120), rng.randrange(6, 120)
        g = L.rh_ground(cx * 1024 + 512, cz * 1024 + 512)
        if all(L.rh_ground((cx + k) * 1024 + 512, cz * 1024 + 512) == g and
               L.rh_surface((cx + k) * 1024 + 512, g + 400, cz * 1024 + 512) == g and
               L.rh_ground((cx + k) * 1024 + 512, cz * 1024 + 512 + d) == g
               for k in range(need) for d in (-700, 700)) and g < 400:
            return (cx * 1024 + 512, g, cz * 1024 + 512)
    return None


def ledge_spot(L, rng, tries=20000):
    """a roof cell with a street cell 300+ units lower next to it along +x"""
    for _ in range(tries):
        cx, cz = rng.randrange(6, 120), rng.randrange(6, 120)
        a = L.rh_ground(cx * 1024 + 512, cz * 1024 + 512)
        b = L.rh_ground((cx + 1) * 1024 + 512, cz * 1024 + 512)
        if a - b > 300 and L.rh_ground((cx + 2) * 1024 + 512, cz * 1024 + 512) == b:
            return (cx * 1024 + 900, a, cz * 1024 + 512)
    return None


def side_view(res, path, title):
    from PIL import Image, ImageDraw
    tr = res['track']
    xs = [q[0] for p in tr for q in p] + [q[2] for p in tr for q in p]
    W, H = 900, 260
    x0 = tr[0][0][0]
    ax = 0 if abs(tr[-1][0][0] - x0) >= abs(tr[-1][0][2] - tr[0][0][2]) else 2
    span = max(1, max(abs(p[0][ax] - tr[0][0][ax]) for p in tr))
    ys = [q[1] for p in tr for q in p]
    ylo, yhi = min(ys) - 20, max(ys) + 20
    sc = min((W - 40) / (span + 300), (H - 30) / (yhi - ylo + 1))
    im = Image.new('RGB', (W, H), (250, 250, 250))
    d = ImageDraw.Draw(im)
    d.text((6, 4), title, fill=(0, 0, 0))

    def P(q):
        return (20 + (q[ax] - tr[0][0][ax]) * sc * (1 if tr[-1][0][ax] >= tr[0][0][ax] else -1) + 150 * sc,
                H - 10 - (q[1] - ylo) * sc)
    for k, p in enumerate(tr):
        if k % 2:
            continue
        hl, hr = hips(p)
        c = (int(200 * k / len(tr)), 60, 255 - int(200 * k / len(tr)))
        for a, b, _ in STICKS:
            A = hl if a == 'hl' else hr if a == 'hr' else p[a]
            d.line([P(A), P(p[b])], fill=c)
    im.save(path)


def gif(sim_tracks, path, L):
    """a 3/4 view of the throw, a frame a game frame (50 ms)"""
    from PIL import Image, ImageDraw
    frames = []
    tr = sim_tracks
    cx = sum(q[0] for q in tr[-1]) / 12
    cz = sum(q[2] for q in tr[-1]) / 12
    ox, oz = (tr[0][0][0] + cx) / 2, (tr[0][0][2] + cz) / 2
    for p in tr:
        im = Image.new('RGB', (240, 160), (190, 210, 235))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 100, 240, 160], fill=(120, 120, 120))

        def P(q):
            x, y, z = q[0] - ox, q[1] - tr[0][0][1], q[2] - oz
            return (120 + (x * 0.8 - z * 0.6) * 0.09, 120 - y * 0.12 + (x * 0.6 + z * 0.8) * -0.03)
        hl, hr = hips(p)
        for a, b, _ in STICKS:
            A = hl if a == 'hl' else hr if a == 'hr' else p[a]
            d.line([P(A), P(p[b])], fill=(200, 60, 20) if b in (8, 9, 10, 11) else (240, 200, 40), width=2)
        x, y = P(p[3])
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(250, 220, 180))
        frames.append(im)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=50, loop=0)


def standard(L, sim, rng, wacky, out, tag):
    L.rh_wacky(wacky)
    res = {}
    spot = flat_spot(L, rng, need=8)
    v = 84 * 256                                   # a car at full speed (units / 256 a tick)
    throws = {
        'car': (spot, 16384, (v, v * 3 // 10, 0), (0, 0, 700)),
        'car_slow': (spot, 16384, (v // 3, v // 10, 0), (0, 0, 300)),
        'blast': (spot, 0, (v // 4, v * 4 // 10, v // 8), (300, 0, 200)),
        'punch': (spot, 0, (0, 1500, 2600), (180, 0, 0)),
    }
    ledge = ledge_spot(L, rng)
    if ledge:
        throws['ledge'] = (ledge, 16384, (900, 300, 0), (0, 0, 100))
    wall = None
    for _ in range(3000):                          # a street cell with a building next along +x
        cx, cz = rng.randrange(6, 120), rng.randrange(6, 120)
        a = L.rh_ground(cx * 1024 + 512, cz * 1024 + 512)
        if a < 200 and L.rh_ground((cx + 1) * 1024 + 100, cz * 1024 + 512) > a + 600:
            wall = (cx * 1024 + 300, a, cz * 1024 + 512)
            break
    if wall:
        throws['wall'] = (wall, 16384, (v * 2 // 3, v // 6, 0), (0, 0, 300))
    for name, (at, yaw, vel, spin) in throws.items():
        r = run(sim, L, at, yaw, vel, spin)
        r['hops'] = hops(r['track'], L)
        res[name] = r
        print('%s %-9s bounces %d hops %-18s stretch %4.1f%% under %3d inside %3d railing %d rest at frame %s' % (
            tag, name, r['bounces'], r['hops'], 100 * r['stretch'], r['under'], r['inside'], r['walls'], r['rest']))
        if out:
            side_view(r, os.path.join(out, '%s_%s.png' % (tag, name)), '%s %s' % (tag, name))
            gif(r['track'], os.path.join(out, '%s_%s.gif' % (tag, name)), L)
    return res


def soak(L, sim, rng, n, wacky, tag):
    L.rh_wacky(wacky)
    worst = dict(stretch=0, under=0, inside=0, lost=0, never=0, walls=0)
    for k in range(n):
        at = None
        while at is None:
            cx, cz = rng.uniform(4, 124), rng.uniform(4, 124)
            g = L.rh_surface(int(cx * 1024), 4000, int(cz * 1024))
            if L.rh_inside(int(cx * 1024), g + 120, int(cz * 1024)) == 0:
                at = (cx * 1024, g, cz * 1024)
        sp = rng.choice((20, 50, 84, 120))
        a = rng.uniform(0, 2 * math.pi)
        vel = (math.sin(a) * sp * 256, rng.uniform(0.1, 0.6) * sp * 256, math.cos(a) * sp * 256)
        spin = [rng.randint(-300, 300) for _ in range(3)]
        r = run(sim, L, at, rng.randrange(65536), vel, spin, frames=220)
        for key in ('stretch', 'under', 'inside'):
            worst[key] = max(worst[key], r[key])
        worst['walls'] += r['walls']
        worst['never'] += r['rest'] is None
    print('%s soak %d: worst stretch %.1f%%, under a floor %d, inside a building %d, through a railing %d, not at rest after 11 s: %d' % (
        tag, n, 100 * worst['stretch'], worst['under'], worst['inside'], worst['walls'], worst['never']))
    return worst


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('--grids', default='0')
    ap.add_argument('--soak', type=int, default=0)
    ap.add_argument('--out')
    ap.add_argument('--rigid', action='store_true')
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix='ragcheck')
    L = build(tmp)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    rom = open(a.rom, 'rb').read()
    for g in [int(x) for x in a.grids.split(',')]:
        assert L.rh_load(world_file(rom, g, tmp).encode()) > 0
        sim = Sim(L, a.rigid)
        for wacky in (0, 1):
            tag = 'g%d%s%s' % (g, '_rigid' if a.rigid else '', '_wacky' if wacky else '')
            rng = random.Random(a.seed + g)
            standard(L, sim, rng, wacky, a.out, tag)
            if a.soak:
                soak(L, sim, random.Random(a.seed * 7 + g), a.soak, wacky, tag)
        # time a step: all slots in the air (the ragdoll), or the one rigid figure
        L.rh_wacky(0)
        rng = random.Random(5)
        spot = flat_spot(L, rng)
        if a.rigid:
            sim.throw(spot, 0, (84 * 256, 6000, 0), (0, 0, -200))
            ns = L.rb_time(TICKS, 20000)
            print('g%d rigid: %.0f ns a frame for one figure' % (g, ns))
        else:
            L.rh_throw(int(spot[0]), int(spot[1]), int(spot[2]), 0, 84 * 256, 6000, 0, 0, 0, -200)
            for k in range(4):
                L.rh_throw2(int(spot[0]), int(spot[1]), int(spot[2]), 0, 84 * 256, 6000, 0, 0, 0, -200)
            ns = L.rh_time(TICKS, 20000)
            print('g%d ragdoll: %.0f ns a frame for 5 bodies, %.0f each' % (g, ns, ns / 5))


if __name__ == '__main__':
    main()
