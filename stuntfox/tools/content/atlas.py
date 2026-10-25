"""The Payback atlas: what the content tools know about each map, read from the grid that ships (after the arena and
the phones are in) with mkworld's own classification, so the atlas and the 3D world cannot disagree.

Cells are indexed i = x * 128 + y (x, y = Payback's cell; y is our z). Heights are world units, the street at 0 on every
map (mkworld's h_units). Per map:
  kind/lo/hi/shape/mat   mkworld.merged's cells (road, kerb, ground, ramp, building); water has shape SHAPE_WATER
  deck / deck2           (bottom, top) of what spans over a floor (bridges, walkways, the upper floors)
  foot / car             the floors a man (a car) can get to by Payback's rules, {cell: [height, ...]}, and the part of
                         them reached from the map's start points (main_foot / main_car)
  lane                   column byte 3 (1 drives -y, 4 +y, 2 +x, 8 -x, 0x20 kerb)
  roofs / decks / towers flat tops (clusters), with a pad cell the Arwing's footprint fits on
  phones, crates, starts, lane graph, the 3D clearance test (blocked)
Nothing here copies a byte of Payback's into the repository: it is computed at build time from the ROM.
"""
import collections
import hashlib
import os
import pickle
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (os.path.join(ROOT, 'tools'), os.path.join(ROOT, '..', 'payback-mod')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import mkworld  # noqa: E402
import mksolo  # noqa: E402

N = 128
CELL = 1024
VERSION = 4                                   # (bump it with any change that alters what an Atlas holds: it keys the cache)


def _tool_hash():
    """The classification code's own bytes: the cache key holds them, so an edit of mkworld, mksolo or this file cannot leave a stale atlas behind."""
    h = hashlib.sha1()
    for m in (mkworld, mksolo, sys.modules[__name__]):
        try:
            with open(m.__file__, 'rb') as f:
                h.update(f.read())
        except OSError:
            h.update(b'?')
    return h.digest()[:8]
OBJ_PHONES = (14, 19)                         # (props.c: a phone, ringing or not)
OBJ_CRATE = 6
FLAT = 64                                     # a flat top: within this many units
SAMPLES = 16                                  # (rim samples of a ring's disc; an inner ring of half as many at half the radius)
WATER_CLEAR = 96                              # a ring's lowest point keeps this far over the water
LANE_STEP = ((0, -1), (1, 0), (0, 1), (-1, 0))     # edge (-y, +x, +y, -x) as mkworld's EDGE_STEP
LANE_BIT = (1, 2, 4, 8)                       # the lane bit that drives along each edge


def cx_of(i):
    return i >> 7


def cz_of(i):
    return i & 127


def idx(cx, cz):
    return cx * N + cz


def inside(cx, cz):
    return 0 <= cx < N and 0 <= cz < N


class Roof:
    """A flat top: cells at one height (within FLAT), 4-connected. pad: a cell whose 3 x 3 neighbourhood is all of it."""
    def __init__(self, h, cells, kind):
        self.h, self.cells, self.kind = h, sorted(cells), kind
        self.area = len(cells)
        xs = [c >> 7 for c in cells]
        zs = [c & 127 for c in cells]
        self.rect = (min(xs), min(zs), max(xs), max(zs))
        self.pad = None

    def __repr__(self):
        return 'Roof(%s h=%d area=%d rect=%s pad=%s)' % (self.kind, self.h, self.area, self.rect, self.pad)


class Atlas:
    def __init__(self, rom, level, cache=None):
        self.level = level
        grid = rom.painted.get(level) or rom.grid(level)
        self.grid = list(grid)
        key = hashlib.sha1(b''.join(rom.column(g) for g in sorted(set(grid))) + bytes(
            b for g in grid for b in struct.pack('<H', g)) + struct.pack('<HH', VERSION, level)).hexdigest()[:16]
        path = os.path.join(cache, 'map%02d_%s.pkl' % (level, key)) if cache else None
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                self.__dict__.update(pickle.load(f))
            return
        self._build(rom, grid)
        if path:
            os.makedirs(cache, exist_ok=True)
            for f in os.listdir(cache):
                if f.startswith('map%02d_' % level):
                    os.remove(os.path.join(cache, f))
            keep = {k: v for k, v in self.__dict__.items()}
            with open(path, 'wb') as f:
                pickle.dump(keep, f, 2)

    # ---- the build ----
    def _build(self, rom, grid):
        was = mkworld.STREET
        mkworld.STREET = mkworld.street_level(rom, grid)
        self.street = mkworld.STREET
        try:
            cells, decks, walls, tiles, objs, decks2, swim = mkworld.merged(rom, grid)
        finally:
            mkworld.STREET = was
        self.kind = [c[0] for c in cells]
        self.lo = [c[1] for c in cells]
        self.hi = [c[2] for c in cells]
        self.shape = [c[3] for c in cells]
        self.deck = {i: (d[0], d[1], d[4], d[5]) for i, d in decks.items()}        # bottom, top, top's low end, shape
        self.deck2 = {i: (d[0], d[1], d[4], d[5]) for i, d in decks2.items()}
        raw = [rom.column(grid[i]) for i in range(N * N)]
        self.lane = [c[3] for c in raw]
        self.cols = [mkworld.pb_records(c) for c in raw]
        self.water = [s == mkworld.SHAPE_WATER for s in self.shape]
        # Payback's own reach: every street and pavement seeds it, so it says where the floors are; the part reached
        # from the map's start points says where the player can go
        self._reach(rom)
        self._objects(raw, rom)
        self._tops()
        del self.cols

    def _reach(self, rom):
        pb_reach = mkworld.pb_reach
        foot = pb_reach(self.cols, self.lane)
        car = pb_reach(self.cols, self.lane, True)
        h_units = lambda h: (h - self.street) * 8
        self.foot = {i: sorted((h_units(h) for k, h in ks.items() if self.cols[i][k][4] != 0x40)) for i, ks in foot.items()}
        self.car = {i: sorted((h_units(h) for k, h in ks.items() if self.cols[i][k][4] != 0x40)) for i, ks in car.items()}
        self.foot = {i: v for i, v in self.foot.items() if v}
        self.car = {i: v for i, v in self.car.items() if v}
        self.starts = [(x, y, k) for x, y, k in mksolo.starts(rom, self.level)]
        # the area reached from the start points: (cell, record) nodes by Payback's edge rule
        seeds = []
        for x, y, k in self.starts:
            i = idx(x, y)
            if i in foot and k in foot[i]:
                seeds.append((i, k, foot[i][k]))
            elif i in foot:
                kk = min(foot[i], key=lambda q: abs(foot[i][q] - 0x100) if q is not None else 0)
                seeds.append((i, kk, foot[i][kk]))
        self.main_foot = self._flood(seeds, False, foot)
        # cars: from the lane cells inside the main foot area (traffic drives where the player walks to)
        cs = []
        for i, ks in car.items():
            if self.lane[i] & 15 and i in self.main_foot:
                for k, h in ks.items():
                    cs.append((i, k, h))
        self.main_car = self._flood(cs, True, car)
        if not self.main_foot:
            self.main_foot = {i: v for i, v in self.foot.items()}
        if not self.main_car:
            self.main_car = {i: v for i, v in self.car.items()}
        self._raw_foot, self._raw_car = foot, car

    def _flood(self, seeds, is_car, allowed):
        """{cell: [heights in units]} of the floors reached from seeds (cell, record, height) by Payback's rules."""
        cols = self.cols
        seen = {}
        todo = []
        for i, k, h in seeds:
            if k not in seen.setdefault(i, {}):
                seen[i][k] = h
                todo.append((i, k, h))
        pbf, pbb = mkworld.pb_floor, mkworld.pb_blocked
        while todo:
            i, k, h = todo.pop()
            if cols[i][k][4] == 0x40:
                continue
            x, y = divmod(i, N)
            for e, (dx, dy) in enumerate(mkworld.EDGE_STEP):
                if not inside(x + dx, y + dy):
                    continue
                j = (x + dx) * N + y + dy
                he = pbf(cols[i], *mkworld.PB_EXIT[e], h)[1]
                if pbb(cols[j], e, he, is_car):
                    continue
                hin = pbf(cols[j], *mkworld.PB_ENTRY[e], he)[1]
                kj, hj = pbf(cols[j], 1024, 1024, hin)
                if kj is not None and kj not in seen.get(j, {}):
                    seen.setdefault(j, {})[kj] = hj
                    todo.append((j, kj, hj))
        return {i: sorted((h - self.street) * 8 for k, h in ks.items() if cols[i][k][4] != 0x40) for i, ks in seen.items()
                if any(cols[i][k][4] != 0x40 for k in ks)}

    def _objects(self, raw, rom):
        self.phones, self.crates = [], []
        for i in range(N * N):
            for k in range(3):
                if raw[i][20 * k + 8]:
                    t = raw[i][20 * k + 1]
                    if t in OBJ_PHONES:
                        self.phones.append((cx_of(i), cz_of(i)))
                    elif t == OBJ_CRATE and k in self._reach_k(i):
                        self.crates.append((cx_of(i), cz_of(i)))
        self.phones = sorted(set(self.phones))

    def _reach_k(self, i):
        return (self._raw_foot.get(i) or {}).keys() | (self._raw_car.get(i) or {}).keys()

    def _tops(self):
        """Roofs, decks and towers: flat tops with a pad the Arwing's footprint fits on."""
        n = N * N
        self.roofs = self._clusters(lambda i: self.kind[i] == 'building', lambda i: self.hi[i], 'roof')
        self.decks = self._clusters(lambda i: i in self.deck and self.deck[i][3] == 1 and not self.water[i],
                                    lambda i: self.deck[i][1], 'deck')
        # ranked: roof.1 is the largest, tower.1 the tallest
        self.roofs.sort(key=lambda r: (-r.area, r.rect))
        self.decks.sort(key=lambda r: (-r.area, r.rect))
        self.towers = sorted([r for r in self.roofs if r.h >= 5000 and r.pad], key=lambda r: (-r.h, -r.area, r.rect))

    def _clusters(self, member, height, kind):
        n = N * N
        seen = bytearray(n)
        out = []
        for s in range(n):
            if seen[s] or not member(s):
                continue
            h0 = height(s)
            comp, todo = [], [s]
            seen[s] = 1
            while todo:
                i = todo.pop()
                comp.append(i)
                x, y = divmod(i, N)
                for dx, dy in LANE_STEP:
                    if inside(x + dx, y + dy):
                        j = (x + dx) * N + y + dy
                        if not seen[j] and member(j) and abs(height(j) - h0) <= FLAT:
                            seen[j] = 1
                            todo.append(j)
            r = Roof(h0, comp, kind)
            cs = set(comp)
            # a pad: a cell whose 3 x 3 is all this top, the one nearest the middle of it
            cx = sum(c >> 7 for c in comp) / len(comp)
            cy = sum(c & 127 for c in comp) / len(comp)
            best = None
            for c in comp:
                x, y = divmod(c, N)
                if all(idx(x + a, y + b) in cs for a in (-1, 0, 1) for b in (-1, 0, 1) if inside(x + a, y + b)) and \
                        all(inside(x + a, y + b) for a in (-1, 1) for b in (-1, 1)):
                    d = (x - cx) ** 2 + (y - cy) ** 2
                    if best is None or d < best[0]:
                        best = (d, c)
            r.pad = divmod(best[1], N) if best else None
            out.append(r)
        return out


    @classmethod
    def cached(cls, cache, level):
        """The newest atlas of the level in a cache folder (host tests: no ROM needed), or None."""
        import glob
        fs = sorted(glob.glob(os.path.join(cache, 'map%02d_*.pkl' % level)), key=os.path.getmtime)
        if not fs:
            return None
        a = cls.__new__(cls)
        with open(fs[-1], 'rb') as f:
            a.__dict__.update(pickle.load(f))
        return a

    # ---- a synthetic map for the host tests (no ROM): flat ground, then put_* and finish() ----
    @classmethod
    def blank(cls, level=0):
        a = cls.__new__(cls)
        n = N * N
        a.level, a.street, a.grid = level, 256, [0] * n
        a.kind = ['ground'] * n
        a.lo = [0] * n
        a.hi = [0] * n
        a.shape = [1] * n
        a.mat = [0] * n
        a.deck, a.deck2 = {}, {}
        a.lane = [0] * n
        a.water = [False] * n
        a.phones, a.crates = [], []
        a.starts = [(4, 4, 0)]
        a.roofs, a.decks, a.towers = [], [], []
        a.foot, a.car, a.main_foot, a.main_car = {}, {}, {}, {}
        return a

    def put_building(self, x0, y0, x1, y1, h):
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                i = idx(x, y)
                self.kind[i], self.lo[i], self.hi[i], self.shape[i] = 'building', h, h, 1

    def put_road(self, x0, y0, x1, y1, bits=0):
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                i = idx(x, y)
                self.kind[i], self.lane[i] = 'road', bits or (2 if x1 - x0 >= y1 - y0 else 1)

    def put_water(self, x0, y0, x1, y1, h=0):
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                i = idx(x, y)
                self.kind[i], self.lo[i], self.hi[i], self.shape[i], self.water[i] = 'ground', h - 4096, h, mkworld.SHAPE_WATER, True

    def put_deck(self, x0, y0, x1, y1, bottom, top):
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                self.deck[idx(x, y)] = (bottom, top, top, 1)

    def put_ramp(self, x0, y0, x1, y1, lo, hi, shape=3):
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                i = idx(x, y)
                self.kind[i], self.lo[i], self.hi[i], self.shape[i] = 'ramp', lo, hi, shape

    def finish(self):
        """Walkable floors (everything that is not a building or water, or a deck's top), then the tops."""
        for i in range(N * N):
            if self.kind[i] != 'building' and not self.water[i]:
                self.foot[i] = [self.hi[i]]
                self.car[i] = [self.hi[i]]
        self.main_foot, self.main_car = dict(self.foot), dict(self.car)
        self._tops()
        return self

    # ---- queries ----
    def surf(self, fx, fz):
        """The ground surface at (fx, fz) in cells (floats): the top of the building, the slope's height, the street."""
        cx, cz = int(fx), int(fz)
        if not inside(cx, cz):
            return 0
        i = idx(cx, cz)
        k, lo, hi, sh = self.kind[i], self.lo[i], self.hi[i], self.shape[i]
        if k == 'building' or sh == 1 or sh == mkworld.SHAPE_WATER:
            return hi
        u, v = fx - cx, fz - cz
        rise = {2: v, 3: u, 4: 1 - v, 5: 1 - u}.get(sh, 0)
        return lo + (hi - lo) * rise

    def blocked(self, x, z, y, margin=0):
        """Is the point (x, z, y), in world units, inside something solid (or within margin of it)?"""
        cx, cz = int(x) >> 10, int(z) >> 10
        if not inside(cx, cz):
            return True
        i = idx(cx, cz)
        if not self.water[i] and y < self.surf(x / CELL, z / CELL) + margin:        # (water: the Arwing flies over it; a ring may dip in)
            return True
        for d in (self.deck.get(i), self.deck2.get(i)):
            if d and d[0] - margin <= y <= d[1] + margin:
                return True
        return False

    def column_top(self, cx, cz):
        """The highest solid in the cell (a building, a deck, the street)."""
        i = idx(cx, cz)
        t = max(self.hi[i], self.lo[i])
        for d in (self.deck.get(i), self.deck2.get(i)):
            if d:
                t = max(t, d[1])
        return t

    def floors(self, cx, cz, mode):
        """The floor heights a man ('foot') or a car ('car') can stand at in the cell, in the player's reachable part."""
        src = self.main_foot if mode == 'foot' else self.main_car
        return src.get(idx(cx, cz), [])

    def lowest_floor(self, cx, cz):
        for src in (self.main_foot, self.main_car, self.foot, self.car):
            v = src.get(idx(cx, cz))
            if v:
                return v[0]
        i = idx(cx, cz)
        return self.hi[i] if self.kind[i] != 'building' else self.hi[i]

    def clear_disc(self, x, z, y, r, axis, margin=192):
        """A ring of radius r (units) at (x, z, y) facing axis ('x': the plane x = const, 'y': z = const, 'h': y = const):
        its centre, an inner ring of half the radius, SAMPLES on the rim and the column through the centre (a ship's way in and out,
        384 units each side along the axis) clear of solids by margin, and the lowest of them over the water by WATER_CLEAR.
        Returns the first blocked sample or None."""
        import math
        pts = [(0, 0, 0)]
        for rr, n in ((r * 0.5, SAMPLES // 2), (r, SAMPLES)):
            for k in range(n):
                a = 2 * math.pi * (k + 0.5 * (rr != r)) / n
                pts.append((rr * math.cos(a), rr * math.sin(a), 0))
        pts += [(0, 0, -384), (0, 0, 384)]
        for u, v, w in pts:
            if axis == 'x':
                p = (x + w, z + u, y + v)
            elif axis == 'y':
                p = (x + u, z + w, y + v)
            else:
                p = (x + u, z + v, y + w)
            if self.blocked(p[0], p[1], p[2], margin if not w else margin // 2):
                return p
            cx, cz = int(p[0]) >> 10, int(p[1]) >> 10
            if inside(cx, cz) and self.water[idx(cx, cz)] and p[2] < self.hi[idx(cx, cz)] + WATER_CLEAR:
                return p
        return None

    def segment_clear(self, a, b, margin=256, step=256):
        """The straight line from a to b (x, z, y in units) clear of solids by margin; the first blocked point or None."""
        n = max(1, int(max(abs(b[0] - a[0]), abs(b[1] - a[1]), abs(b[2] - a[2])) // step))
        for k in range(n + 1):
            t = k / n
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)
            if self.blocked(p[0], p[1], p[2], margin):
                return p
        return None

    def walkable(self, cx, cz, mode, h=None, tol=300):
        fl = self.floors(cx, cz, mode)
        if h is None:
            return bool(fl)
        return any(abs(f - h) <= tol for f in fl)

    def lane_graph(self):
        """{cell: [neighbour cells]} for the lane cells (traffic drives the way the lane bits say) that are in the car area."""
        g = {}
        for i in self.main_car:
            b = self.lane[i] & 15
            if not b:
                continue
            x, y = divmod(i, N)
            out = []
            for e, (dx, dy) in enumerate(LANE_STEP):
                if b & LANE_BIT[e] and inside(x + dx, y + dy):
                    j = (x + dx) * N + y + dy
                    if self.lane[j] & 15 and j in self.main_car:
                        out.append(j)
            g[i] = out
        return g

    def lane_cells(self):
        return {i for i in self.main_car if self.lane[i] & 15}

    def junctions(self):
        return sorted(i for i in self.lane_cells() if bin(self.lane[i] & 15).count('1') >= 2)

    def summary(self):
        c = collections.Counter(self.kind)
        return dict(level=self.level, kinds=dict(c), roofs=len(self.roofs), towers=len(self.towers), decks=len(self.decks),
                    foot=len(self.main_foot), car=len(self.main_car), phones=len(self.phones), crates=len(self.crates),
                    starts=len(self.starts), lanes=len(self.lane_cells()))


def load_all(rom, cache=None, levels=range(11)):
    return {m: Atlas(rom, m, cache) for m in levels}
