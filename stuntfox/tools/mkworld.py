"""Builds Stunt Fox's 3D city from the player's own Payback ROM.

Like IW4L reading a game install, nothing from Payback is stored in this repository: the
city layout (roads, kerbs, plazas, building footprints and heights, ramps) is decoded from
Freedom City's level grid at build time and turned into Stunt Fox's own world format.

World units: one Payback cell is 1024 units (about 8 m). X runs with Payback's x, Z with
Payback's y, and Y is up.

Output (little endian), see src/world.h:
    header   'SFW1', counts and offsets
    boxes    buildings: x0 z0 x1 z1 (cells), height (units), material
    lots     ground patches that are not road: x0 z0 x1 z1, material
    ramps    drivable slopes: x0 z0 x1 z1, h0 h1, rising direction, material
    loops    x z (units), direction, radius, width
    sectors  16 x 16 sectors of 8 x 8 cells: index into the item list
    items    u16: kind << 13 | index
    height   128 x 128 cells: s16 low, s16 high, u8 shape, u8 material (collision and minimap)
    far      16 x 16 sectors: material and average height for distant rendering
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'payback-mod'))
from paybackmod.rom import PaybackRom   # noqa: E402

CELL = 1024
N = 128
STREET = 0x100

# materials (rows of the palette, see src/palette.c)
M_SKY, M_ROAD, M_KERB, M_GRASS, M_PLAZA, M_CONCRETE, M_GLASS, M_BRICK, M_TEAL, M_CREAM, \
    M_STEEL, M_CAR, M_ACCENT, M_SHIP, M_GLOW, M_STUNT = range(16)
BUILDING_MATS = (M_CONCRETE, M_GLASS, M_BRICK, M_TEAL, M_CREAM, M_STEEL)
GRASS_TEX = {0x0c, 0x0b, 0x0d}
WATER_MAT = M_GLASS

K_BOX, K_LOT, K_RAMP, K_LOOP = range(4)
STADIUM = (40, 24, 80, 44)      # x0, y0, x1, y1 (exclusive) of the football stadium block


def h_units(h):
    return (h - STREET) * 8


def classify(rom):
    """Per cell: (kind, low, high, shape, material). kind: road, kerb, ground, ramp, building."""
    grid = rom.grid(0)
    cells = []
    for i in range(N * N):
        col = rom.column(grid[i])
        top, top_tex = STREET, None
        recs = []
        for k in range(3):
            b = col[20 * k:20 * k + 20]
            h0, h1, shape = struct.unpack_from('<HHB', b, 4)
            if shape:
                recs.append((h0, h1, shape, b[10]))
                if max(h0, h1) >= top:
                    top, top_tex = max(h0, h1), b[10]
        lanes = col[3]
        floor = recs[0] if recs else (STREET, STREET, 1, col[10])
        if top >= 0x8000:                     # below-street cells (water / pits): flat water
            cells.append(('ground', 0, 0, 1, WATER_MAT))
        elif len(recs) == 1 and floor[2] in (2, 3, 4, 5) and min(floor[0], floor[1]) <= STREET + 0x20:
            lo, hi = sorted((floor[0], floor[1]))
            cells.append(('ramp', h_units(lo), h_units(hi), floor[2], M_KERB))
        elif top > STREET:
            mat = BUILDING_MATS[(top_tex * 7 + 3) % len(BUILDING_MATS)]
            cells.append(('building', h_units(top), h_units(top), 1, mat))
        elif lanes & 0x0f:
            cells.append(('road', 0, 0, 1, M_ROAD))
        elif lanes & 0x20:
            cells.append(('kerb', 0, 0, 1, M_KERB))
        else:
            tex = col[10]
            mat = M_GRASS if tex in GRASS_TEX else M_ROAD if tex == 0x2b else M_PLAZA
            cells.append(('ground', 0, 0, 1, mat))
    return cells


def stunt_park(cells):
    """The stadium becomes an open stunt arena: flat floor, kickers and a loop are added later."""
    x0, y0, x1, y1 = STADIUM
    for x in range(x0, x1):
        for y in range(y0, y1):
            edge = x in (x0, x1 - 1) or y in (y0, y1 - 1)
            gate = edge and (y0 + 7 <= y <= y1 - 8)        # open ends to the east and west
            if edge and not gate and y in (y0, y1 - 1):
                cells[x * N + y] = ('building', 384, 384, 1, M_STUNT)      # low striped walls
            else:
                stripe = (x - x0) % 10 == 5 and y0 + 2 <= y < y1 - 2
                cells[x * N + y] = ('ground', 0, 0, 1, M_KERB if stripe else M_GRASS)
    ramps = []

    def kicker(xa, ya, xb, yb, h, direction):
        for x in range(xa, xb):
            for y in range(ya, yb):
                if direction == 3:   # rising toward +x
                    t0, t1 = (x - xa) * h // (xb - xa), (x - xa + 1) * h // (xb - xa)
                else:                # rising toward -x
                    t0, t1 = (xb - 1 - x) * h // (xb - xa), (xb - x) * h // (xb - xa)
                cells[x * N + y] = ('ramp', t0, t1, direction, M_STUNT)
        ramps.append((xa, ya, xb, yb))

    kicker(46, 27, 50, 30, 384, 3)       # north lane: kicker toward +x
    kicker(70, 38, 74, 41, 384, 5)       # south lane: kicker toward -x
    return ramps


def greedy(cells, want, cap):
    """Merge cells into rectangles. want(i) -> key or None. Returns [(x0, y0, x1, y1, key)]."""
    used = [False] * (N * N)
    out = []
    for y in range(N):
        for x in range(N):
            i = x * N + y
            k = want(i)
            if k is None or used[i]:
                continue
            w = 1
            while x + w < N and w < cap and not used[(x + w) * N + y] and want((x + w) * N + y) == k:
                w += 1
            h = 1
            while y + h < N and h < cap and all(
                    not used[(x + j) * N + y + h] and want((x + j) * N + y + h) == k for j in range(w)):
                h += 1
            for j in range(w):
                for m in range(h):
                    used[(x + j) * N + y + m] = True
            out.append((x, y, x + w, y + h, k))
    return out


def build(rom_bytes):
    rom = PaybackRom(rom_bytes)
    cells = classify(rom)
    stunt_park(cells)

    boxes = greedy(cells, lambda i: (cells[i][2], cells[i][4]) if cells[i][0] == 'building' else None, 4)
    lots = greedy(cells, lambda i: cells[i][4] if cells[i][0] in ('ground', 'kerb') and cells[i][4] != M_ROAD
                  else None, 16)
    ramps = greedy(cells, lambda i: cells[i][1:5] if cells[i][0] == 'ramp' else None, 8)
    # loops: (x, z) of the entry point in units, direction (0 +z, 1 +x, 2 -z, 3 -x), radius, width
    loops = [(60 * CELL, int(36.5 * CELL), 1, 2560, 1536)]

    # sector index
    sectors = [[] for _ in range(256)]

    def add(kind, idx, x0, y0, x1, y1):
        for sx in range(x0 // 8, (x1 - 1) // 8 + 1):
            for sy in range(y0 // 8, (y1 - 1) // 8 + 1):
                sectors[sx * 16 + sy].append(kind << 13 | idx)
    for i, (x0, y0, x1, y1, _) in enumerate(boxes):
        add(K_BOX, i, x0, y0, x1, y1)
    for i, (x0, y0, x1, y1, _) in enumerate(lots):
        add(K_LOT, i, x0, y0, x1, y1)
    for i, (x0, y0, x1, y1, _) in enumerate(ramps):
        add(K_RAMP, i, x0, y0, x1, y1)
    for i, (x, z, d, r, w) in enumerate(loops):
        cx, cz = x // CELL, z // CELL
        add(K_LOOP, i, max(0, cx - 4), max(0, cz - 4), min(N, cx + 5), min(N, cz + 5))

    items, starts = [], []
    for s in sectors:
        starts.append((len(items), len(s)))
        items += s

    far = []
    for sx in range(16):
        for sy in range(16):
            hs = [cells[(sx * 8 + i) * N + sy * 8 + j] for i in range(8) for j in range(8)]
            b = [c for c in hs if c[0] == 'building']
            mat = max(set(c[4] for c in b), key=[c[4] for c in b].count) if len(b) > 20 else \
                M_GRASS if sum(c[4] == M_GRASS for c in hs) > 32 else M_ROAD
            avg = sum(c[2] for c in b) // max(1, len(b)) if len(b) > 20 else 0
            far.append((mat, avg))

    blob = bytearray()
    parts = []

    def section(data):
        while len(blob) % 4:
            blob.append(0)
        parts.append(len(blob))
        blob.extend(data)

    section(b''.join(struct.pack('<BBBBhBB', x0, y0, x1, y1, k[0], k[1], 0) for x0, y0, x1, y1, k in boxes))
    section(b''.join(struct.pack('<BBBBB', x0, y0, x1, y1, k) for x0, y0, x1, y1, k in lots))
    section(b''.join(struct.pack('<BBBBhhBB', x0, y0, x1, y1, k[0], k[1], k[2], k[3])
                     for x0, y0, x1, y1, k in ramps))
    section(b''.join(struct.pack('<iiBxhhxx', x, z, d, r, w) for x, z, d, r, w in loops))
    section(b''.join(struct.pack('<HH', a, b) for a, b in starts))
    section(b''.join(struct.pack('<H', v) for v in items))
    section(b''.join(struct.pack('<hhBB', c[1], c[2], c[3], c[4]) for c in cells))
    section(b''.join(struct.pack('<Bxh', m, h) for m, h in far))
    header = struct.pack('<4s8I', b'SFW1', len(boxes), len(lots), len(ramps), len(loops), len(items), 0, 0, 0)
    header += struct.pack('<8I', *[p + 4 * 9 + 4 * 8 for p in parts])
    return header + bytes(blob), dict(boxes=len(boxes), lots=len(lots), ramps=len(ramps), items=len(items))


if __name__ == '__main__':
    data, stats = build(open(sys.argv[1], 'rb').read())
    open(sys.argv[2], 'wb').write(data)
    print('world:', stats, len(data), 'bytes')
