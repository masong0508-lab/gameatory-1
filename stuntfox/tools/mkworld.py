"""Builds Stunt Fox's 3D city from the player's own Payback ROM.

Like IW4L reading a game install, nothing from Payback is stored in this repository: the
city layout (roads, kerbs, plazas, building footprints and heights, ramps) is decoded from
the city's level grid at build time and turned into Stunt Fox's own world format.

World units: one Payback cell is 1024 units (about 8 m). X runs with Payback's x, Z with
Payback's y, and Y is up.

Output (little endian), see src/world.h:
    header   'SFW2', counts and offsets
    boxes    buildings: x0 z0 x1 z1 (cells), height (units), material, base (units / 64: 0, or
             the underside of a deck spanning over open air, a bridge)
    lots     ground patches that are not road: x0 z0 x1 z1, material
    ramps    drivable slopes: x0 z0 x1 z1, h0 h1, rising direction, material
    loops    x z (units), direction, radius, width
    lines    road centre lines: at, from, to (cells), dir (0 along z, 1 along x) | crossings << 1
    trees    x z (units / 4), height (units / 8), kind
    ctex     128 x 128 cells: Payback tile id of the cell's top surface (0xffff: none)
    btex     per box, 4 sides (-z, +x, +z, -x) x 4 cells along it: Payback tile id (0xffff: none)
    sectors  16 x 16 sectors of 8 x 8 cells: index into the item list
    items    u16: kind << 13 | index
    height   128 x 128 cells: s16 low, s16 high, u8 shape, u8 material (collision and minimap)
    far      16 x 16 sectors: material and average height for distant rendering
    deck     128 x 128 cells: s8 bottom, s8 top (units / 64) of a deck over the cell, 0 0: none
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

K_BOX, K_LOT, K_RAMP, K_LOOP, K_LINE, K_TREE = range(6)
STADIUM = (40, 24, 80, 44)      # x0, y0, x1, y1 (exclusive) of the football stadium block


def h_units(h):
    return (h - STREET) * 8


FENCE_EDGE = {0x3: 2, 0xc: 0, 0x5: 1, 0xa: 3}    # flags' low bits -> edge (-z, +x, +z, -x)


def fence_of(recs):
    """A street-level cell with a sloped block standing on it whose flags mark one edge: Payback
    draws a slanted panel there, and people walk through the cell freely except across the
    opposite edge (measured by walking Payback's man into every such cell). That is a fence or
    railing on that edge. Returns (edge, height in units, tile) or None."""
    if len(recs) < 2 or recs[0][:3] != (STREET, STREET, 1):
        return None
    up = max(recs[1:], key=lambda r: max(r[0], r[1]))
    if up[2] not in (2, 3, 4, 5) or min(up[0], up[1]) > STREET + 0x20 or max(up[0], up[1]) <= STREET:
        return None
    edge = FENCE_EDGE.get(up[4] & 15)
    if edge is None:
        return None
    return edge, h_units(max(up[0], up[1])), up[5]


# Payback's street objects: the object type is byte 1 of a cell's floor record, byte 0 turns it.
# Walking Payback's man into them: trees (3, 5, 7, 8) and lamps (2, 15) are sprites he walks
# past or through, but benches (6, 18) and bins (14) stop him: invisible walls unless drawn.
OBJ_TREES = {3: 900, 7: 800, 5: 650, 8: 450}     # type -> height (units)
OBJ_PROPS = {6: 6, 18: 6, 14: 7, 2: 8, 15: 8}    # type -> kind: 6 bench, 7 bin, 8 lamp


def street_objects(rom, cells):
    """(x, z, h, kind) entries for the trees list: trees as kind 0/1 (x, z in units / 4),
    props as kind 6..8 with the cell (x | turn << 7, z)."""
    out = []
    grid = rom.grid(0)
    for i in range(N * N):
        if cells[i][0] not in ('road', 'kerb', 'ground') or cells[i][4] == WATER_MAT:
            continue
        b = rom.column(grid[i])[0:20]
        if not b[8] or not b[1]:
            continue
        x, z = divmod(i, N)
        if b[1] in OBJ_TREES:
            out.append(((x * CELL + CELL // 2) // 4, (z * CELL + CELL // 2) // 4,
                        OBJ_TREES[b[1]] // 8, b[1] & 1))
        elif b[1] in OBJ_PROPS:
            out.append((x | b[0] << 7, z, 0, OBJ_PROPS[b[1]]))
    return out


# Which edges of a cell Payback stops people at: the low four bits of the flags byte of the floor
# they stand on are its corners, and an edge blocks when both its corners are set (the same
# bits as FENCE_EDGE). Measured by walking Payback's man across about 1100 cell edges: right
# for 51 of 56 edges this marks, and many of them had nothing drawn there.
EDGE_CORNERS = ((0xc, 0), (0x5, 1), (0x3, 2), (0xa, 3))     # corners -> edge (-z, +x, +z, -x)
EDGE_STEP = ((0, -1), (1, 0), (0, 1), (-1, 0))


def floors(col):
    """A column's floor records as classify() reads them: (h0, h1, shape, tile, flags, tile id)."""
    out = []
    for k in range(3):
        b = col[20 * k:20 * k + 20]
        h0, h1, shape = struct.unpack_from('<HHB', b, 4)
        if shape:
            out.append((h0, h1, shape, b[10], b[9], b[10] | (b[11] & 3) << 8))
    return out


def blocked_edges(recs):
    """Edges (0..3) a street-level walker cannot cross into this cell: by the flags of the
    highest floor at or below the street; a sloped floor only counts as a pit walled all
    round."""
    under = [r for r in recs if max(r[0], r[1]) <= STREET]
    if not under:
        return []
    w = max(under, key=lambda r: max(r[0], r[1]))
    if w[2] != 1 and not ((w[4] & 15) == 15 and max(w[0], w[1]) < STREET):
        return []
    return [e for m, e in EDGE_CORNERS if (w[4] & m) == m]


def edge_walls(rom, cells, skip):
    """Fences (trees list entries, kind 2 + edge) on every edge Payback blocks where nothing
    solid is drawn: not beside a building or a ramp up (both are seen), not in cells that already
    have a fence or a bench or bin (skip), each shared edge once."""
    grid = rom.grid(0)
    out, done = [], set()
    for i in range(N * N):
        if cells[i][0] in ('building', 'ramp') or i in skip:
            continue
        x, y = divmod(i, N)
        for e in blocked_edges(floors(rom.column(grid[i]))):
            nx, ny = x + EDGE_STEP[e][0], y + EDGE_STEP[e][1]
            if not (0 <= nx < N and 0 <= ny < N):
                continue
            o = cells[nx * N + ny]
            if o[0] == 'building' or o[0] == 'ramp' and o[2] > 0:
                continue                      # (a slope down into an underpass gets its railing)
            key = (min(i, nx * N + ny), e & 1)
            if key in done:
                continue
            done.add(key)
            out.append((x | 511 << 7, y, 25, 2 + e))
    return out


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def stack(col):
    """Payback's column as it really stands: its three records sit on one another from height
    0, each as thick as its h0 / h1. Shape 0 is open air, and so is a record without flag 0x20
    (tile 0, nothing drawn: people walk through those). Measured by dropping Payback's man onto
    them: on the bridge at cells (16..17, 49..50) the road below is at 0 (z 24000) and the deck
    above at 0x100 (z 19904) from records 0 / 0xc0 air / 0x40; a building of 0x100 air and 0x170
    solid has its roof at 0x270 (z 14016), not at 0x170; the slab over the road at (56, 75) is
    0x280..0x400; the slope at (2, 18) of 0x100 air and 0x60 / 0xc0 is at 0x190 in its middle.
    Returns the solid layers: [(bottom, top0, top1, shape, flags, tile)]."""
    base, out = 0, []
    for k in range(3):
        b = col[20 * k:20 * k + 20]
        h0, h1, shape = struct.unpack_from('<HHB', b, 4)
        h0, h1 = s16(h0), s16(h1)
        if shape and b[9] & 0x20:
            out.append((base, base + h0, base + h1, shape, b[9], b[10] | (b[11] & 3) << 8))
        base += h0      # (after a slope, from its h0 edge: both parapets of that bridge at 0x150)
    return out


def floor_and_deck(col):
    """The surface Payback's people and traffic stand on in a cell, and what spans over it with
    open air in between (a bridge deck, a walkway, a building over the road), from stack().
    Returns (floor layer or None, its top, deck or None): deck = (bottom, top, tile)."""
    layers = stack(col)
    if not layers:
        return (0, STREET, STREET, 1, 0, 0), STREET, None
    floor, top, deck, tile = layers[0], max(layers[0][1], layers[0][2]), None, layers[0][5]
    for lay in layers[1:]:
        t = max(lay[1], lay[2])
        if deck is None and lay[0] <= top:
            floor, top, tile = None, max(top, t), lay[5]     # solid on solid: one block
        elif deck is None:
            deck = (lay[0], t, lay[5])
        else:
            deck = (deck[0], max(deck[1], t), lay[5])
    return floor if floor is not None else (0, top, top, 1, 0, tile), top, deck


def classify(rom, stacked=False, decks=None):
    """Per cell: (kind, low, high, shape, material). kind: road, kerb, ground, ramp, building.
    stacked (Stunt Fox inside Payback): heights as Payback has them (stack()), and cells with
    open air under something get their floor here and the thing over it in decks (index ->
    (bottom, top, material, tile)), so the road goes on under bridges."""
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
                recs.append((h0, h1, shape, b[10], b[9], b[10] | (b[11] & 3) << 8))
                if max(h0, h1) >= top:
                    top, top_tex = max(h0, h1), b[10]
        lanes = col[3]
        floor = recs[0] if recs else (STREET, STREET, 1, col[10])
        if stacked and top < 0x8000:
            fl, top, deck = floor_and_deck(col)
            top_tex = fl[5] & 0xff if top_tex is None else top_tex
            if deck and decks is not None:
                tile = deck[2]
                decks[i] = (h_units(deck[0]), h_units(deck[1]),
                            BUILDING_MATS[((tile & 0xff) * 7 + 3) % len(BUILDING_MATS)], tile)
                recs = [(fl[1], fl[2], fl[3])]   # the floor alone decides what the cell is
            elif len(recs) == 1:
                recs = [(fl[1], fl[2], fl[3])]
            floor = recs[0] if recs else floor
            if top < STREET and fl[3] == 1:
                # a flat floor below the street (the road under a bridge): a flat ramp down there
                cells.append(('ramp', h_units(top), h_units(top), 1, M_ROAD if lanes & 0x0f else M_KERB))
                continue
        if top >= 0x8000:                     # below-street cells (water / pits): flat water
            cells.append(('ground', 0, 0, 1, WATER_MAT))
        elif len(recs) == 1 and floor[2] in (2, 3, 4, 5) and min(floor[0], floor[1]) <= STREET + 0x20:
            lo, hi = sorted((floor[0], floor[1]))
            # the shape says which way h0 -> h1 runs (h0 on the -y / -x edge for 2 / 3, measured
            # on the slopes into the underpass at (16, 45..47)); a ramp coming down runs the other way
            shape = floor[2] if floor[0] <= floor[1] else {2: 4, 3: 5, 4: 2, 5: 3}[floor[2]]
            cells.append(('ramp', h_units(lo), h_units(hi), shape, M_KERB))
        elif fence_of(recs):
            # a railing, fence or thin wall along one edge of a street-level cell (see fence_of):
            # the cell itself is street, the fence is drawn on its own
            tex = col[10]
            mat = M_ROAD if lanes & 0x0f else M_KERB if lanes & 0x20 else \
                M_GRASS if tex in GRASS_TEX else M_ROAD if tex == 0x2b else M_PLAZA
            cells.append(('road' if lanes & 0x0f else 'kerb' if lanes & 0x20 else 'ground', 0, 0, 1, mat))
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


def centre_lines(rom, cells):
    """Dashed lines between a road's two opposite lanes (Payback marks each road cell with its
    traffic directions: 1 / 4 for the two lanes along y, 2 / 8 along x). Runs of at most 16
    cells. A run that ends at a junction gets a zebra crossing there."""
    grid = rom.grid(0)
    lanes = [rom.column(grid[i])[3] & 15 if cells[i][0] == 'road' else 0 for i in range(N * N)]
    junction = lambda i: cells[i][0] == 'road' and lanes[i] not in (1, 2, 4, 8)
    out = []
    for d, pair in ((0, {1, 4}), (1, {2, 8})):
        for a in range(N - 1):
            # cell index of (across a / a + 1, along t)
            idx = (lambda a, t: a * N + t) if d == 0 else (lambda a, t: t * N + a)
            t = 0
            while t < N:
                if {lanes[idx(a, t)], lanes[idx(a + 1, t)]} != pair:
                    t += 1
                    continue
                t0 = t
                while t < N and t - t0 < 16 and {lanes[idx(a, t)], lanes[idx(a + 1, t)]} == pair:
                    t += 1
                cross = 0
                if t0 > 0 and junction(idx(a, t0 - 1)):
                    cross |= 1
                if t < N and junction(idx(a, t)):
                    cross |= 2
                out.append((a + 1, t0, t, d | cross << 1))
    return out


def park_trees(cells):
    """A tree on about every other grass cell outside the stunt arena."""
    x0, y0, x1, y1 = STADIUM
    out = []
    for x in range(N):
        for y in range(N):
            c = cells[x * N + y]
            if c[0] != 'ground' or c[4] != M_GRASS or (x0 <= x < x1 and y0 <= y < y1):
                continue
            h = (x * 73856093 ^ y * 19349663) & 0xffff
            if h & 1:
                continue
            ox, oy = 256 + (h >> 1) % 512, 256 + (h >> 5) % 512
            out.append(((x * CELL + ox) // 4, (y * CELL + oy) // 4, 60 + (h >> 9) % 40, (h >> 3) & 1))
    return out


# Payback's 32 x 32 tiles: ids below TILE_IDS index a bank in ROM. Only ids are stored here;
# the game finds the tiles through Payback's own table at run time.
TILE_BANK = 0x0ce0bc
TILE_IDS = 0x318


def tile_ok(rom_bytes, tid, most=0x100):
    """A tile that is not mostly see-through (colour 0): railings and fences are left out."""
    if tid >= TILE_IDS:
        return False
    a = TILE_BANK + tid * 0x400
    return rom_bytes[a:a + 0x400].count(0) < most


def recs_of(col):
    out = []
    for k in range(3):
        b = col[20 * k:20 * k + 20]
        h0, h1, shape = struct.unpack_from('<HHB', b, 4)
        if shape:
            out.append((max(h0, h1), b[10] | (b[11] & 3) << 8, struct.unpack_from('<4H', b, 12)))
    return out


def tex_tables(rom, rom_bytes, cells, boxes, merge=False, decks=None):
    """Tile ids for the top of every cell and for the walls of every box."""
    grid = rom.grid(0)
    cols = [recs_of(rom.column(grid[i])) for i in range(N * N)]
    x0, y0, x1, y1 = STADIUM if not merge else (0, 0, 0, 0)
    decks = decks or {}
    ctex = []
    for i in range(N * N):
        x, y = divmod(i, N)
        tid = 0xffff
        if merge and (i in decks or cells[i][0] == 'ramp'):
            # a ramp, the road under a bridge or a sunken floor: its own tile, unless a deck at
            # street level covers it (then that is the street people walk on)
            fl, _, deck = floor_and_deck(rom.column(grid[i]))
            t = deck[2] if deck and i in decks and decks[i][1] <= 256 else fl[5]
            if tile_ok(rom_bytes, t):
                tid = t
        elif cols[i] and not (x0 <= x < x1 and y0 <= y < y1) and cells[i][0] != 'ramp':
            top = max(cols[i], key=lambda r: r[0])
            if top[0] < 0x8000 and tile_ok(rom_bytes, top[1]):
                tid = top[1]
        ctex.append(tid)

    def side(i, s):
        for h, _, sides in sorted(cols[i], key=lambda r: -r[0]):
            t = sides[s] & 0x3ff
            if t and tile_ok(rom_bytes, t, 0x280):    # (dark see-through windows are fine on walls)
                return t
        return None
    btex = []
    for bx0, by0, bx1, by1, k in boxes:
        ids = []
        for s in range(4):
            if s == 0:
                cl = [x * N + by0 for x in range(bx0, bx1)]
            elif s == 1:
                cl = [(bx1 - 1) * N + y for y in range(by0, by1)]
            elif s == 2:
                cl = [x * N + by1 - 1 for x in range(bx0, bx1)]
            else:
                cl = [bx0 * N + y for y in range(by0, by1)]
            t = [side(i, s) for i in cl]
            fill = next((v for v in t if v is not None), None)
            if fill is None:      # nothing on this side: borrow from another side of the box
                for s2 in range(4):
                    fill = fill or next((side(i, s2) for i in cl if side(i, s2) is not None), None)
            if fill is None and ctex[cl[0]] != 0xffff:
                fill = ctex[cl[0]]  # still nothing: the box's own roof, as a plain wall
            t = [v if v is not None else fill for v in t]
            t = [0xffff if v is None or k[1] == M_STUNT else v for v in t] + [0xffff] * (4 - len(t))
            ids += t[:4]
        btex.append(ids)
    return ctex, btex


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


def build(rom_bytes, merge=False):
    """merge: for Stunt Fox inside Payback, where Payback's own collision decides where people
    walk, so the city is drawn exactly as Payback has it (its stadium, not the stunt arena)."""
    rom = PaybackRom(rom_bytes)
    decks = {}
    cells = classify(rom, stacked=merge, decks=decks)
    if not merge:
        stunt_park(cells)

    boxes = greedy(cells, lambda i: (cells[i][2], cells[i][4], 0) if cells[i][0] == 'building' else None, 4)
    # what spans over open air (bridge decks, walkways, buildings over a road): boxes with a base
    boxes += greedy(cells, lambda i: (decks[i][1], decks[i][2], decks[i][0]) if i in decks else None, 4)
    lots = greedy(cells, lambda i: cells[i][4] if cells[i][0] in ('ground', 'kerb') and cells[i][4] != M_ROAD
                  else None, 16)
    ramps = greedy(cells, lambda i: cells[i][1:5] if cells[i][0] == 'ramp' else None, 8)
    # loops: (x, z) of the entry point in units, direction (0 +z, 1 +x, 2 -z, 3 -x), radius, width
    loops = [(60 * CELL, int(36.5 * CELL), 1, 2560, 1536)]
    lines = centre_lines(rom, cells)
    if merge:
        # Payback's fences, trees, benches, bins and lamps (citydraw.c draw_tree)
        trees = []
        grid = rom.grid(0)
        for i in range(N * N):
            col = rom.column(grid[i])
            recs = []
            for k in range(3):
                b = col[20 * k:20 * k + 20]
                h0, h1, shape = struct.unpack_from('<HHB', b, 4)
                if shape:
                    recs.append((h0, h1, shape, b[10], b[9], b[10] | (b[11] & 3) << 8))
            fe = fence_of(recs)
            if fe:
                x, y = divmod(i, N)
                tile = fe[2] if fe[2] < 512 and tile_ok(rom_bytes, fe[2], 0x280) else 511
                trees.append((x | tile << 7, y, min(255, fe[1] // 8), 2 + fe[0]))
        objects = street_objects(rom, cells)
        skip = {(t[0] & 127) * N + t[1] for t in trees + objects if t[3] >= 2}
        trees += objects + edge_walls(rom, cells, skip)
    else:
        trees = park_trees(cells)
    ctex, btex = tex_tables(rom, rom_bytes, cells, boxes, merge, decks)

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
    for i, (at, t0, t1, d) in enumerate(lines):
        if d & 1:
            add(K_LINE, i, t0, at - 1, t1, at + 1)
        else:
            add(K_LINE, i, at - 1, t0, at + 1, t1)
    for i, (x, z, h, k) in enumerate(trees):
        if k >= 2:      # a fence: cell x (low 7 bits; the tile above), cell z
            add(K_TREE, i, x & 127, z, (x & 127) + 1, z + 1)
        else:
            add(K_TREE, i, x * 4 // CELL, z * 4 // CELL, x * 4 // CELL + 1, z * 4 // CELL + 1)
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

    assert all(k[2] % 64 == 0 and -128 * 64 <= k[2] < 128 * 64 for *_, k in boxes)
    section(b''.join(struct.pack('<BBBBhBb', x0, y0, x1, y1, k[0], k[1], k[2] // 64) for x0, y0, x1, y1, k in boxes))
    section(b''.join(struct.pack('<BBBBB', x0, y0, x1, y1, k) for x0, y0, x1, y1, k in lots))
    section(b''.join(struct.pack('<BBBBhhBB', x0, y0, x1, y1, k[0], k[1], k[2], k[3])
                     for x0, y0, x1, y1, k in ramps))
    section(b''.join(struct.pack('<iiBxhhxx', x, z, d, r, w) for x, z, d, r, w in loops))
    section(b''.join(struct.pack('<HH', a, b) for a, b in starts))
    section(b''.join(struct.pack('<H', v) for v in items))
    section(b''.join(struct.pack('<hhBB', c[1], c[2], c[3], c[4]) for c in cells))
    section(b''.join(struct.pack('<Bxh', m, h) for m, h in far))
    section(b''.join(struct.pack('<BBBB', *ln) for ln in lines))
    section(b''.join(struct.pack('<HHBB', *t) for t in trees))
    section(struct.pack('<%dH' % len(ctex), *ctex))
    section(b''.join(struct.pack('<16H', *b) for b in btex))
    # per cell: bottom and top (units / 64) of what spans over it, 0 0 for nothing (collision)
    section(b''.join(struct.pack('<bb', decks[i][0] // 64, min(127, decks[i][1] // 64)) if i in decks
                     else b'\0\0' for i in range(N * N)))
    assert len(boxes) <= 2560 and len(lots) <= 2048 and len(ramps) <= 512, 'see SEEN_* in citydraw.c'
    assert len(lines) <= 1024 and len(trees) <= 2048, 'see SEEN_* in citydraw.c'
    header = struct.pack('<4s8I', b'SFW2', len(boxes), len(lots), len(ramps), len(loops), len(items),
                         len(lines), len(trees), 0)
    header += struct.pack('<%dI' % len(parts), *[p + 4 * 9 + 4 * len(parts) for p in parts])
    return header + bytes(blob), dict(boxes=len(boxes), lots=len(lots), ramps=len(ramps), items=len(items),
                                      lines=len(lines), trees=len(trees))


if __name__ == '__main__':
    data, stats = build(open(sys.argv[1], 'rb').read())
    open(sys.argv[2], 'wb').write(data)
    print('world:', stats, len(data), 'bytes')
