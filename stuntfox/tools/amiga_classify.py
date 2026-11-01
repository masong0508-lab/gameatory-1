"""Classifies the cells of Payback's city maps from the player's own Amiga copy of the game.

Nothing of the Amiga game is kept: this reads its files from a folder the player names (--amiga DIR) at build
time, like the Payback ROM, and tools/mkworld.py uses what it says to draw water and bridges as the Amiga game does.
Without the folder the build is what it always was.

The Amiga maps are Payback's maps cell for cell: GBA grids 0, 1 and 2 are its maps/0, 1 and 2 and grid 3 is its
usermap "The Killing Zone"; and a cell's number is the same too (row * 128 + column in the file is the grid's
x * 128 + y). A map file is 128 x 128 squares of three stacked cubes (big endian: a mask byte, then per cube a
2 byte height for an invisible one, or an 8 or 16 byte record: slope in the top 3 bits of byte 0, the thickness at
its two ends as bytes 4 and 5 (x 16), and six face words: top, north, east, south, west). A face word's low 12
bits are a line of cubetextures/.CubeTextureList, whose first number is the texture's class (65 water, 36 sand, 50
snow, 52 ice) and whose name says the rest (Road, Bridge, Roof, ...). The heights are in Payback's own steps
(the column records' thicknesses): a water cube's top is the water's surface.

What it finds, per cell (flags):
  WATER   a visible cube with water on top: the surface at water_top
  DECK    a road or bridge top on a cube over a hollow: an invisible cube (the Amiga game draws nothing under it)
          or a water cube with no sides. A bridge, a viaduct or a raised road, open underneath.
          deck_under says what is under it: UNDER_WATER (the span is joined to water) or UNDER_GROUND
  RAMP    a visible sloped top (a slope record)
  ROOF    a top that is a roof
  ROAD    a top that is a road, a crossing or a pavement

Usage:  amiga_classify.py --amiga DIR [--grid G ...] [--out DIR]   (a report, and per grid a json of the flags)
"""
import argparse
import json
import os
import struct
import sys

N = 128
WATER, DECK, RAMP, ROOF, ROAD = 1, 2, 4, 8, 16
UNDER_GROUND, UNDER_WATER = 0, 1
WATER_CLASS = 65
MAPS = {0: 'maps/0.map', 1: 'maps/1.map', 2: 'maps/2.map', 3: 'usermaps/The Killing Zone.map'}
ROADISH = ('Road', 'Bridge', 'Cross', 'Pavement', 'Paving', 'Junction', 'Arrow', 'Kerb', 'Giveway', 'Gutter')
GROUND = 256                          # the street's level: a cube's top is a span's underside only over this
HOLLOW_MIN = 128                      # a road this far over the street, on an invisible cube, is a span (lower is its ramp)


def load_textures(root):
    """[(class, name)] by line of cubetextures/.CubeTextureList (0 based)."""
    out = []
    for ln in open(os.path.join(root, 'cubetextures', '.CubeTextureList'), 'rb').read().decode('latin1').split('\n'):
        ln = ln.strip('\r')
        if ln.strip():
            a, _, b = ln.partition(' ')
            out.append((int(a), b.replace('.chunky', '')))
    return out


def parse_map(path):
    """Squares as [row * 128 + col] -> three cubes (kind 0 invisible, 1 sides off, 2 sides on; slope 0..5; h1, h2;
    the top face word). Fails unless the file is used to its last byte."""
    b = open(path, 'rb').read()
    if b[0] != 0xff:
        raise ValueError('%s: not an Amiga map' % path)
    p, sq = 13, []
    for _ in range(N * N):
        mask, p, cubes = b[p], p + 1, []
        for c in range(3):
            kind = mask >> (2 * c) & 3
            if kind == 0:
                h = struct.unpack_from('>h', b, p)[0]
                p += 2
                cubes.append((0, 0, h, h, 0))
            elif kind in (1, 2):
                n = 8 if kind == 1 else 16
                r = b[p:p + n]
                p += n
                sb = lambda v: (v - 256 if v > 127 else v) * 16
                cubes.append((kind, r[0] >> 5, sb(r[4]), sb(r[5]), r[6] << 8 | r[7]))
            else:
                raise ValueError('%s: bad square mask' % path)
        sq.append(cubes)
    if p != len(b):
        raise ValueError('%s: %d bytes left over' % (path, len(b) - p))
    return sq


