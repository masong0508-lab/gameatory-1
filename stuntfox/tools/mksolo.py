"""Every Payback map in single-player rampage, each with phones and missions (build.py --merge).

Payback's RAMPAGE SETUP (0x08034c08) offers a map only when the story trophies say so (maps
1, 2, 4..9 follow the six trophy words at 0x020026d2; 0, 3 and 10 are always there): its eight
"movs rX, #0" defaults become "#1", so every map is offered from the start.

A rampage only gets its target score, its phone and its random missions (the level handler
0x08047034, which finds its own places to send you) when the map has rampage phones: a count per
map at 0x08193d08 and 22 (x, y, floor) entries per map at 0x08193940. The Killing Zone, Desert
Deathmatch, Tank Warfare, The Big Track and Isla Nublar have none, so here they get phones of
our own choosing: kerbside cells next to a road, spread far apart, in the walkable area around
the map's own start points (0x081928e0: 68 x (x, y, floor, 0) per map, count - 1 at 0x08193490;
a rampage starts at one of them at random). Payback rings and draws a phone only where the
cell holds one (object 0x0e in the floor record, as in Little Chicago's), so those cells are
repainted with one.

After each rampage whose target is reached, src/merge.c (sf_menu) starts a rampage on the next
map, so a rampage begun on Freedom City runs through all eleven as a campaign.
"""
import struct

PHONE_COUNT = 0x193d08              # s8 per map
PHONE_TABLE = 0x193940              # 22 x (x, y, floor, 0) per map
PHONES_PER_MAP = 22
STARTS = 0x1928e0                   # 68 x (x, y, floor, 0) per map
START_COUNT = 0x193490              # s8 per map: the number of start points - 1
STARTS_PER_MAP = 68
NEW_PHONES = 8
OBJ_PHONE = 0x0e
RAMPAGE_OFFER = ((0x034c48, 0x2200), (0x034c5a, 0x2200), (0x034c74, 0x2200), (0x034c84, 0x2300),
                 (0x034c96, 0x2200), (0x034ca8, 0x2200), (0x034cb6, 0x2500), (0x034d26, 0x2500))


def offer_every_map(d):
    for off, op in RAMPAGE_OFFER:
        assert struct.unpack_from('<H', d, off)[0] == op, 'rampage setup not as expected at %x' % off
        struct.pack_into('<H', d, off, op | 1)


EDGE_CORNERS = ((0xc, 0), (0x5, 1), (0x3, 2), (0xa, 3))   # (as mkworld: corners -> edge -y, +x, +y, -x)
STEPS = ((0, -1), (1, 0), (0, 1), (-1, 0))
CLIMB = 0x20                        # the most one step up or down between cells
HEADROOM = 0x80


def surfaces(col):
    """Where people can stand in a column: {record: (lowest top, highest top, shape, record
    bytes)}. Records stack from height 0, each as thick as its h0 / h1 (mkworld.stack); a solid
    one is a floor when the next solid record leaves headroom over it."""
    base, solid = 0, []
    for k in range(3):
        b = col[20 * k:20 * k + 20]
        h0, h1, shape = struct.unpack_from('<hhB', b, 4)
        if shape and b[9] & 0x20:
            solid.append((k, base, base + h0, base + h1, shape, b))
        base += h0
    out = {}
    for i, (k, bottom, t0, t1, shape, b) in enumerate(solid):
        if i + 1 == len(solid) or solid[i + 1][1] >= max(t0, t1) + HEADROOM:
            out[k] = (t0, t1, shape, b)
    return out


# the edge (0 -y, 1 +x, 2 +y, 3 -x) where each slope shape is low, and where it is high
SLOPE_EDGES = {2: (0, 2), 3: (3, 1), 4: (2, 0), 5: (1, 3)}


