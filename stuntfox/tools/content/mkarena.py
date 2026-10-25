"""The Killing Zone (Payback grid 3) grown from its 34 x 34 cell arena to the whole 128 x 128 grid.

build(rom, orig) is what tools/s2build.py's pre_world calls (rom: the PaybackRom being built, orig: the
player's Payback bytes). It paints grid 3 from content/arena/killzone.json out of Payback's own columns
(rom.column_index(): roads, kerbs and junctions are copied from Payback's own streets, the rest are made
as Payback's records are), checks it (AV1-AV9: any failure stops the build), writes the map's start points,
phones and minimap into the ROM, and returns {3: [loops]} for mkworld.build.

The Pit (the old arena, x53-86 y58-91) is kept as it is: Payback's objects and parked cars still stand
where it expects them. Eight gates are cut through its wall ring, each a T junction on one of its inner
roads. Nothing here is copied from the ROM into the repository: columns are read from it at build time.
"""
import collections
import json
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, '..')
ROOT = os.path.join(TOOLS, '..')
for _p in (HERE, TOOLS, os.path.join(ROOT, '..', 'payback-mod')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import mkworld   # noqa: E402
import mksolo    # noqa: E402
import minimap   # noqa: E402
import arenacheck   # noqa: E402

PLAN = os.path.join(ROOT, 'content', 'arena', 'killzone.json')
N = 128
LEVEL = 3
STREET = 0x100
CLIMB = 0x20                 # the most a floor may step up between cells (mksolo.CLIMB)
GAP_CLEAR = 2048             # the room under a deck (units): AV4
PHONE_OBJ = 0x0e
WATER_TILE = 0x311

# a lane's traffic direction bits (byte 3 of its column) and the step each leads
DIR_STEP = {1: (0, -1), 2: (1, 0), 4: (0, 1), 8: (-1, 0)}
OPPOSITE = {1: 4, 4: 1, 2: 8, 8: 2}
ARMS = {'N': (0, -1), 'E': (1, 0), 'S': (0, 1), 'W': (-1, 0)}


def raw(units):
    """Payback's height step (0x100 = the street) of a height in world units (8 to a step)."""
    assert units % 8 == 0, units
    return STREET + units // 8


# ---- columns: three 20-byte records, as paybackmod/blocks.py has them ----
def rec(h0=STREET, h1=None, shape=0, flags=0, tile=0, sides=(0, 0, 0, 0), b1=0, b3=0, water=False):
    h1 = h0 if h1 is None else h1
    attr = 0xc3 if water else 0x90 | (tile >> 8 & 3)
    return struct.pack('<BBBBHHBBBB4H', 0, b1, 0, b3, h0, h1, shape, flags, tile & 0xff, attr, *sides)


def gap(thick=STREET):
    """A record with nothing in it, thick high (the room under what is stacked over it)."""
    return struct.pack('<BBBBHHBBBB4H', 0, 0, 0, 0, thick, thick, 0, 0, 0, 0, 0, 0, 0, 0)


def col_ground(tile, b3=0, obj=0):
    return rec(STREET, STREET, 1, 0x60, tile, b3=b3, b1=obj) + gap() + gap()


def col_building(top, roof, side):
    """A solid block from the street up to raw height top: a gap as thick as the street, then the solid,
    as Payback's own walls are (its side words: 0x9000 | tile stops people, 0x8000 | tile does not)."""
    return gap() + rec(top - STREET, top - STREET, 1, 0x6f, roof, sides=((0x9000 | side),) * 4) + gap()


def col_table(top, tile, side):
    """A raised flat floor people and cars can stand on, solid down to the street (as stuntpark's)."""
    return rec(top, top, 1, 0x60, tile, sides=((0x1000 | side),) * 4) + gap() + gap()


def col_slope(lo, hi, shape, tile, side=None):
    """A drivable slope in the floor record, rising from lo to hi (raw heights) toward shape's direction
    (2 +y, 3 +x, 4 -y, 5 -x); its sides stop people and cars where it stands over the street."""
    sides = (0x1000 | (side or tile),) * 4 if max(lo, hi) > STREET else (0, 0, 0, 0)
    return rec(lo, hi, shape, 0x60, tile, sides=sides) + gap() + gap()


def col_water(depth):
    h = STREET - depth // 8
    return rec(h, h, 1, 0x20, WATER_TILE, water=True) + gap() + gap()


def with_deck(col60, bottom, top, tile, side):
    """col60's floor with a solid slab over it, raw heights bottom to top (room to pass under)."""
    r0 = col60[:20]
    h0 = struct.unpack_from('<H', r0, 4)[0]
    assert bottom > h0 and top > bottom
    return r0 + gap(bottom - h0) + rec(top - bottom, top - bottom, 1, 0x60, tile, sides=((0x1000 | side),) * 4)


def with_object(col60, obj, k=0):
    b = bytearray(col60)
    b[20 * k + 1] = obj
    b[20 * k + 2] = 0
    return bytes(b)


def lanes_of(col60):
    return col60[3]


def top_of(col60):
    """The highest solid top of a column, raw."""
    return max([max(r[1], r[2]) for r in mkworld.pb_records(col60) if r[3]] or [STREET])


STAMP_MAPS = (0, 2, 1, 5, 4, 3, 6, 7, 8, 9, 10)     # the order Vocab looks for junctions in


class Vocab:
    """What Payback's streets are made of, found in its grids: the 4-wide straight roads and the
    junctions (X, the four T and the four L) as the 4 x 4 blocks they stand in, the most used of each."""

    def __init__(self, rom):
        self.rom = rom
        self.ix = rom.column_index()
        self.straight = {}               # 'x': the four columns across a road along x (by y); 'y': along y (by x)
        self.stamps = {}                 # frozenset of arms -> (where found, 16 columns, index i * 4 + j)
        self.lane = [[self.rom.column(c)[3] & 0x2f for c in rom.orig_grid(lv)] for lv in range(11)]
        self._find_straights()
        self._find_stamps()

    def _plain(self, c):
        s = self.ix.sig(c)
        return s[0][6] == 1 and s[0][4] == STREET and s[0][7] == 0x60 and not s[1][6] and not s[2][6] and not s[0][1]

    def _find_straights(self):
        pat = {'y': (0x20, 1, 4, 0x20), 'x': (0x20, 2, 8, 0x20)}      # along y: lanes -y and +y across x
        g, lane = self.rom.orig_grid(0), self.lane[0]
        for axis, p in pat.items():
            cnt = collections.Counter()
            for x in range(N - 3):
                for y in range(N - 3):
                    idx = [(x + i) * N + y if axis == 'y' else x * N + y + i for i in range(4)]
                    if all(lane[idx[i]] == p[i] and self._plain(g[idx[i]]) for i in range(4)):
                        cnt[tuple(g[i] for i in idx)] += 1
            assert cnt, 'no plain straight road along ' + axis
            self.straight[axis] = min(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0]

    def _find_stamps(self):
        want = {frozenset(a) for a in ('NESW', 'ESW', 'NSW', 'NEW', 'NES', 'ES', 'SW', 'NW', 'NE')}
        pat = {'N': (0x20, 1, 4, 0x20), 'S': (0x20, 1, 4, 0x20), 'W': (0x20, 2, 8, 0x20), 'E': (0x20, 2, 8, 0x20)}
        found = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
        first = {}
        for lv in range(11):
            g, lane = self.rom.orig_grid(lv), self.lane[lv]

            def arm(d, x0, y0):
                if d == 'N':
                    cells = [(x0 + i, y0 - 1) for i in range(4)]
                elif d == 'S':
                    cells = [(x0 + i, y0 + 4) for i in range(4)]
                elif d == 'W':
                    cells = [(x0 - 1, y0 + j) for j in range(4)]
                else:
                    cells = [(x0 + 4, y0 + j) for j in range(4)]
                v = tuple(lane[x * N + y] for x, y in cells)
                return True if v == pat[d] else False if not any(v) else None
            for x0 in range(1, N - 4):
                for y0 in range(1, N - 4):
                    if not (lane[x0 * N + y0] and lane[(x0 + 3) * N + y0 + 3] and lane[(x0 + 3) * N + y0]
                            and lane[x0 * N + y0 + 3]):
                        continue
                    if not all(lane[(x0 + i) * N + y0 + j] for i in range(4) for j in range(4)):
                        continue
                    a = [arm(d, x0, y0) for d in 'NESW']
                    if None in a or sum(a) < 2:
                        continue
                    arms = frozenset(d for d, v in zip('NESW', a) if v)
                    if arms not in want:
                        continue
                    ids = tuple(g[(x0 + i) * N + y0 + j] for i in range(4) for j in range(4))
                    found[arms][lv][ids] += 1
                    first.setdefault((arms, ids), (lv, x0, y0))
        # (Freedom City's streets where it has the piece, then Corona's, the cities most alike)
        for arms, by_level in found.items():
            lv = min(by_level, key=lambda l: STAMP_MAPS.index(l))
            cnt = by_level[lv]
            ids = min(cnt, key=lambda k: (-cnt[k], first[(arms, k)], k))
            self.stamps[arms] = (first[(arms, ids)], ids)
        missing = sorted(''.join(sorted(a)) for a in want if a not in self.stamps)
        assert not missing, "no junction block of Payback's for arms: %s" % missing

    def stamp(self, arms):
        return self.stamps[frozenset(arms)][1]


class Arena:
    def __init__(self, rom, plan):
        self.rom, self.plan = rom, plan
        self.voc = Vocab(rom)
        self.ix = rom.column_index()
        self.seed = plan['seed']
        self.t = plan['tiles']
        self.cols = [None] * (N * N)         # the 60 bytes of each cell's column
        self.kind = ['?'] * (N * N)          # what the cell is for (the minimap, the validators)
        self.towers = []                     # (x0, y0, x1, y1, top raw) of every tower (AV7)
        self.lips = set()                    # slope cells that end at a drop on purpose (kickers, lips: AV3)
        self.loops = []
        self.notes = []
        self.pit = tuple(plan['pit'])
        self._orig3 = [rom.column(c) for c in rom.orig_grid(LEVEL)]

    # -- cells --
    def rng(self, name):
        return random.Random('%d:%s' % (self.seed, name))

    def inb(self, x, y):
        return 0 <= x < N and 0 <= y < N

    def put(self, x, y, col, kind=None):
        assert self.inb(x, y), (x, y)
        self.cols[x * N + y] = col
        if kind:
            self.kind[x * N + y] = kind

    def at(self, x, y):
        return self.cols[x * N + y]

    def in_pit(self, x, y):
        x0, y0, x1, y1 = self.pit
        return x0 <= x <= x1 and y0 <= y <= y1

    def fill(self, r, col, kind):
        for x in range(r[0], r[2] + 1):
            for y in range(r[1], r[3] + 1):
                self.put(x, y, col, kind)

    def tile(self, name):
        return self.t[name]

    # -- stage 1: border, base, the Pit --
    def paint_base(self):
        ground = col_ground(self.tile('plaza'))
        for i in range(N * N):
            self.cols[i] = ground
            self.kind[i] = 'ground'
        b = self.plan['border']
        w, top = b['width'], raw(b['top'])
        wall = col_building(top, self.tile('wall'), self.tile('wall'))
        for x in range(N):
            for y in range(N):
                if x < w or y < w or x >= N - w or y >= N - w:
                    self.put(x, y, wall, 'wall')
        x0, y0, x1, y1 = self.pit
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                col = self._orig3[x * N + y]
                k = 'pit'
                self.put(x, y, col, k)
        self.notes.append('the Pit %s kept: %d cells' % (self.pit, (x1 - x0 + 1) * (y1 - y0 + 1)))

    # -- stage 2: roads --
    def road_rects(self):
        out = {}
        for name, r in self.plan['roads'].items():
            out[name] = ('N' if r[2] - r[0] == 3 and r[3] - r[1] != 3 else 'E' if r[3] - r[1] == 3 and r[2] - r[0] != 3
                         else None, tuple(r))
            assert out[name][0], 'a road is 4 wide and not square: ' + name
        for g in self.plan['gates']:
            r = g['road']
            axis = 'N' if r[2] - r[0] == 3 else 'E' if r[3] - r[1] == 3 else None
            assert axis, 'gate road %s: 4 wide' % g['name']
            out[g['name']] = (axis, tuple(r))
        return out

    def paint_roads(self):
        v = self.voc
        rects = self.road_rects()
        ns, ew = {}, {}
        for name, (axis, r) in rects.items():
            for x in range(r[0], r[2] + 1):
                for y in range(r[1], r[3] + 1):
                    if axis == 'N':
                        ns[x, y] = (name, x - r[0])
                    else:
                        ew[x, y] = (name, y - r[1])
        # junction blocks: where a road along x and one along y meet (4 x 4, tested)
        both = sorted(set(ns) & set(ew))
        blocks, seen = [], set()
        for c in both:
            if c in seen:
                continue
            comp, todo = [], [c]
            seen.add(c)
            while todo:
                p = todo.pop()
                comp.append(p)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    q = (p[0] + dx, p[1] + dy)
                    if q in both and q not in seen:
                        seen.add(q)
                        todo.append(q)
            xs, ys = [p[0] for p in comp], [p[1] for p in comp]
            assert len(comp) == 16 and max(xs) - min(xs) == 3 and max(ys) - min(ys) == 3, \
                'roads cross in %d cells at %s: not one 4 x 4 block' % (len(comp), comp[0])
            blocks.append((min(xs), min(ys)))
        for (x, y), (name, off) in ns.items():
            if (x, y) not in ew:
                self.put(x, y, self.rom.column(v.straight['y'][off]), 'road')
        for (x, y), (name, off) in ew.items():
            if (x, y) not in ns:
                self.put(x, y, self.rom.column(v.straight['x'][off]), 'road')
        for x0, y0 in blocks:
            arms = ''
            for d, (dx, dy) in ARMS.items():
                pts = {'N': [(x0 + 1, y0 - 1), (x0 + 2, y0 - 1)], 'S': [(x0 + 1, y0 + 4), (x0 + 2, y0 + 4)],
                       'W': [(x0 - 1, y0 + 1), (x0 - 1, y0 + 2)], 'E': [(x0 + 4, y0 + 1), (x0 + 4, y0 + 2)]}[d]
                tab = ns if d in 'NS' else ew
                if all(p in tab for p in pts):
                    arms += d
            self.stamp_block(x0, y0, arms)
        # the Pit's own roads meet the gates in T blocks (their arms are the Pit's lanes)
        for gate in self.plan['gates']:
            self.stamp_block(gate['block'][0], gate['block'][1], gate['arms'])
        self.notes.append('roads: %d junction blocks and %d gates' % (len(blocks), len(self.plan['gates'])))

    def stamp_block(self, x0, y0, arms):
        ids = self.voc.stamp(arms)
        for i in range(4):
            for j in range(4):
                self.put(x0 + i, y0 + j, self.rom.column(ids[i * 4 + j]), 'junction')

    # -- stage 3: districts (kits) --
    MARGIN = 2                       # pavement kept clear round a built district (phones, walkers)

    def slots(self, lo, hi, size, gap, anchor=None, least=3):
        """[(a, b)] along one axis inside lo..hi: slots of size with gap cells between, in step with
        anchor; the end ones are cut to fit and dropped when under least wide."""
        a0 = lo if anchor is None else anchor
        k = -((a0 - lo) // (size + gap))
        out = []
        s = a0 + k * (size + gap)
        while s <= hi:
            a, b = max(s, lo), min(s + size - 1, hi)
            if b - a + 1 >= least:
                out.append((a, b))
            s += size + gap
        return out

    def packed(self, lo, hi, sizes, gap, rng, least=3):
        """Slots of random sizes (lo..hi inclusive of both, from sizes) with gap between."""
        out, a = [], lo
        while a <= hi:
            b = min(a + rng.randint(*sizes) - 1, hi)
            if b - a + 1 >= least:
                out.append((a, b))
            a = b + 1 + gap
        return out

    def inner(self, r, m=None):
        m = self.MARGIN if m is None else m
        return (r[0] + m, r[1] + m, r[2] - m, r[3] - m)

    def sector_boxes(self, r):
        """How many boxes (mkworld's greedy rectangles of equal top and colour, 4 cells at most)
        each 16 x 16 sector touching r has, and how many tall towers: the density governor's numbers."""
        used, boxes = set(), collections.Counter()
        key = {}
        for x in range(max(0, r[0] - 1), min(N, r[2] + 2)):
            for y in range(max(0, r[1] - 1), min(N, r[3] + 2)):
                rs = [q for q in mkworld.pb_records(self.cols[x * N + y]) if q[3]]
                q = max(rs, key=lambda q: max(q[1], q[2]), default=None)
                if q and max(q[1], q[2]) > STREET and q[3] == 1 and q[4] != 0x40:
                    key[x, y] = (q[1], q[6])      # (a block: its top and roof)
        for (x, y), k in sorted(key.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            if (x, y) in used:
                continue
            w = 1
            while w < 4 and key.get((x + w, y)) == k and (x + w, y) not in used:
                w += 1
            h = 1
            while h < 4 and all(key.get((x + j, y + h)) == k and (x + j, y + h) not in used for j in range(w)):
                h += 1
            used.update((x + j, y + m) for j in range(w) for m in range(h))
            boxes[x // 16, y // 16] += 1
        tall = collections.Counter()
        for x0, y0, x1, y1, top in self.towers:
            if top >= raw(6144) and not (x1 < r[0] or x0 > r[2] or y1 < r[1] or y0 > r[3]):
                tall[(x0 + x1) // 32, (y0 + y1) // 32] += 1
        return boxes, tall

    def governed(self, name, d, paint):
        """Paint a district with paint(rng, attempt); a seed that crowds a sector beyond the governor
        (70 boxes, 6 tall towers) is dropped for the next, 8 tries (stage2.md 6.2)."""
        r = d['rect']
        snapshot = {(x, y): (self.cols[x * N + y], self.kind[x * N + y]) for x in range(r[0], r[2] + 1)
                    for y in range(r[1], r[3] + 1)}
        mark = len(self.towers)
        worst = None
        for attempt in range(8):
            paint(self.rng('%s:%d' % (name, attempt)), attempt)
            boxes, tall = self.sector_boxes(r)
            worst = (max(boxes.values() or [0]), max(tall.values() or [0]))
            if worst[0] <= 70 and worst[1] <= 6:
                self.notes.append('%s: seed %d, %d boxes and %d tall towers at most in a sector'
                                  % ((name, attempt) + worst))
                return
            for (x, y), (c, k) in snapshot.items():
                self.cols[x * N + y], self.kind[x * N + y] = c, k
            del self.towers[mark:]
        raise AssertionError('AV7: %s crowds a sector in all 8 seeds (boxes %d, tall towers %d)' % ((name,) + worst))

    def tile_of(self, d, key, rng):
        v = self.t[d[key]] if key in d else self.t[key]
        return rng.choice(v) if isinstance(v, list) else v

    def kit_lots(self, name, d):
        """Low-rise blocks: lots of 3 to 5 cells with one-cell alleys, over the pavement margin."""
        def paint(rng, attempt):
            x0, y0, x1, y1 = self.inner(d['rect'])
            for ya, yb in self.packed(y0, y1, d['lot'], d['alley'], rng):
                for xa, xb in self.packed(x0, x1, d['lot'], d['alley'], rng):
                    top = raw(rng.choice(d['heights']))
                    col = col_building(top, rng.choice(self.t['roofs']), self.tile_of(d, 'windows', rng))
                    self.fill((xa, ya, xb, yb), col, 'bld')
        self.governed(name, d, paint)

    def tiers(self, r, steps, rng, windows, roofs):
        """A tower in steps: steps is [(inset, top raw)] from the base up; each is the footprint cut
        in by inset cells, drawn bottom to top (the higher overwrites)."""
        side, roof = rng.choice(windows), rng.choice(roofs)
        for inset, top in steps:
            a = (r[0] + inset, r[1] + inset, r[2] - inset, r[3] - inset)
            if a[2] < a[0] or a[3] < a[1]:
                continue
            self.fill(a, col_building(top, roof, side), 'tower')
        self.towers.append((r[0], r[1], r[2], r[3], steps[-1][1]))

    def kit_towers(self, name, d):
        """Towers on a podium of base height, a core to a height of tops; sizes follow the slots."""
        specials = d.get('special', [])
        def paint(rng, attempt):
            x0, y0, x1, y1 = self.inner(d['rect'])
            xs = self.slots(x0, x1, d['tower'], d['alley'], least=4)
            ys = self.slots(y0, y1, d['tower'], d['alley'], least=4)
            base = raw(d['base'])
            for ya, yb in ys:
                for xa, xb in xs:
                    r = (xa, ya, xb, yb)
                    if any(not (xb < s['rect'][0] - 1 or xa > s['rect'][2] + 1 or yb < s['rect'][1] - 1
                                or ya > s['rect'][3] + 1) for s in specials):
                        continue
                    top = raw(rng.choice(d['tops']))
                    steps = [(0, base), (1, top)] if min(xb - xa, yb - ya) >= 4 else [(0, top)]
                    self.tiers(r, steps, rng, self.t['windows_sky'], self.t['roofs'])
            for s in specials:       # the landmark: three steps, the spire at its top
                r = tuple(s['rect'])
                self.tiers(r, [(0, base), (1, raw(s['top'] - 2048)), (2, raw(s['top']))], rng,
                           self.t['windows_sky'], self.t['roofs'])
        self.governed(name, d, paint)

    def kit_field(self, name, d):
        """Fox Field: grass, the runway (asphalt with a dashed centre line), hangars and the control tower."""
        r = d['rect']
        self.fill(r, col_ground(self.t['grass']), 'ground')
        rw = d['runway']
        self.fill(rw, col_ground(self.t['asphalt']), 'ground')
        for x in range(rw[0] + 1, rw[2] - 1, 4):
            self.fill((x, rw[1] + 1, x + 1, rw[1] + 2), col_ground(self.t['centre']), 'ground')
        rng = self.rng(name)
        for h in d['hangars']:
            self.fill(h, col_building(raw(d['hangar_top']), rng.choice(self.t['roofs']), rng.choice(self.t['hangar'])),
                      'bld')
        self.fill(d['tower'], col_building(raw(d['tower_top']), self.t['roofs'][0], rng.choice(self.t['windows_sky'])),
                  'tower')
        self.towers.append(tuple(d['tower']) + (raw(d['tower_top']),))

    def kit_apron(self, name, d):
        self.fill(d['rect'], col_ground(self.t['plaza']), 'ground')
        self.fill(d['drift'], col_ground(self.t['asphalt']), 'ground')

    def kit_park(self, name, d):
        self.fill(d['rect'], col_ground(self.t['asphalt']), 'ground')

    def kit_canyon(self, name, d):
        """Two blocks of cliff either side of the trench, cut by one-cell slots; each stretch its own height."""
        x0, y0, x1, y1 = d['rect']
        rng = self.rng(name)
        cuts = sorted(d['slots'])
        edges = [y0] + [c for s in cuts for c in (s, s + 1)] + [y1 + 1]
        stretches = [(edges[i], edges[i + 1] - 1) for i in range(0, len(edges), 2)]
        # (the last stretch is halved so that there are as many as there are heights)
        while len(stretches) < len(d['tops']):
            a, b = stretches.pop()
            m = (a + b) // 2
            stretches += [(a, m), (m + 1, b)]
        for (a, b), top in zip(stretches, d['tops']):
            self.fill((x0, a, x1, b), col_building(raw(top), rng.choice(self.t['roofs']), self.t['wall']), 'cliff')
        for s in cuts:
            self.fill((x0, s, x1, s), col_ground(self.t['plaza']), 'ground')

    def kit_speedway(self, name, d):
        self.fill(d['rect'], col_ground(self.t['plaza']), 'ground')
        self.fill(d['infield'], col_ground(self.t['grass']), 'ground')

    def kit_docks(self, name, d):
        """Crates in stacks with aisles between them, and the gantry cranes on legs along the north edge."""
        x0, y0, x1, y1 = d['rect']
        rng = self.rng(name)
        self.fill(d['rect'], col_ground(self.t['plaza']), 'ground')
        cx0, cy0, cx1, cy1 = d['cranes']
        top = raw(d['crane_top'])
        for legs in ((cx0, cy0, cx0 + 1, cy1), (cx1 - 1, cy0, cx1, cy1)):
            self.fill(legs, col_building(top, self.t['roofs'][0], self.t['windows_dock'][0]), 'tower')
        beam = self.at(cx0 + 2, cy0)
        self.fill((cx0 + 2, cy0, cx1 - 2, cy1), with_deck(beam, top - 64, top, self.t['deck'], self.t['deck']), 'deck')
        for ya, yb in self.packed(cy1 + 3, y1 - 1, (2, 3), 2, rng, least=2):
            for xa, xb in self.packed(x0 + 1, x1 - 1, (2, 3), 2, rng, least=2):
                h = raw(rng.choice((1536, 2048, 2560)))
                self.fill((xa, ya, xb, yb), col_building(h, self.t['crate'], self.t['crate']), 'crate')

    def kit_beach(self, name, d):
        self.fill(d['rect'], col_ground(self.t['sand']), 'ground')

    def kit_harbour(self, name, d):
        self.fill(d['rect'], col_water(self.plan['water']['depth']), 'water')

    # -- stage 4: features --
    @staticmethod
    def steps(total, n):
        """n+1 heights from 0 to total (raw) for a run of n slope cells: as even as they can be while every cell
        either reaches a man's knee (64: then a wall on its sides stops him) or lifts him by under 24 at its
        side (so that nothing needs one): the bend near the foot of a kicker. Even if no profile does both."""
        for tenth in range(10, 41):
            b = [round(total * (k / n) ** (tenth / 10)) for k in range(n + 1)]
            if all(b[k] <= b[k + 1] for k in range(n)) and all(
                    b[k + 1] >= mkworld.PB_KNEE or b[k] + b[k + 1] <= 2 * arenacheck.MID for k in range(n)):
                return b
        return [round(total * k / n) for k in range(n + 1)]

    def ramp(self, x, y, shape, lo, hi, tile, kind='ramp'):
        """One slope cell rising from lo to hi (raw, over 0) toward shape's direction."""
        self.put(x, y, col_slope(STREET + lo, STREET + hi, shape, tile), kind)

    def run(self, x, y, shape, total, n, tile, width=1, kind='ramp'):
        """n slope cells of width in a row from (x, y) toward shape's direction (2 +y, 3 +x, 4 -y, 5 -x) rising
        by total (raw) in all; the last cell is the lip. Returns the cells' last coordinate."""
        b = self.steps(total, n)
        dx, dy = {2: (0, 1), 3: (1, 0), 4: (0, -1), 5: (-1, 0)}[shape]
        px, py = (1, 0) if dx == 0 else (0, 1)
        for k in range(n):
            lo, hi = b[k], b[k + 1]
            for w in range(width):
                self.ramp(x + dx * k + px * w, y + dy * k + py * w, shape, lo, hi, tile, kind)
        return x + dx * (n - 1), y + dy * (n - 1)

    def block(self, r, top, tile, side=None, kind='table'):
        """A raised flat floor, solid to the street, over the rect r (top raw over 0)."""
        self.fill(r, col_table(STREET + top, tile, side or tile), kind)

    def paint_features(self):
        for name, f in self.plan['features'].items():
            getattr(self, 'feat_' + f['kit'])(name, f)

    def feat_skybridge(self, name, f):
        """A deck at f.top over the cells of its rect (road below it) with a landing one cell past each end."""
        x0, y0, x1, y1 = f['rect']
        top, bot = raw(f['top']), raw(f['top'] - f['thick'])
        if f['axis'] == 'x':
            cells = [(x, y) for x in range(x0 - 1, x1 + 2) for y in range(y0, y1 + 1)]
        else:
            cells = [(x, y) for x in range(x0, x1 + 1) for y in range(y0 - 1, y1 + 2)]
        for x, y in cells:
            c = self.at(x, y)
            if top_of(c) >= top or self.kind[x * N + y] in ('pit', 'wall'):
                continue
            if self.kind[x * N + y] in ('road', 'junction'):
                self.put(x, y, with_deck(c, bot, top, self.t['deck'], self.t['deck']), 'deck')
            else:
                self.put(x, y, col_building(top, self.t['deck'], self.t['windows_sky'][0]), 'tower')

    def feat_loops(self, name, f):
        """mkworld loops on the alley: (x, z) of each entry in units, direction +x, radius, width. A loop wants 14 x 5
        open flat cells round it (mkworld.pick_loop): the entry 6.5 cells in, the drift toward -z."""
        for x in f['xs']:
            self.loops.append((int((x + 0.5) * mkworld.CELL), int(f['entry_y'] * mkworld.CELL), 1, f['radius'], f['width']))

    def feat_kickers(self, name, f):
        """Kickers side by side along the row: each 3 wide and f.length long, rising toward +y to its top."""
        for i, top in enumerate(f['tops']):
            x = f['x0'] + f['step'] * i
            self.run(x, f['rect'][1], 2, top // 8, f['length'], self.t['kicker'], 3)

    def feat_halfpipe(self, name, f):
        """Banks of three cells each side of one flat row, rising to f.top toward the outside."""
        x0, y0, x1, y1 = f['rect']
        top = f['top'] // 8
        for x in range(x0, x1 + 1):
            self.run(x, y0 + 2, 4, top, 3, self.t['ramp'])           # the north bank (high at y0)
            self.run(x, y1 - 2, 2, top, 3, self.t['ramp'])           # the south bank
            self.put(x, y0 + 3, col_ground(self.t['asphalt']), 'park')
        # (the north bank's run goes toward -y from y0 + 2: its cells are y0 + 2, y0 + 1, y0)

    def feat_table(self, name, f):
        """A table at f.top with a ramp of f.ramp cells up to each end."""
        x0, y0, x1, y1 = f['rect']
        top, n = f['top'] // 8, f['ramp']
        for y in range(y0, y1 + 1):
            self.run(x0, y, 3, top, n, self.t['ramp'])
            self.run(x1, y, 5, top, n, self.t['ramp'])
        self.block((x0 + n, y0, x1 - n, y1), top, self.t['deck'])

    def feat_roofhop(self, name, f):
        """Platforms of rising height f.len cells long with f.gap cells of nothing between; each ends in a
        small kicker toward the next, and the first has its own ramp up from the street."""
        x0, y0, x1, y1 = f['rect']
        ya, yb = y0 + 3, y0 + 6
        tops = [t // 8 for t in f['tops']]
        n = f['len']
        self.run(x0, ya, 3, tops[0], 3, self.t['ramp'], 4)
        x = x0 + 3
        for i, t in enumerate(tops):
            self.block((x, ya, x + n - 2, yb), t, self.t['deck'])
            for y in range(ya, yb + 1):
                self.ramp(x + n - 1, y, 3, t, t + 48, self.t['kicker'])
            x += n + f['gap']

    def feat_megaramp(self, name, f):
        """The climb (9 cells to the lip), a canal of water, then the landing ramp falling to the street."""
        x0, y0, x1, y1 = f['rect']
        w = x1 - x0 + 1
        lip_y, lip = f['lip_y'], f['lip'] // 8
        n = lip_y - f['climb_y'] + 1
        cy0, cy1 = f['canal']
        for x in range(x0, x1 + 1):
            self.run(x, f['climb_y'], 2, lip, n, self.t['ramp'])
            for y in range(cy0, cy1 + 1):
                self.put(x, y, col_water(self.plan['water']['depth']), 'water')
            self.run(x, y1, 4, f['landing_top'] // 8, y1 - cy1, self.t['ramp'])

    def feat_needle(self, name, f):
        x0, y0, x1, y1 = f['rect']
        self.tiers(tuple(f['rect']), [(0, raw(f['top']))], self.rng(name), self.t['windows_sky'], self.t['roofs'])

    def feat_overpass(self, name, f):
        """A causeway across the infield: ramps up at both ends, a solid top between, hollow (a deck over the
        cross road) where a road runs under it."""
        x0, y0, x1, y1 = f['rect']
        top, n = (f['under'] + f['slab']) // 8, f['ramp']
        for y in range(y0, y1 + 1):
            self.run(x0, y, 3, top, n, self.t['ramp'])
            self.run(x1, y, 5, top, n, self.t['ramp'])
        for x in range(x0 + n, x1 - n + 1):
            for y in range(y0, y1 + 1):
                c = self.at(x, y)
                if self.kind[x * N + y] == 'road':
                    self.put(x, y, with_deck(c, raw(f['under']), raw(f['under'] + f['slab']), self.t['deck'], self.t['deck']), 'deck')
                else:
                    self.put(x, y, col_table(STREET + top, self.t['deck'], self.t['deck']), 'table')

    def feat_pierjump(self, name, f):
        x0, y0, x1, y1 = f['rect']
        for y in range(y0, y1 + 1):
            self.run(x0, y, 3, f['top'] // 8, x1 - x0 + 1, self.t['ramp'])

    def feat_deck(self, name, f):
        self.block(f['rect'], f['top'] // 8, self.t['deck'])

    def feat_pier(self, name, f):
        """A pier out from the beach, a ramp up from the sand at its root."""
        x0, y0, x1, y1 = f['rect']
        top = f['top'] // 8
        for x in range(x0, x1 + 1):
            self.ramp(x, y0, 2, 0, top, self.t['ramp'])
        self.block((x0, y0 + 1, x1, y1), top, self.t['deck'])

    def feat_tower(self, name, f):
        r = tuple(f['rect'])
        top = raw(f['top'])
        self.tiers(r, [(0, raw(4096)), (1, top)], self.rng(name), self.t['windows_sky'], self.t['roofs'])

    def paint_districts(self):
        for name, d in self.plan['districts'].items():
            getattr(self, 'kit_' + d['kit'])(name, d)

    # -- stage 5: what Payback's collision needs of the raised floors --
    def finish_sides(self):
        """The side words of every raised or sloped floor (record 0): a wall on each edge where a neighbour's floor
        is lower (arenacheck.needs_wall), none elsewhere. Payback stops people only by these, and only where the
        floor at the knee is this one: where a floor is too low there for a wall to work, the plain ground beside
        it gets a post instead. The solid blocks' sides (those of the Pit's wall ring too) are made walls on every
        face that meets open ground. The Pit's other cells keep theirs."""
        edge = arenacheck.floor_edge
        walls = posts = 0
        for i in range(N * N):
            if self.kind[i] == 'pit':
                continue
            col = self.cols[i]
            recs = mkworld.pb_records(col)
            r0 = recs[0]
            if not r0[3] or r0[4] in (0, 0x40) or (r0[3] == 1 and r0[1] <= STREET):
                continue
            x, y = divmod(i, N)
            sides = []
            for e, (dx, dy) in enumerate(ARM_STEP):
                wall = False
                if self.inb(x + dx, y + dy):
                    j = (x + dx) * N + y + dy
                    n0 = mkworld.pb_records(self.cols[j])[0]
                    if n0[3] and n0[4]:
                        ha, hb = edge(r0, e), edge(n0, e ^ 2)
                        wall = arenacheck.needs_wall(ha, hb)
                        if wall:
                            walls += 1
                            if not (max(r0[1], r0[2]) >= max(hb) + mkworld.PB_KNEE):
                                # (the knee passes over this floor: nothing stops him here but a post beside it)
                                if self.kind[j] == 'ground' and not self.cols[j][3]:
                                    self.put(x + dx, y + dy, col_building(raw(2048), self.t['wall'], self.t['wall']), 'post')
                                    posts += 1
                                elif self.kind[j] != 'water':      # (a swimmer's way out is swim_table's)
                                    self.notes.append('a lift at (%d, %d) edge %d that nothing stops' % (x, y, e))
                sides.append((0x1000 | r0[6]) if wall else 0)
            self.cols[i] = col[:12] + struct.pack('<4H', *sides) + col[20:]
        sealed = 0
        for i in range(N * N):
            r = mkworld.pb_records(self.cols[i])
            if r[0][3] or not (r[1][3] and r[1][4]):
                continue                                      # (not a block: a floor, or nothing to stop anyone)
            x, y = divmod(i, N)
            sd, changed = list(r[1][5]), False
            for e, (dx, dy) in enumerate(ARM_STEP):
                if self.inb(x + dx, y + dy) and (sd[e] >> 12) & 7 in (0, 5):
                    n0 = mkworld.pb_records(self.cols[(x + dx) * N + y + dy])
                    if n0[0][3] and n0[0][4]:
                        sd[e] = (sd[e] & 0x8fff) | 0x1000
                        sealed += 1
                        changed = True
            if changed:
                col = self.cols[i]
                self.cols[i] = col[:20 + 12] + struct.pack('<4H', *sd) + col[40:]
        self.notes.append('side walls on %d floor edges, %d posts, %d block faces sealed' % (walls, posts, sealed))

    # -- stage 6: phones, starts --
    def carve(self, x, y):
        """Plaza ground in place of any block round (x, y), so that a phone has clear ground about it."""
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if self.inb(x + dx, y + dy) and self.kind[(x + dx) * N + y + dy] in ('cliff', 'bld', 'tower', 'crate', 'table'):
                    self.put(x + dx, y + dy, col_ground(self.t['plaza']), 'ground')

    def place_phones(self):
        phones = []
        for g in self.plan['phones']:
            for x, y in g['cells']:
                self.carve(x, y)
                self.put(x, y, with_object(self.at(x, y), PHONE_OBJ), self.kind[x * N + y])
                phones.append((x, y, 0))
        assert len(phones) <= mksolo.PHONES_PER_MAP, 'more phones than the table holds'
        self.phones = phones

    def spawn_ok(self, x, y):
        """A start at (x, y): on a road or its kerb, AHEAD cells clear in front (arenacheck.av6's rule)."""
        return not arenacheck.av6(self.cols, [(x, y, 0)], self.pre)

    def choose_spawns(self):
        sp = self.plan['spawns']
        rom = self.rom
        self.pre = arenacheck.prep(self.cols)
        n = min(struct.unpack_from('<b', rom.d, mksolo.START_COUNT + LEVEL)[0] + 1, mksolo.STARTS_PER_MAP)
        old = [tuple(rom.d[mksolo.STARTS + 4 * (mksolo.STARTS_PER_MAP * LEVEL + i):][:3]) for i in range(n)]
        out = [s for s in old if self.spawn_ok(s[0], s[1])][:sp['pit_keep']]
        near = lambda a, b: (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
        cand = [(x, y) for x in range(N) for y in range(N)
                if self.kind[x * N + y] == 'road' and self.cols[x * N + y][3] == 0x20 and not self.in_pit(x, y)
                and arenacheck.heading(self.cols, x, y) is not None]
        for hx, hy in sp['extra']:
            for x, y in sorted(cand, key=lambda c: near(c, (hx, hy))):
                if all(near((x, y), s) >= 25 for s in out) and self.spawn_ok(x, y):
                    out.append((x, y, 0))
                    break
            else:
                raise AssertionError('no start near (%d, %d)' % (hx, hy))
        assert len(out) <= mksolo.STARTS_PER_MAP
        self.spawns = out

    # -- stage 7: into the ROM --
    def commit(self):
        ix, rom = self.ix, self.rom
        ids = []
        for c in self.cols:
            n = ix.lookup(c)
            ids.append(n if n is not None else rom.add_column(c))
        rom.set_grid(LEVEL, ids)
        rom.painted[LEVEL] = ids
        self.ids = ids

    def write_tables(self):
        d = self.rom.d
        for i, (x, y, k) in enumerate(self.spawns):
            struct.pack_into('<4B', d, mksolo.STARTS + 4 * (mksolo.STARTS_PER_MAP * LEVEL + i), x, y, k, 0)
        struct.pack_into('<b', d, mksolo.START_COUNT + LEVEL, len(self.spawns) - 1)
        for i, (x, y, k) in enumerate(self.phones):
            struct.pack_into('<4B', d, mksolo.PHONE_TABLE + 4 * (mksolo.PHONES_PER_MAP * LEVEL + i), x, y, k, 0)
        d[mksolo.PHONE_COUNT + LEVEL] = len(self.phones)

    def paint_all(self):
        self.paint_base()
        self.paint_districts()
        self.paint_roads()
        self.paint_features()
        self.finish_sides()
        self.place_phones()
        self.choose_spawns()
        assert all(c is not None for c in self.cols)


ARM_STEP = tuple(ARMS[d] for d in 'NESW')      # edge order of the side words: -y, +x, +y, -x


def build(rom, orig=None, plan=None, check=True):
    """Paint the Killing Zone into rom (a paybackmod PaybackRom) and return {3: loops} for mkworld.build(loops=...).
    orig: Payback's bytes (the minimap's compass is read from them). Raises AssertionError on any validator."""
    plan = plan or json.load(open(PLAN))
    orig = orig or bytes(rom.orig)
    a = Arena(rom, plan)
    a.paint_all()
    stamp = minimap.compass(orig, LEVEL)
    lanes = [c[3] & 15 for c in a.cols]
    pic = minimap.pack(minimap.pixels(lanes, stamp))
    if check:
        res = arenacheck.check(a, a.cols, a.spawns, a.phones, pic, stamp, minimap)
        bad = ['%s: %s' % (k, '; '.join(v[:3]) + (' (+%d more)' % (len(v) - 3) if len(v) > 3 else ''))
               for k, v in res.items() if v]
        if bad:
            raise AssertionError('Killing Zone validators failed:\n  ' + '\n  '.join(bad))
    a.commit()
    a.write_tables()
    minimap.write(rom, LEVEL, pic)
    for n in a.notes:
        print('arena:', n)
    print('arena: %d starts, %d phones, %d loops, %d new columns' % (len(a.spawns), len(a.phones), len(a.loops),
                                                                   len(rom.new_columns)))
    return {LEVEL: list(a.loops)}