def classify(root, grid):
    """{'flags': [N*N], 'water_top': [N*N], 'under': [N*N]} for GBA grid 0..3 (None for the others, which the Amiga copy
    does not have)."""
    if grid not in MAPS:
        return None
    tex = load_textures(root)
    sq = parse_map(os.path.join(root, MAPS[grid]))
    top = lambda cu: tex[cu[4] & 0xfff] if cu[4] >> 12 & 7 and (cu[4] & 0xfff) < len(tex) else None
    flags, wtop = [0] * (N * N), [0] * (N * N)
    for i, cubes in enumerate(sq):
        base, tops = 0, []
        for k, cu in enumerate(cubes):
            kind, slope, h1, h2, _ = cu
            thick = max(h1, h2) if slope >= 2 else h1
            t = top(cu) if slope else None
            tops.append(base + thick)
            if t:
                if t[0] == WATER_CLASS:
                    flags[i] |= WATER
                    wtop[i] = base + thick
                if slope >= 2:
                    flags[i] |= RAMP
                if 'Roof' in t[1]:
                    flags[i] |= ROOF
                if any(w in t[1] for w in ROADISH):
                    flags[i] |= ROAD
            base += thick
        # a road on a hollow: the cube under the topmost visible one is invisible (or a water cube with no sides)
        vis = [k for k in (1, 2) if cubes[k][1] and top(cubes[k])]
        if vis:
            k = vis[-1]
            under = cubes[k - 1]
            hollow = under[0] == 0 and tops[k - 1] >= GROUND + HOLLOW_MIN
            wet = under[0] == 1 and under[1] and top(under) and top(under)[0] == WATER_CLASS
            tk = top(cubes[k])
            if (hollow or wet) and any(w in tk[1] for w in ROADISH) and 'Roof' not in tk[1]:
                flags[i] |= DECK
                if wet:
                    flags[i] |= WATER
                    wtop[i] = tops[k - 1]
    # what a span is over: water when it is joined (4 neighbours, through the span) to a water cell that is no span
    under = [UNDER_GROUND] * (N * N)
    seen = set()
    for s in range(N * N):
        if not flags[s] & DECK or s in seen:
            continue
        comp, todo, wet = [], [s], False
        seen.add(s)
        while todo:
            c = todo.pop()
            comp.append(c)
            r, q = divmod(c, N)
            for dr, dq in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nq = r + dr, q + dq
                if not (0 <= nr < N and 0 <= nq < N):
                    continue
                j = nr * N + nq
                if flags[j] & DECK:
                    if j not in seen:
                        seen.add(j)
                        todo.append(j)
                elif flags[j] & WATER:
                    wet = True
        if wet:
            for c in comp:
                under[c] = UNDER_WATER
    return dict(flags=flags, water_top=wtop, under=under)


def surface_near(info, i):
    """The water's surface (steps) round cell i: the commonest top of the water cells (not spans) next to it, or None."""
    r, q = divmod(i, N)
    tops = [info['water_top'][j] for dr in (-1, 0, 1) for dq in (-1, 0, 1) if (dr or dq) and 0 <= r + dr < N and 0 <= q + dq < N
            for j in ((r + dr) * N + q + dq,) if info['flags'][j] & WATER and not info['flags'][j] & DECK]
    return max(set(tops), key=tops.count) if tops else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--amiga', required=True, help="the folder of the player's Amiga Payback (the one with maps/)")
    ap.add_argument('--grid', type=int, action='append', help='GBA grid 0..3 (default all four)')
    ap.add_argument('--out', help='a folder for gridN.json (flags per cell)')
    a = ap.parse_args()
    for g in a.grid or sorted(MAPS):
        info = classify(a.amiga, g)
        f = info['flags']
        print('grid %d: water %d, decks %d (over water %d), ramps %d, roofs %d, roads %d' % (
            g, sum(1 for v in f if v & WATER and not v & DECK), sum(1 for v in f if v & DECK),
            sum(1 for i, v in enumerate(f) if v & DECK and info['under'][i]), sum(1 for v in f if v & RAMP),
            sum(1 for v in f if v & ROOF), sum(1 for v in f if v & ROAD)))
        if a.out:
            os.makedirs(a.out, exist_ok=True)
            json.dump(info, open(os.path.join(a.out, 'grid%d.json' % g), 'w'))


if __name__ == '__main__':
    sys.exit(main())
