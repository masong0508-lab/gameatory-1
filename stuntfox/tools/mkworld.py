"""Builds Stunt Fox's 3D city from the player's own Payback ROM.

Like IW4L reading a game install, nothing from Payback is stored in this repository: the
city layout (roads, kerbs, plazas, building footprints and heights, ramps) is decoded from
the city's level grid at build time and turned into Stunt Fox's own world format.

World units: one Payback cell is 1024 units (about 8 m). X runs with Payback's x, Z with
Payback's y, and Y is up.

Output (little endian), see src/world.h:
    header   'SFW4', counts and offsets
    boxes    buildings: x0 z0 x1 z1 (cells), height (units), material, base (units / 64: 0, or
             the underside of a deck spanning over open air, a bridge)
    lots     ground patches that are not road: x0 z0 x1 z1, material
    ramps    drivable slopes: x0 z0 x1 z1, h0 h1, rising direction, material
    loops    x z (units), direction, radius, width
    lines    road centre lines: at, from, to (cells), dir (0 along z, 1 along x) | crossings << 1
    trees    x z (units / 4), height (units / 8), kind (0 1 trees, 6 bench, 7 bin, 8 lamp: h is its
             turn; 9 drawn by props.c from Payback's live map, only stops cars here), base
             (units / 64), radius (units / 4) cars are stopped at, 0 for none;
             kind 2 + edge: a railing, x z its cell (x | 128: Payback lets you across it from the
             next cell, one way), h and base its bottom (units / 32, s16 as h | base << 8)
    ctex     128 x 128 cells: Payback tile id of the cell's top surface (0xffff: none)
    btex     per box, 4 sides (-z, +x, +z, -x) x 4 cells along it: Payback tile id (0xffff: none)
    sectors  16 x 16 sectors of 8 x 8 cells: index into the item list
    items    u16: kind << 13 | index
    height   128 x 128 cells: s16 low, s16 high, u8 shape, u8 material (collision and minimap)
    far      16 x 16 sectors: material and average height for distant rendering
    deck     128 x 128 cells: s8 bottom, s8 top, s8 top's low end (units / 64 - HBIAS), u8 shape of its
             top (as a cell's) of a deck over the cell, all 0: none
    wall     128 x 128 cells: u8 edges (bits -z, +x, +z, -x) a car in the cell is stopped at;
             then 128 x 128 cells: s8 bottom, s8 top (units / 64 - HBIAS) of those walls
    deck2    128 x 128 cells: a second deck over the first, as deck
    dtex     128 x 128 cells: Payback tile id of the top of the deck over the cell (the higher one
             of two), 0xffff: none (ctex has the floor under it)
    swim     128 x 128 cells: u8 for a man swimming in the water cell, bits 0..3 the edges he climbs
             out across, bit 4 a way out in reach, bit 5 a ladder on an edge, bits 6..7 the edge to
             swim across for the nearest way out; then u16 ladders, u16 0,
             and per ladder u8 x, u8 z (cell), u8 edge, pad, s16 bottom, s16 top (units)
"""
import collections
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
# a cell of Payback's water (src/world.h): drawn at its surface (hi), solid to our physics only at
# lo, WATER_DEEP under it, where Payback has long since lost whatever went in (it sinks a car
# about 3550 units, then wrecks it)
SHAPE_WATER = 6
WATER_DEEP = 4096

K_BOX, K_LOT, K_RAMP, K_LOOP, K_LINE, K_TREE = range(6)
HBIAS = 40                      # deck and wall heights: units / 64 less this (src/world.h)
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


# Payback's street objects: the object type is byte 1 of a floor record, byte 0 turns it (256 a
# turn). Each type's descriptor (OBJ_DESC + type * 0x3c, read from the ROM) has, at -0x14, the
# object's offset from the cell's middle (x, y; turned as 0x08000e10 turns it) and at -0x10 the
# radius of the circle Payback pushes people and cars out of (half of it, plus their own: a man
# standing in one is put table / 2 + 168 from its middle). Payback draws the object there: in the
# emulator a lamp's post stands at its circle, its arm out toward the cell's middle, and a man
# put inside a lamp's or a tree's circle is pushed out. Walking past a lamp he slides round it;
# cars are stopped at nearly all of them (tools/colcheck.py).
OBJ_DESC = 0x353f00
OBJ_SIN, OBJ_COS = 0x666daa, 0x669aaa        # Payback's sine and cosine, 5760 a turn, x 256
# Types 25 and 32 are more trees (25 has 7's descriptor; 32 is a shrub), 33 and 36 lamps (2's).
OBJ_TREES = {7: 800, 5: 650, 8: 450, 25: 800, 32: 450}  # type -> height (units)
OBJ_PROPS = {18: 6, 2: 8, 33: 8, 36: 8}                 # type -> kind: 6 bench, 8 lamp
# Drawn from Payback's live map instead (src/props.c), since missions put them down and take them
# away (a crate opened, a pickup taken) and a ringing phone flips its type: rocks, crates, phones,
# crossing beacons, traffic lights, pickups and the rest. Kind 9 here, at Payback's circle, for
# our car's posts only (car.c, while the live map still has it) and h its height (units / 8,
# from the descriptor)
OBJ_LIVE = {1, 3, 4, 6, 14, 15, 16, 17, 19, 20, 21, 22, 23, 24, 26, 27, 28, 29, 30, 31, 34, 35} | set(range(9, 14))
OBJ_NOCAR = {26}          # (Payback's car goes through these: tools/colcheck.py)
# half the length of a bench, bin, lamp as citydraw.c draws them (a bench as long as Payback's
# descriptor has it, x -280..280): our narrower car is stopped at least there
PROP_HALF = {6: 140, 7: 80, 8: 16}