def _edge(s, e):
    """The range of heights a surface has along edge e."""
    t0, t1, shape, _ = s
    lo_hi = SLOPE_EDGES.get(shape)
    if lo_hi is None:
        return t0, t0
    if e == lo_hi[0]:
        return t0, t0
    if e == lo_hi[1]:
        return t1, t1
    return min(t0, t1), max(t0, t1)


def _blocks(b, e):
    m = EDGE_CORNERS[e][0]
    return (b[9] & m) == m


def _walk(rom, level, seeds):
    """Every (x, y, record) one can walk to from the seeds: up at most CLIMB a step, down any
    drop (Payback's man steps off ledges), never across an edge the street floor blocks (only
    the ground floor's corner flags stop him: measured on Isla Nublar, where he walks off the
    start platform over cells whose upper floor has all four corners set)."""
    g = rom.grid(level)
    surf = {}
    def at(x, y):
        if (x, y) not in surf:
            surf[x, y] = surfaces(rom.column(g[x * 128 + y]))
        return surf[x, y]
    area = set()
    todo = []
    for x, y, k in seeds:
        if k in at(x, y):
            area.add((x, y, k)); todo.append((x, y, k))
    while todo:
        x, y, k = todo.pop()
        here = at(x, y)[k]
        for e, (dx, dy) in enumerate(STEPS):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < 128 and 0 <= ny < 128) or k == 0 and _blocks(here[3], e):
                continue
            lo, hi = _edge(here, e)
            for j, there in at(nx, ny).items():
                lo2, hi2 = _edge(there, e ^ 2)
                if (nx, ny, j) not in area and lo2 <= hi + CLIMB and not (j == 0 and _blocks(there[3], e ^ 2)):
                    area.add((nx, ny, j)); todo.append((nx, ny, j))
    return area, surf


def starts(rom, level):
    n = min(struct.unpack_from('<b', rom.d, START_COUNT + level)[0] + 1, STARTS_PER_MAP)
    return [tuple(rom.d[STARTS + 4 * (STARTS_PER_MAP * level + i):][:3]) for i in range(n)]


def choose_phones(rom, level, n=NEW_PHONES):
    """Up to n phone places (x, y, record) for a level, spread apart, each where one can walk
    from the level's start points, on flat ground with nothing on it, beside a road."""
    area, surf = _walk(rom, level, starts(rom, level))
    def road(x, y, k):
        s = surf.get((x, y), {}).get(k)
        return s is not None and s[3][3] & 0xf
    pool = []
    for x, y, k in area:
        b = surf[x, y][k][3]
        if b[8] == 1 and b[4:6] == b[6:8] and b[1] == 0 and not b[3] & 0xf and any(
                road(x + dx, y + dy, k) for dx, dy in STEPS):
            pool.append((x, y, k))
    if not pool:
        return []
    pool.sort()
    floor0 = [c for c in pool if c[2] == 0]
    pool = floor0 or pool              # (the floor the phone check wants is surely right for 0)
    cx = sum(c[0] for c in area) / len(area)
    cy = sum(c[1] for c in area) / len(area)
    picked = [min(pool, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)]
    while len(picked) < min(n, len(pool)):        # each farthest from those already picked
        picked.append(max(pool, key=lambda c: min((c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2 for p in picked)))
    return picked


def add_phones(rom):
    """Phones for every map that has none. Returns {level: [(x, y, record), ...]}."""
    added = {}
    for level in range(11):
        if rom.d[PHONE_COUNT + level]:
            continue
        cells = choose_phones(rom, level)
        g = rom.grid(level)
        paint = {}
        for i, (x, y, k) in enumerate(cells):
            col = bytearray(rom.column(g[x * 128 + y]))
            col[20 * k + 1], col[20 * k + 2] = OBJ_PHONE, 0
            paint[x, y] = bytes(col)
            struct.pack_into('<4B', rom.d, PHONE_TABLE + 4 * (PHONES_PER_MAP * level + i), x, y, k, 0)
        if paint:
            rom.paint(level, paint)
            rom.d[PHONE_COUNT + level] = len(cells)
            added[level] = cells
    return added
