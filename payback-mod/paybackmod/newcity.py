"""Neo Mute City: a new free-roam city on Freedom City's road network.

Traffic and spawn points follow the existing streets, so the roads and their
kerbs stay exactly where they are. Every city block between them is rebuilt:
window-lit towers, stunt plazas with full-width kickers that land inside the
plaza, and neon parks. Nothing low enough to be mistaken for flat ground
stands next to a road: buildings are set back one cell and are all tall.
"""
import random
import struct

from .blocks import rec, EMPTY
from .stuntpark import surf, ZEBRA, CHECKER, G, STEP, UP_X, DOWN_X

DARK, RED, GRASS, SIDEWALK = 0x2b, 0x2e, 0x0c, 0x52
ROOFS = (0x0d, 0x29, 0x32, 0x11, 0x33, 0x31, 0x24, 0x1c)   # the city's own rooftop textures
WINDOWS = (0x1014, 0x1016, 0x1045, 0x104d)
PARK = (range(40, 80), range(24, 44))      # the stunt park block stays as it is


def _kind(col):
    h0, h1, shape = struct.unpack_from('<HHB', col, 4)
    if h0 != G or h1 != G:
        return '#'
    return '+' if col[3] & 0x0f else ':' if col[3] & 0x20 else '.'


def building(h, top, side):
    return rec(G, h, shape=1, flags=0x60, tex=top, attr=0x90, sides=(side,) * 4) + EMPTY + EMPTY


def build(city, seed=2026):
    """city: 16384 level-0 columns (index x*128+y). Returns {(x, y): column} for the new blocks."""
    rnd = random.Random(seed)
    kind = [_kind(c) for c in city]
    at = lambda x, y: kind[x * 128 + y] if 0 <= x < 128 and 0 <= y < 128 else '#'

    def keep(x, y):
        if x in (0, 127) or y in (0, 127) or (x in PARK[0] and y in PARK[1]):
            return True
        k = at(x, y)
        return k == '+' or (k == ':' and any(at(x + i, y + j) == '+' for i in (-1, 0, 1) for j in (-1, 0, 1)))

    free = {(x, y) for x in range(128) for y in range(128) if not keep(x, y)}
    out = {}
    seen = set()
    for start in sorted(free):
        if start in seen:
            continue
        block, todo = [], [start]
        seen.add(start)
        while todo:
            x, y = todo.pop()
            block.append((x, y))
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in free and n not in seen:
                    seen.add(n)
                    todo.append(n)
        _fill(block, set(block), out, rnd)
    return out


def _inner(cells, bset):
    """Cells of the block that are not on its edge (one-cell sidewalk set-back)."""
    return [(x, y) for x, y in cells
            if all((x + i, y + j) in bset for i in (-1, 0, 1) for j in (-1, 0, 1))]


def _fill(block, bset, out, rnd):
    for p in block:
        out[p] = surf(G, tex=SIDEWALK)                   # sidewalk
    inner = _inner(block, bset)
    if len(block) < 30 or not inner:
        for x, y in inner:                               # neon park with light pillars
            out[(x, y)] = surf(G, tex=GRASS)
            if x % 4 == 0 and y % 4 == 0:
                out[(x, y)] = building(0x1c0, RED, WINDOWS[0])
        return
    xs, ys = [p[0] for p in inner], [p[1] for p in inner]
    w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    if max(w, h) >= 16 and rnd.random() < 0.45 and _plaza(inner, set(inner), out, rnd):
        return
    iset = set(inner)
    for x, y in inner:                                    # towers on 3x3 lots with 1-cell alleys
        lx, ly = (x - min(xs)) % 4, (y - min(ys)) % 4
        if lx == 3 or ly == 3:
            continue
        lot = (x - lx, y - ly)
        r = random.Random(hash(lot) ^ 77)
        if all((lot[0] + i, lot[1] + j) in iset for i in range(3) for j in range(3)):
            hgt = r.choice((0x1c0, 0x200, 0x240, 0x280, 0x2c0, 0x300, 0x340))
            out[(x, y)] = building(hgt, RED if r.random() < 0.1 else r.choice(ROOFS), r.choice(WINDOWS))


def _plaza(inner, iset, out, rnd):
    """Full-width kicker on the plaza's long axis; landing and run-out stay inside the plaza."""
    xs, ys = [p[0] for p in inner], [p[1] for p in inner]
    along_x = max(xs) - min(xs) >= max(ys) - min(ys)
    for p in inner:
        out[p] = surf(G, tex=DARK)
    lo_a, hi_a = (min(xs), max(xs)) if along_x else (min(ys), max(ys))
    lo_c, hi_c = (min(ys), max(ys)) if along_x else (min(xs), max(xs))
    mid = (lo_c + hi_c) // 2
    lanes = range(mid - 1, mid + 2)
    start = lo_a + 2
    kicker, landing = 5, 8
    if start + kicker + landing > hi_a:
        return False
    cells = [(a, c) for a in range(start, start + kicker + landing) for c in lanes]
    pos = lambda a, c: (a, c) if along_x else (c, a)
    if not all(pos(a, c) in iset for a, c in cells):
        return False
    for k in range(kicker):
        for c in lanes:
            out[pos(start + k, c)] = surf(G + STEP * k, G + STEP * (k + 1),
                                          UP_X if along_x else 2, ZEBRA)
    return True