def street_objects(rom, recs, reach, grid):
    """Trees list entries (x, z (units / 4), h, kind, base (units / 64), radius (units / 4)) for
    Payback's street objects on the floors people or cars get to (reach: per cell {record:
    height}): trees as kind 0/1 (h their height / 8), benches, bins and lamps as kind 6..8 (h
    Payback's turn), what props.c draws as kind 9 (h its height / 8). At their circles, with
    Payback's radius or, wider, what is drawn."""
    global UNDRAWN
    d, out, UNDRAWN = rom.d, [], []
    for i in range(N * N):
        col = rom.column(grid[i])
        for k in range(3):
            # (the trees, benches and lamps on floors nobody gets to are not drawn: props.c
            # hit_cell lets bolts through them)
            if (col[20 * k + 1] in OBJ_TREES or col[20 * k + 1] in OBJ_PROPS) and col[20 * k + 8] and \
                    k not in reach[i]:
                UNDRAWN.append(i << 2 | k)
        if not reach[i]:
            continue
        for k in reach[i]:
            turn, typ = col[20 * k], col[20 * k + 1]
            if typ not in OBJ_TREES and typ not in OBJ_PROPS and typ not in OBJ_LIVE:
                continue
            ox, oy, r = struct.unpack_from('<hhh', d, OBJ_DESC + typ * 0x3c - 0x14)
            a = turn * 5760 // 256
            c, s = struct.unpack_from('<h', d, OBJ_COS + 2 * a)[0], struct.unpack_from('<h', d, OBJ_SIN + 2 * a)[0]
            x, z = divmod(i, N)
            cx = x * CELL + CELL // 2 + ((c * ox + s * oy) >> 9)
            cz = z * CELL + CELL // 2 + ((c * oy - s * ox) >> 9)
            base = max(-128, min(127, (h_units(pb_slope(recs[i][k], 1024, 1024)) + 32) >> 6))
            r = min(255, r // 16)
            if typ in OBJ_TREES:
                # (a crown as wide as Payback's circle, on a trunk tall enough to hold it)
                out.append((cx // 4, cz // 4, max(OBJ_TREES[typ], 8 * r) // 8, typ & 1, base, r))
            elif typ in OBJ_PROPS:
                kind = OBJ_PROPS[typ]
                out.append((cx // 4, cz // 4, turn, kind, base, max(r, PROP_HALF[kind] // 4)))
            else:
                tall = struct.unpack_from('<h', d, OBJ_DESC + typ * 0x3c - 0x2c)[0] // 2
                out.append((cx // 4, cz // 4, min(255, max(tall, 64) // 8), 9, base, 0 if typ in OBJ_NOCAR else r))
    return out


EDGE_STEP = ((0, -1), (1, 0), (0, 1), (-1, 0))         # edge (-z, +x, +z, -x) -> step


# ---- Payback's own collision, for the merged city ----
# Read from Payback's code, which runs these in IWRAM: its floor routine (0x030060f8), its
# layer lookup (0x03005d00) and its edge tests (0x030063ec along x, 0x030065bc along y). Checked
# against Payback itself under an emulator by tools/colcheck.py: on Freedom City this edge rule
# gives Payback's answer for 65037 of 65057 cell edges a man walks across, and for all 17939
# edges a car meets on the streets.
#
# A column is three records stacked from height 0 (0x100 is the street): each as thick as its
# h0 (signed), with a top that runs from its h0 edge to its h1 edge when sloped (shapes 2..5;
# 0 is open air, 1 flat). Type (byte 11 & 0x70): 0 nothing to stand on, 0x40 water (people
# sink in it to its h1), anything else a floor. Its four sides (-y, +x, +y, -x) each have a type
# in bits 12..14: 0 and 5 let people through, 3 is a fence a car breaks, anything else is a wall.
# Heights alone never stop anyone: a man (a car) going into a cell is stopped only by the side
# facing him of the record at his knee (his feet + 0x40), and then stands on the floor nearest
# his feet (never one more than 0x80 above them once there is any).

PB_KNEE = 0x40
KERB = 440 + 38                  # what a car of ours climbs (units), under Payback's knee: physics.c


def pb_records(col):
    """[(base, top0, top1, shape, type, sides, tile)] for the three records, heights in Payback
    steps: top0 at the h0 edge, top1 at the h1 edge."""
    base, out = 0, []
    for k in range(3):
        b = col[20 * k:20 * k + 20]
        h0, h1 = struct.unpack_from('<hh', b, 4)
        out.append((base, base + h0, base + h1, b[8], b[11] & 0x70, struct.unpack_from('<4H', b, 12),
                    b[10] | (b[11] & 3) << 8))
        base += h0
    return out


def pb_layer_at(recs, h):
    """The record a point at height h is in (Payback's 0x03005d00), or -1 above them all."""
    for k, (base, t0, t1, shape, typ, _, _) in enumerate(recs):
        if h <= t0 or (h <= t1 and (shape != 1 or typ == 0x40)):
            return k
    return -1


def pb_blocked(recs, e, h, car=False):
    """Does the column recs stop a man (car) at height h coming into it across its edge e^2,
    i.e. moving along e (0 -y, 1 +x, 2 +y, 3 -x)?"""
    k = pb_layer_at(recs, h + PB_KNEE)
    if k < 0 or not recs[k][3]:
        return False
    return (recs[k][5][e ^ 2] >> 12) & 7 not in ((0, 5, 3) if car else (0, 5))


def pb_slope(rec, fx, fy):
    """Height of a record's top at (fx, fy) in the cell (0..2047 each)."""
    base, t0, t1, shape, typ = rec[:5]
    if typ == 0x40 or shape == 1:
        return t1 if typ == 0x40 else t0
    f = fy if shape in (2, 4) else fx
    return t0 + (f * (t1 - t0) >> 11) if shape in (2, 3) else t1 + (f * (t0 - t1) >> 11)


def pb_floor(recs, fx, fy, h):
    """Payback's floor (0x030060f8) at (fx, fy) for someone with feet at h: (record, height),
    or (None, h) when the column has nothing to stand on."""
    best, out = None, (None, h)
    for k, rec in enumerate(recs):
        base, t0, t1, shape, typ = rec[:5]
        if not shape or not typ:
            continue
        ref = t1 if typ == 0x40 or (shape != 1 and t1 <= t0) else t0
        d = ref - h
        if best is not None and d > 0x80:
            continue
        if abs(d) > (best if best is not None else 1 << 30):
            continue
        best = abs(d) + 0x40
        out = (k, pb_slope(rec, fx, fy))
    return out


PB_ENTRY = ((1024, 2047), (0, 1024), (1024, 0), (2047, 1024))     # where you come in, going along e
PB_EXIT = ((1024, 0), (2047, 1024), (1024, 2047), (0, 1024))
PB_CARMID = ((1024, 1470), (577, 1024), (1024, 577), (1470, 1024))    # a car's middle, its nose there


def pb_reach(cols, lanes, car=False, seeds=()):
    """The floors people (cars) can get to from Payback's streets and pavements by Payback's
    rules: {cell index: {record: height at the cell centre}}, cols: pb_records of each cell,
    lanes: byte 3 of each column. Water is entered but not left. seeds: more floors (cell,
    record, height) to start from (where a swimmer climbs out: swim_table)."""
    seen = {}
    todo = []
    for i, k, h in seeds:
        seen.setdefault(i, {})[k] = h
        todo.append((i, k, h))
    for i in range(N * N):
        if lanes[i] & (0x0f if car else 0x2f):
            k, h = pb_floor(cols[i], 1024, 1024, STREET)
            if k is not None:
                seen.setdefault(i, {})[k] = h
                todo.append((i, k, h))
    while todo:
        i, k, h = todo.pop()
        if cols[i][k][4] == 0x40:
            continue
        x, y = divmod(i, N)
        for e, (dx, dy) in enumerate(EDGE_STEP):
            if not (0 <= x + dx < N and 0 <= y + dy < N):
                continue
            j = (x + dx) * N + y + dy
            he = pb_floor(cols[i], *PB_EXIT[e], h)[1]
            if pb_blocked(cols[j], e, he, car):
                continue
            hin = pb_floor(cols[j], *PB_ENTRY[e], he)[1]
            kj, hj = pb_floor(cols[j], 1024, 1024, hin)
            if kj is not None and kj not in seen.get(j, {}):
                seen.setdefault(j, {})[kj] = hj
                todo.append((j, kj, hj))
    return seen


PB_SWAP = {2: 4, 3: 5, 4: 2, 5: 3}
PB_CLEAR = 0x40                  # headroom left under a deck people walk under (a man's height)
DECK_T = 0x20                    # how thick a slab of a split deck is (Payback's are solid down to the street)


def merged(rom, grid, wet=(), city=None):
    """The merged city from Payback's collision: per cell the floor people and cars use, what
    spans over it, and the cell edges Payback stops them at. Returns (cells, decks, walls,
    tiles, objects, decks2): cells as classify(); decks {cell: (bottom, top, material, tile, top's
    low end, shape of its top as a cell's)} (units), decks2 the same for a second deck over the
    first;
    walls {(cell, edge, level): (bottom, top, to draw, to collide, one way)} (units): the edges
    people in that cell are stopped at, from each floor (level: its height there) they stand on;
    tiles {cell: the floor's tile id}.
    wet: floors a swimmer climbs out onto (swim_table), which people get to from there on foot
    as from the streets (an island's beach); city: the city's cells (city_part)."""
    raw = [rom.column(grid[i]) for i in range(N * N)]
    cols = [pb_records(c) for c in raw]
    lanes = [c[3] for c in raw]
    foot, car = pb_reach(cols, lanes, seeds=wet), pb_reach(cols, lanes, True)
    cells, decks, decks2, tiles, floor, reaches = [], {}, {}, {}, [], []
    def deck_over(over, hi):
        """The floors over (records of cell i, lowest first) as one deck over the floor at hi:
        (bottom, top, material, tile, top's low end, shape), or None."""
        top_rec = recs[over[-1]]
        top = max(max(recs[k][1], recs[k][2]) for k in over)
        dlo, dshape = top, 1
        if len(over) == 1 and top_rec[3] != 1 and top_rec[1] != top_rec[2]:
            # a sloped deck (a ramp up onto a bridge over a yard): its top runs lo..top
            dlo = min(top_rec[1], top_rec[2])
            dshape = top_rec[3] if top_rec[1] <= top_rec[2] else PB_SWAP[top_rec[3]]
        bottom = max(recs[over[0]][0], hi + PB_CLEAR)
        dt = top_rec[6]
        return (h_units(bottom), h_units(top), BUILDING_MATS[((dt & 0xff) * 7 + 3) % len(BUILDING_MATS)], dt,
                h_units(dlo), dshape) if dlo > bottom else None
    for i in range(N * N):
        recs = cols[i]
        reach = {k: h for d in (foot.get(i, {}), car.get(i, {})) for k, h in d.items() if recs[k][4] != 0x40}
        reaches.append(reach)
        floors = [k for k, r in enumerate(recs) if r[3] and r[4] not in (0, 0x40)]
        water = next((k for k, r in enumerate(recs) if r[3] and r[4] == 0x40), None)
        if reach:
            g = min(reach, key=lambda k: reach[k])
        elif floors:
            g = max(floors, key=lambda k: max(recs[k][1], recs[k][2]))
        else:
            g = None
        floor.append(g)
        tex = raw[i][10]
        if g is None and water is None:
            tiles[i] = tex                  # (nothing to stand on at all)
            cells.append(('ground', 0, 0, 1, M_PLAZA))
            continue
        # water under a deck with room to walk in (a pier on its stilts) is water too
        pier = (g is not None and water is not None and water < 2 and not recs[water + 1][3] and min(floors) > water
                and recs[min(floors)][0] >= recs[water][1] + PB_CLEAR and deck_over(floors, recs[water][1]))
        if g is None or pier:
            # water: people and cars go in and sink to its bed. Drawn at its surface (a pool
            # raised over the street is a block of it, open as Payback's is): its top, or the
            # height Payback puts people at going in where that is higher (a ditch Payback has
            # them wade into at street level, not a pit)
            h = max(recs[water][1], recs[water][2])
            tiles[i] = recs[water][6]
            cells.append(('ground' if h == STREET else 'ramp', h_units(h) - WATER_DEEP, h_units(h), SHAPE_WATER,
                          WATER_MAT))
            if pier:
                decks[i] = pier
            continue
        base, t0, t1, shape, typ, _, tile = recs[g]
        tiles[i] = tile
        lo, hi = min(t0, t1), max(t0, t1)
        # what is above: the floors stacked over it, from the first one's underside
        over = [k for k in floors if k > g]

        def slab(k, under):
            """Record k as a deck of its own, a slab DECK_T thick over the floor at under."""
            t0, t1, shape = recs[k][1:4]
            dlo, dshape = max(t0, t1), 1
            if shape != 1 and t0 != t1:
                dlo, dshape = min(t0, t1), (shape if t0 <= t1 else PB_SWAP[shape])
            bottom = max(recs[k][0], under + PB_CLEAR, dlo - DECK_T)
            dt = recs[k][6]
            return (h_units(bottom), h_units(max(t0, t1)), BUILDING_MATS[((dt & 0xff) * 7 + 3) % len(BUILDING_MATS)], dt,
                    h_units(dlo), dshape) if dlo > bottom else None
        d = slab(over[0], hi) if len(over) == 2 and over[0] in reach else None
        if d:
            # three floors people get to, one over another (Little Chicago's walkways over its
            # covered roads, its railway platforms under their roofs): Payback walks you through
            # its solid records, so each floor over the ground is a slab, with headroom under it
            decks[i] = d
            d2 = slab(over[1], max(recs[over[0]][1], recs[over[0]][2]))
            if d2:
                decks2[i] = d2
        elif over:
            d = deck_over(over, hi)
            if d:
                decks[i] = d
        if shape != 1 and lo != hi and (reach or lo <= STREET):
            # (a roof nobody gets onto stays a box at its ridge: the ramps are kept for slopes
            # people and cars use, see SEEN_RAMP in citydraw.c)
            cells.append(('ramp', h_units(lo), h_units(hi), shape if t0 <= t1 else PB_SWAP[shape], M_KERB))
        elif hi > STREET:
            # (its colour from the column's top record, the roof, as before: the floor's tile
            # changes from cell to cell along a building's walls, and split it into boxes whose
            # faces inside it are drawn too)
            roof = next(raw[i][20 * k + 10] for k in (2, 1, 0) if raw[i][20 * k + 8] or k == 0)
            cells.append(('building', h_units(hi), h_units(hi), 1, BUILDING_MATS[(roof * 7 + 3) % len(BUILDING_MATS)]))
        elif hi < STREET:
            cells.append(('ramp', h_units(hi), h_units(hi), 1, M_ROAD if lanes[i] & 0x0f else M_KERB))
        elif lanes[i] & 0x0f:
            cells.append(('road', 0, 0, 1, M_ROAD))
        elif lanes[i] & 0x20:
            cells.append(('kerb', 0, 0, 1, M_KERB))
        else:
            cells.append(('ground', 0, 0, 1, M_GRASS if tex in GRASS_TEX else M_ROAD if tex == 0x2b else M_PLAZA))

    level_pockets(cells)

    # walls: every edge Payback stops someone at, from a floor they can get to. Kept on the side
    # they are stopped on: Payback tests only the cell you go into, so you may well drive off a
    # roof over a parapet you could not come back across.
    corners = (((0, 0), (1, 0)), ((1, 0), (1, 1)), ((0, 1), (1, 1)), ((0, 0), (0, 1)))   # each face's ends

    def face(j, f):
        """The heights of cell j's top at the two ends of its face f."""
        lo, hi, shape = cells[j][1:4]
        ends = []
        for cx, cz in corners[f]:
            rise = {2: cz, 3: cx, 4: 1 - cz, 5: 1 - cx, SHAPE_WATER: 0}.get(shape)
            ends.append(hi if rise is None else lo + (hi - lo) * rise)
        return ends

    def ours_top(j, f, h):
        """What we have along face f of cell j, at height h (units) and just above: the lowest top
        of a solid there (a ramp's lower end)."""
        top = min(face(j, f))
        for d in (decks.get(j), decks2.get(j)):
            if d and d[0] < h + 256 and d[1] > h:
                top = max(top, d[1])
        return top
    walls = {}
    for reachset, is_car in ((foot, False), (car, True)):
        for i, ks in reachset.items():
            x, y = divmod(i, N)
            for k, h in ks.items():
                if cols[i][k][4] == 0x40:
                    continue
                for e, (dx, dy) in enumerate(EDGE_STEP):
                    if not (0 <= x + dx < N and 0 <= y + dy < N):
                        continue
                    j = (x + dx) * N + y + dy
                    he = pb_floor(cols[i], *PB_EXIT[e], h)[1]
                    # (a car is tested at its middle's height when its nose is at the edge: the
                    # top of a steep ramp stops a car where it lets a man by, and so may its foot)
                    hk = pb_floor(cols[i], *PB_CARMID[e], h)[1] if is_car else he
                    if not pb_blocked(cols[j], e, hk, is_car):
                        continue
                    rb = cols[j][pb_layer_at(cols[j], hk + PB_KNEE)]
                    bottom, top = h_units(min(he, hk)), h_units(max(rb[1], rb[2], hk + PB_KNEE))
                    rise = ours_top(j, e ^ 2, bottom) - bottom
                    # drawn unless a solid of ours is there to see; in our physics where the car
                    # would get over what we have there (physics.c climbs under KERB, and up any
                    # ramp: ramp_grip; off a ramp along the edge, from where it is highest)
                    low = ours_top(j, e ^ 2, bottom) - max([bottom] + face(i, e)) if 2 <= cells[i][3] <= 5 else rise
                    draw, phys = rise < 96, is_car and (min(rise, low) <= KERB or 2 <= cells[j][3] <= 5)
                    if not (draw or phys):
                        continue
                    old = walls.get((i, e, bottom))
                    if old:
                        draw, phys = draw or old[2], phys or old[3]
                        top = max(old[1], top)
                    walls[(i, e, bottom)] = (bottom, top, draw, phys, 0)
    # one way: Payback stops you at it from this side only, and you get to a floor just across it
    # (drawn open from there: draw_fence)
    blocks = collections.defaultdict(list)
    for (i, e, bottom) in walls:
        blocks[(i, e)].append(bottom)
    for (i, e, bottom), w in walls.items():
        x, y = divmod(i, N)
        j = (x + EDGE_STEP[e][0]) * N + y + EDGE_STEP[e][1]
        across = [h_units(h) for d in (foot.get(j, {}), car.get(j, {})) for h in d.values()]
        if any(abs(h - bottom) < 256 for h in across) and not any(abs(b - bottom) < 256 for b in blocks[(j, e ^ 2)]):
            walls[(i, e, bottom)] = w[:4] + (1,)
    city = city or city_part(cells, decks, set(foot) | set(car))
    swim = swim_table(cells, decks, decks2, walls, foot, car, cols, face, city)
    more = [s for s in swim[3] if s[1] not in foot.get(s[0], {})]
    if more and len(wet) < 4096:
        # banks a swimmer gets out onto that nobody walks to from the streets: again, with
        # Payback's people (and walls) on them and on whatever they lead to
        return merged(rom, grid, tuple(wet) + tuple(more), city)
    return cells, decks, walls, tiles, street_objects(rom, cols, reaches, grid), decks2, swim[:3]


# ---- swimming (src/merge.c): Payback's man floats in its water and swims; where he gets out ----
CLIMB = 256                      # a bank he climbs out onto: up to about his own height over the water
DROP = 512                       # ... or down onto, no further (a longer fall hurts in Payback)
SWIM_ROOM = 256                  # room he needs over the water under a deck, and over a bank to stand up
LADDER_GAP = 16                  # where ladders go: no swim to the nearest way out much longer than this (cells)
LADDER_MAX = 4096                # the highest bank a ladder goes up (units)


def city_part(cells, decks, reached):
    """The city: the cells people get to from its streets (reached), joined cell to cell over land
    and bridges, but not a part of under 256 cells (an island in the sea with its own paths)."""
    dry = {i for i in reached if cells[i][3] != SHAPE_WATER or i in decks}
    city, seen = set(), set()
    for s in dry:
        if s in seen:
            continue
        part, todo = [s], [s]
        seen.add(s)
        while todo:
            x, y = divmod(todo.pop(), N)
            for dx, dy in EDGE_STEP:
                j = (x + dx) * N + y + dy
                if 0 <= x + dx < N and 0 <= y + dy < N and j in dry and j not in seen:
                    seen.add(j)
                    part.append(j)
                    todo.append(j)
        if len(part) >= 256:
            city |= set(part)
    return city


def level_pockets(cells):
    """A few water cells lower than all the water round them (between a bridge's piers, where
    Payback's water is shallower): level with the lowest of it, as water would be, so a swimmer
    who goes in gets back out."""
    W = [c[3] == SHAPE_WATER for c in cells]
    seen = set()
    for s in range(N * N):
        if not W[s] or s in seen:
            continue
        comp, todo, rim = [s], [s], []
        seen.add(s)
        while todo:
            a = todo.pop()
            x, y = divmod(a, N)
            for dx, dy in EDGE_STEP:
                if 0 <= x + dx < N and 0 <= y + dy < N:
                    b = (x + dx) * N + y + dy
                    if W[b] and cells[b][2] == cells[s][2]:
                        if b not in seen:
                            seen.add(b)
                            comp.append(b)
                            todo.append(b)
                    elif W[b]:
                        rim.append(cells[b][2])
        if len(comp) <= 8 and rim and min(rim) > cells[s][2]:
            for a in comp:
                cells[a] = ('ground' if min(rim) == 0 else 'ramp', min(rim) - WATER_DEEP, min(rim)) + cells[a][3:]


def swim_table(cells, decks, decks2, walls, foot, car, cols, face, city):
    """For the swimmer (merge.c): per cell, bits 0..3 the edges (-z, +x, +z, -x) a man in this
    water cell climbs out across (a bank in reach of the streets, at most CLIMB over the water or
    DROP under it where he crosses the edge, with no railing drawn on it and room to stand up),
    bit 4 a way out in reach swimming from here, bit 5 a ladder on one of its edges, bits 6..7
    the edge to swim across for the nearest way out (that way out's own edge in a cell that has
    one) into the city (city_part), an island's beach only where there is none. Ladders [(cell,
    edge, the water's surface, the bank's top)] (units) go up higher banks where water people
    can get into has no way out in reach, or only a long swim away (into the city, and onto a
    bank with room at its top). Where he can get into the water and not out, and nothing of ours shows
    it (the bank falls away under the water, or nobody can stand there), a railing goes along
    the water's edge (walls). Also a report of each body of water, and the floors a swimmer gets
    out onto that nobody walks to from the streets (merged() goes again from them)."""
    # (Payback keeps everyone two cells in from the map's edge)
    W = [c[3] == SHAPE_WATER and 2 <= i // N < N - 2 and 2 <= i % N < N - 2 for i, c in enumerate(cells)]
    surf = [c[2] for c in cells]
    rails = collections.defaultdict(list)
    for (i, e, b), w in walls.items():
        if w[2]:
            rails[(i, e)].append(b)
    land = set(foot) | set(car)

    def step(i, e):
        x, y = divmod(i, N)
        x, y = x + EDGE_STEP[e][0], y + EDGE_STEP[e][1]
        return x * N + y if 2 <= x < N - 2 and 2 <= y < N - 2 else None

    def railed(i, e, h):
        """A railing drawn on edge e of cell i (from either side) about at height h?"""
        j = step(i, e)
        return any(abs(b - h) < 256 for b in rails[(i, e)] + (rails[(j, e ^ 2)] if j is not None else []))

    def bank(i, e, most=CLIMB, part=0):
        """The bank across edge e of water cell i: (its height at the edge's middle, ok to climb
        onto (up to most over the water) along part of it at least, or anywhere along it)."""
        j = step(i, e)
        if j is None or W[j] or j not in land:
            return None, False
        ends = face(j, e ^ 2)
        top, hi = (ends[0] + ends[1]) // 2, max(ends)
        # (a bank sloping along the water is climbed where it is low enough: merge.c tests where
        # he crosses)
        a, b = ends[0] - surf[i], ends[1] - surf[i]
        if a == b:
            ok = -DROP <= a <= most
        else:
            t0, t1 = sorted(((-DROP - a) / (b - a), (most - a) / (b - a)))
            ok = min(t1, 1) - max(t0, 0) >= part and t1 >= 0 and t0 <= 1
        ok = ok and not railed(i, e, top)
        for d in (decks.get(j), decks2.get(j)):
            ok = ok and not (d and d[0] < hi + SWIM_ROOM and d[1] > top - 64)
        return top, ok

    def room(i, e, top):
        """Somewhere to walk on from the bank (a floor at about its height further in, not the
        water again, nor a ledge a cell wide)."""
        j = step(i, e)
        k = step(j, e) if j is not None else None
        if k is None or W[k] or cells[k][3] == SHAPE_WATER or k not in land:
            return False
        return all(abs(h - top) <= CLIMB for h in face(k, e ^ 2))

    def swims(i, j):
        """Can he swim from water cell i into the next one, j? (up a little, down any way, and
        under a deck with room over the water)"""
        if j is None or not W[j] or surf[j] - surf[i] > CLIMB:
            return False
        return not any(d and d[0] < surf[j] + SWIM_ROOM and d[1] > surf[j] for d in (decks.get(j), decks2.get(j)))
    out, wide = [0] * (N * N), [0] * (N * N)
    for i in range(N * N):
        if W[i]:
            for e in range(4):
                if bank(i, e)[1]:
                    out[i] |= 1 << e
                    # (a way out to swim to, and to point to: along a quarter of the edge at least)
                    wide[i] |= bank(i, e, CLIMB, 0.25)[1] << e
    # where people get in: from a floor in reach, across an edge Payback lets them over
    entry = set()
    for reachset, is_car in ((foot, False), (car, True)):
        for j, ks in reachset.items():
            for k, h in ks.items():
                if cols[j][k][4] == 0x40:
                    if W[j]:
                        entry.add(j)
                    continue
                for e in range(4):
                    i = step(j, e)
                    if i is not None and W[i] and not pb_blocked(cols[i], e, pb_floor(cols[j], *PB_EXIT[e], h)[1], is_car):
                        entry.add(i)

    def way_out(ladders, toward=None, streets=False):
        """Swimming distance (cells) to the nearest way out (streets: into the city), for every
        water cell that has one (toward: the edge to swim across for it, in each)."""
        dist, todo, lad = {}, collections.deque(), {l[:2] for l in ladders}
        for i in range(N * N):
            ways = [e for e in range(4) if (wide[i] >> e & 1 or (i, e) in lad) and (not streets or step(i, e) in city)]
            if ways:
                dist[i] = 0
                todo.append(i)
                if toward is not None:
                    toward[i] = ways[0]
        while todo:
            i = todo.popleft()
            for e in range(4):
                j = step(i, e)
                if j is not None and j not in dist and swims(j, i):
                    dist[j] = dist[i] + 1
                    todo.append(j)
                    if toward is not None:
                        toward[j] = e ^ 2
        return dist

    def ahead(i):
        """Water cells he swims to from i, by distance."""
        seen, todo = {i: 0}, collections.deque([i])
        while todo:
            a = todo.popleft()
            for e in range(4):
                b = step(a, e)
                if b is not None and b not in seen and swims(a, b):
                    seen[b] = seen[a] + 1
                    todo.append(b)
        return seen
    entered = set()
    for i in entry:
        if i not in entered:
            entered |= set(ahead(i))
    # floors a swimmer gets out onto that are not in reach of the streets (an island's low
    # beach): Payback's floor there, as it has a man come in at the water's surface
    seeds = []
    for i in sorted(entered):
        hs = surf[i] // 8 + STREET
        for e in range(4):
            j = step(i, e)
            if j is None or W[j] or cells[j][3] == SHAPE_WATER or j in land or pb_blocked(cols[j], e, hs):
                continue
            hin = pb_floor(cols[j], *PB_ENTRY[e], hs)[1]
            k, h = pb_floor(cols[j], 1024, 1024, hin)
            if k is not None and cols[j][k][4] not in (0, 0x40) and -DROP <= h_units(hin) - surf[i] <= CLIMB:
                seeds.append((j, k, h))
    # ladders: first where people can get in but find no way out, then where the nearest way out
    # into the city (not an island's beach) is a long swim and a bank much nearer can take one,
    # with room to walk on at its top (a floor on beyond it, not a wall a cell thick)
    ladders = []
    for streets in (False, True) if city else (False,):
        def fit(i, e):
            top, ok = bank(i, e, LADDER_MAX)
            return ok and (not streets or step(i, e) in city and room(i, e, top)), top
        cand = [(i, e) for i in range(N * N) if W[i] for e in range(4) if fit(i, e)[0]]
        near, todo = {}, collections.deque()
        for i, e in cand:
            if i not in near:
                near[i] = 0
                todo.append(i)
        while todo:                    # swimming distance to the nearest bank a ladder can go up
            i = todo.popleft()
            for e in range(4):
                j = step(i, e)
                if j is not None and j not in near and swims(j, i):
                    near[j] = near[i] + 1
                    todo.append(j)
        while len(ladders) < 48:
            dist = way_out(ladders, streets=streets)
            need = [i for i in entered if i in near and dist.get(i, 1 << 20) > max(LADDER_GAP, near[i] + LADDER_GAP // 2)]
            if not need:
                break
            f = max(need, key=lambda i: (dist.get(i, 1 << 20), -i))
            # the nearest bank swimming from there, the lowest of those about as near (a ladder up
            # a quay, a wall or a beach's edge), one with room to walk on at its top before one without
            best = None
            for i, d in ahead(f).items():
                for e in range(4):
                    ok, top = fit(i, e)
                    if ok and (i, e) not in [(l[0], l[1]) for l in ladders]:
                        key = (d // 6, not room(i, e, top), (top - surf[i]) // 256, d, i, e)
                        if best is None or key < best[0]:
                            best = (key, i, e, top)
            _, i, e, top = best
            ladders.append((i, e, surf[i], top))
    toward = {}
    dist = way_out(ladders, toward)
    home = way_out(ladders, toward, True)      # (the arrow: back to the streets, not onto an island)
    for i in range(N * N):
        if W[i] and i in dist:
            out[i] |= 16 | toward[i] << 6
    for i, e, _, _ in ladders:
        out[i] |= 32
    # no way out across an edge, and nothing to show it: the land beyond falls away under the
    # water (or is a floor nobody stands on): a railing along the water's edge
    lad = {(l[0], l[1]) for l in ladders}
    for i in range(N * N):
        if not W[i] or not (i in entered or out[i] & 16):
            continue
        for e in range(4):
            j = step(i, e)
            if j is None or W[j] or out[i] >> e & 1 or (i, e) in lad or cells[j][3] == SHAPE_WATER:
                continue
            ends = face(j, e ^ 2)
            if min(ends) - surf[i] > CLIMB or railed(i, e, surf[i]):
                continue                   # (a bank too high to climb is a wall we draw)
            if any(d and d[0] < max(ends) + SWIM_ROOM and d[1] > surf[i] for d in (decks.get(j), decks2.get(j))):
                continue                   # (a deck low over it, drawn)
            walls[(i, e, surf[i])] = (surf[i], surf[i] + 256, True, False, 0)
    # the report: each body of water (water cells joined by swimming either way)
    seen, report = set(), []
    for s in range(N * N):
        if not W[s] or s in seen:
            continue
        comp, todo = [], [s]
        seen.add(s)
        while todo:
            a = todo.pop()
            comp.append(a)
            for e in range(4):
                b = step(a, e)
                if b is not None and W[b] and b not in seen and (swims(a, b) or swims(b, a)):
                    seen.add(b)
                    todo.append(b)
        cs = set(comp)
        report.append(dict(cells=len(comp), at=divmod(s, N), surface=surf[s],
                           entered=len(cs & entered), banks=sum(bin(out[i] & 15).count('1') for i in comp),
                           ladders=[(divmod(l[0], N), l[1], l[3] - l[2]) for l in ladders if l[0] in cs],
                           stuck=len([i for i in cs & entered if i not in dist]),
                           no_way_out=len([i for i in comp if i not in dist]),
                           farthest=max([dist[i] for i in cs & entered if i in dist] or [0]),
                           to_streets=max([home.get(i, 999) for i in cs & entered] or [0])))
    return out, ladders, report, seeds


def classify(rom, grid):
    """Per cell: (kind, low, high, shape, material). kind: road, kerb, ground, ramp, building."""
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


def centre_lines(rom, cells, grid):
    """Dashed lines between a road's two opposite lanes (Payback marks each road cell with its
    traffic directions: 1 / 4 for the two lanes along y, 2 / 8 along x). Runs of at most 16
    cells. A run that ends at a junction gets a zebra crossing there."""
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
            out.append(((x * CELL + ox) // 4, (y * CELL + oy) // 4, 60 + (h >> 9) % 40, (h >> 3) & 1, 0, 0))
    return out


# Payback's 32 x 32 tiles: ids below TILE_IDS index a bank in ROM. Only ids are stored here;
# the game finds the tiles through Payback's own table at run time.
TILE_BANK = 0x0ce0bc
TILE_IDS = 0x318
# Payback's water: tile id 0x311 is not a picture in the bank (its renderer skips it there and
# draws its own water image instead), so water cells get an id of their own, one no map uses,
# which merge.c points at that image (see TEX_WATER in src/tex.h)
WATER_TILE = 0x311
TEX_WATER = 0x317


def tile_ok(rom_bytes, tid, most=0x100):
    """A tile that is not mostly see-through (colour 0): railings and fences are left out."""
    if tid >= TILE_IDS:
        return False
    a = TILE_BANK + tid * 0x400
    return rom_bytes[a:a + 0x400].count(0) < most


def recs_of(col):
    """(top, tile, side tiles) of each record of a column. The records stack, each h0 thick: the
    top record is the highest, not the thickest (the deck of Freedom City's river bridge, 192
    over 384 of water, took the water's tile)."""
    out, base = [], 0
    for k in range(3):
        b = col[20 * k:20 * k + 20]
        h0, h1, shape = struct.unpack_from('<HHB', b, 4)
        if shape:
            out.append((base + max(h0, h1), b[10] | (b[11] & 3) << 8, struct.unpack_from('<4H', b, 12)))
        base += h0
    return out


def tex_tables(rom, rom_bytes, cells, boxes, grid, merge=False, decks=None, tiles=None, decks2=None):
    """Tile ids for the top of every cell, for the walls of every box and for the top of the deck
    over every cell. tiles: the floor's tile of each cell (merged())."""
    cols = [recs_of(rom.column(grid[i])) for i in range(N * N)]
    x0, y0, x1, y1 = STADIUM if not merge else (0, 0, 0, 0)
    water = WATER_TILE if merge else -1     # (only merge.c knows where Payback's water is)
    decks = decks or {}
    ctex = []
    for i in range(N * N):
        x, y = divmod(i, N)
        tid = 0xffff
        if merge and cells[i][3] == SHAPE_WATER and not (i in decks and decks[i][1] <= 256):
            tid = TEX_WATER                     # (whatever tile Payback gave it: it is water)
        elif merge and (i in decks or cells[i][0] == 'ramp'):
            # a ramp, the road under a bridge or a sunken floor: its own tile, unless a deck at
            # street level covers it (then that is the street people walk on)
            t = decks[i][3] if i in decks and decks[i][1] <= 256 else tiles[i]
            if t == water:
                tid = TEX_WATER
            elif tile_ok(rom_bytes, t):
                tid = t
        elif merge and cells[i][4] == WATER_MAT and cells[i][0] == 'ground':
            tid = TEX_WATER
        elif cols[i] and not (x0 <= x < x1 and y0 <= y < y1) and cells[i][0] != 'ramp':
            top = max(cols[i], key=lambda r: r[0])
            if top[1] == water:
                tid = TEX_WATER
            elif top[0] < 0x8000 and tile_ok(rom_bytes, top[1]):
                tid = top[1]
        ctex.append(tid)

    def side(i, s):
        for h, _, sides in sorted(cols[i], key=lambda r: -r[0]):
            t = sides[s] & 0x3ff
            if t == water:
                return TEX_WATER
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
    # a deck's top: its own tile (a car park's roof, a railway's track), the higher deck's where
    # there are two
    dtex = []
    for i in range(N * N):
        d = (decks2 or {}).get(i) or decks.get(i)
        t = d[3] if d else -1
        dtex.append(TEX_WATER if d and t == water else t if d and tile_ok(rom_bytes, t) else 0xffff)
    return ctex, btex, dtex


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


def street_level(rom, grid):
    """The height Payback's roads run at: 0x100 on every map but Little Chicago (level 4), whose
    ground is at 0 (with its elevated railway at 0x280)."""
    c = collections.Counter(pb_floor(pb_records(rom.column(g)), 1024, 1024, 0x100)[1] for g in grid
                            if rom.column(g)[3] & 15)
    return c.most_common(1)[0][0] if c else 0x100


def build(rom_bytes, merge=False, level=0, rom=None, limits=True):
    """merge: for Stunt Fox inside Payback, where Payback's own collision decides where people
    walk, so the city is drawn exactly as Payback has it (its stadium, not the stunt arena).
    level: which of Payback's 11 level grids; rom: a PaybackRom whose grids may be repainted.
    limits: fail on more than citydraw.c can draw (tools/colcheck.py, which only collides, needs
    no drawing)."""
    global STREET
    rom = rom or PaybackRom(rom_bytes)
    grid = rom.painted.get(level) or rom.grid(level)
    STREET = street_level(rom, grid)
    yoff = (0x100 - STREET) * 8         # (Payback's heights are from 0x100: see world.h)
    decks, decks2, walls, tiles, swim = {}, {}, {}, None, ([0] * (N * N), [], [])
    global UNDRAWN
    UNDRAWN = []
    if merge:
        cells, decks, walls, tiles, objs, decks2, swim = merged(rom, grid)
    else:
        cells = classify(rom, grid)
        stunt_park(cells)

    boxes = greedy(cells, lambda i: (cells[i][2], cells[i][4], 0) if cells[i][0] == 'building' else None, 4)
    # what spans over open air (bridge decks, walkways, buildings over a road): boxes with a base
    for dd in (decks, decks2):
        boxes += greedy(cells, lambda i: (dd[i][4], dd[i][2], dd[i][0]) if i in dd else None, 4)
    lots = greedy(cells, lambda i: cells[i][4] if cells[i][0] in ('ground', 'kerb') and cells[i][4] != M_ROAD
                  else None, 16)
    # (water below the street: a flat floor at its surface)
    ramps = greedy(cells, lambda i: ((cells[i][2], cells[i][2], 1, cells[i][4]) if cells[i][3] == SHAPE_WATER
                                     else cells[i][1:5]) if cells[i][0] == 'ramp' else None, 8)
    # a sloped deck's top: a ramp on its box, sides from its low end (dir | 0x80, citydraw.c)
    for dd in (decks, decks2):
        ramps += greedy(cells, lambda i: (dd[i][4], dd[i][1], dd[i][5] | 0x80, dd[i][2])
                        if i in dd and dd[i][5] != 1 else None, 8)
    # loops: (x, z) of the entry point in units, direction (0 +z, 1 +x, 2 -z, 3 -x), radius, width
    # (Freedom City's, in its stadium)
    loops = [(60 * CELL, int(36.5 * CELL), 1, 2560, 1536)] if level == 0 else []
    lines = centre_lines(rom, cells, grid)
    if merge:
        # Payback's walls and railings along cell edges (merged()) at the height of the floor
        # they stand on (units / 32), its trees, benches, bins and lamps (citydraw.c draw_tree)
        # (a one-way railing is drawn from the cell it stops you in: draw_fence draws it open
        # from across)
        trees, drawn = [], set()
        for (i, e, _), (bottom, top, draw, phys, oneway) in sorted(walls.items()):
            x, y = divmod(i, N)
            j = (x + EDGE_STEP[e][0]) * N + y + EDGE_STEP[e][1]
            key = (min(i, j), e & 1, (bottom + 64) >> 7)
            if draw and key not in drawn:
                drawn.add(key)
                b32 = max(-0x8000, min(0x7fff, bottom >> 5))         # (RAIL_BASE in world.h)
                trees.append((x | oneway << 7, y, b32 & 0xff, 2 + e, b32 >> 8, 0))
        trees += objs
    else:
        trees = park_trees(cells)
    ctex, btex, dtex = tex_tables(rom, rom_bytes, cells, boxes, grid, merge, decks, tiles, decks2)

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
    # (trees after boxes, lots, ramps and lines, and only loops after them: car.c's car_posts
    # reads a sector's trees from the end)
    for i, (x, z, h, k, *_) in enumerate(trees):
        if 2 <= k < 6:      # a fence: cell x (low 7 bits; the tile above), cell z
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
                M_GRASS if sum(c[4] == M_GRASS for c in hs) > 32 else \
                WATER_MAT if sum(c[4] == WATER_MAT for c in hs) > 32 else M_ROAD
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
    # (then, inside Payback, the street objects of the world data's kinds it leaves out, as cell << 2
    # | record, sorted: a count and the list; props.c hit_cell)
    section(b''.join(struct.pack('<HHBBbB', *t) for t in trees) +
            (struct.pack('<H%dH' % len(UNDRAWN), len(UNDRAWN), *UNDRAWN) if merge else b''))
    section(struct.pack('<%dH' % len(ctex), *ctex))
    section(b''.join(struct.pack('<16H', *b) for b in btex))
    # per cell: bottom and top (units / 64) of what spans over it, its top's low end and shape
    # (as a cell's), 0 0 0 0 for nothing (collision)
    hb = lambda v: max(-128, min(127, v // 64 - HBIAS))      # (world.h)
    deck = lambda dd: b''.join(struct.pack('<bbbB', hb(dd[i][0]), hb(dd[i][1]), hb(dd[i][4]), dd[i][5]) if i in dd
                               else bytes(4) for i in range(N * N))
    section(deck(decks))
    # per cell: the edges (bits -z, +x, +z, -x) a car in it is stopped at, then their bottom and
    # top (units / 64), for physics.c
    wb, wr = bytearray(N * N), {}
    for (i, e, _), (bottom, top, draw, phys, _) in walls.items():
        if phys:
            wb[i] |= 1 << e
            lo, hi = wr.get(i, (bottom, top))
            wr[i] = (min(lo, bottom), max(hi, top))
    rng = lambda c: (hb(wr[c][0]), hb(-(-wr[c][1] // 64) * 64)) if c in wr else (0, 0)
    # (and in the top 4 bits, the edges with a railing drawn along them, from either side: the
    # Arwing meets what is drawn, so physics.c rail_on looks only where one is marked)
    if merge:
        for t in trees:
            if 2 <= t[3] <= 5:
                x, y, e = t[0] & 127, t[1], t[3] - 2
                wb[x * N + y] |= 16 << e
                ax, ay = x + EDGE_STEP[e][0], y + EDGE_STEP[e][1]
                if 0 <= ax < N and 0 <= ay < N:
                    wb[ax * N + ay] |= 16 << (e ^ 2)
    section(bytes(wb) + b''.join(struct.pack('<bb', *rng(c)) for c in range(N * N)))
    # per cell: a second deck over the first, as the first (physics.c)
    section(deck(decks2))
    # per cell: the tile of the top of the deck over it (citydraw.c draw_box, tex.c)
    section(struct.pack('<%dH' % len(dtex), *dtex))
    # per cell: where a swimmer gets out of Payback's water (swim_table), then the ladders as
    # cell x, z, edge, and their bottom and top (units) (merge.c)
    sw, lad, _ = swim
    section(bytes(sw) + struct.pack('<HH', len(lad), 0) +
            b''.join(struct.pack('<BBBxhh', i // N, i % N, e, lo, hi) for i, e, lo, hi in lad))
    counts = 'boxes %d lots %d ramps %d lines %d trees %d' % (len(boxes), len(lots), len(ramps), len(lines), len(trees))
    assert not limits or len(boxes) <= 3072 and len(lots) <= 1536 and len(ramps) <= 1024, 'see SEEN_* in citydraw.c: ' + counts
    assert not limits or len(lines) <= 256 and len(trees) <= 2304, 'see SEEN_* in citydraw.c: ' + counts
    header = struct.pack('<4s7Ii', b'SFW4', len(boxes), len(lots), len(ramps), len(loops), len(items),
                         len(lines), len(trees), yoff)
    header += struct.pack('<%dI' % len(parts), *[p + 4 * 9 + 4 * len(parts) for p in parts])
    return header + bytes(blob), dict(boxes=len(boxes), lots=len(lots), ramps=len(ramps), items=len(items),
                                      lines=len(lines), trees=len(trees), yoff=yoff, ladders=len(swim[1]))


if __name__ == '__main__':
    # rom out [level]: with a level, that map's world for Stunt Fox inside Payback
    lv = int(sys.argv[3]) if len(sys.argv) > 3 else None
    data, stats = build(open(sys.argv[1], 'rb').read(), merge=lv is not None, level=lv or 0)
    open(sys.argv[2], 'wb').write(data)
    print('world:', stats, len(data), 'bytes')
