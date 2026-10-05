"""The space level the Arwing flies to: a dark deck with asteroid towers, landing pads and kickers."""
import random

from .blocks import rec, EMPTY
from .stuntpark import surf, ZEBRA, CHECKER, G, STEP, UP_X, DOWN_X

SPACE, RED, CONCRETE_TOP = 0x2b, 0x2e, 0x3c
TOWER_SIDES = (0x103c, 0x102e, 0x103c, 0x102e)


def tower(h, top):
    return rec(G, h, shape=1, flags=0x60, tex=top, attr=0x90, sides=TOWER_SIDES) + EMPTY + EMPTY


def build(city, seed=1701):
    """city: level 0 grid as column bytes per cell (for the map edge). Returns 16384 columns."""
    rnd = random.Random(seed)
    cells = [surf(G, tex=SPACE) for _ in range(128 * 128)]
    for i in range(128):                           # keep the city's outer wall
        for x, y in ((i, 0), (i, 127), (0, i), (127, i)):
            cells[x * 128 + y] = city[x * 128 + y]

    def put(x, y, col):
        if 2 <= x < 126 and 2 <= y < 126:
            cells[x * 128 + y] = col

    for _ in range(220):                           # asteroid towers in small clusters
        cx, cy = rnd.randrange(4, 124), rnd.randrange(4, 124)
        h = rnd.choice((0x180, 0x200, 0x280, 0x300))
        for _ in range(rnd.randrange(1, 6)):
            put(cx + rnd.randrange(-1, 2), cy + rnd.randrange(-1, 2),
                tower(h + rnd.randrange(-2, 3) * 0x20, RED if rnd.random() < 0.3 else CONCRETE_TOP))
    for _ in range(30):                            # landing pads with a ramp up each side
        cx, cy = rnd.randrange(8, 116), rnd.randrange(8, 116)
        top = G + 3 * STEP
        for x in range(cx, cx + 4):
            for y in range(cy, cy + 4):
                put(x, y, surf(top, tex=CHECKER))
        for k in range(3):
            lo, hi = G + STEP * k, G + STEP * (k + 1)
            for y in range(cy, cy + 4):
                put(cx - 3 + k, y, surf(lo, hi, UP_X))
                put(cx + 6 - k, y, surf(lo, hi, DOWN_X))
            for x in range(cx, cx + 4):
                put(x, cy - 3 + k, surf(lo, hi, 2))
                put(x, cy + 6 - k, surf(lo, hi, 4))
    for _ in range(60):                            # kickers, any direction
        cx, cy = rnd.randrange(8, 120), rnd.randrange(8, 120)
        d = rnd.randrange(4)
        step = ((0, 1), (1, 0), (0, -1), (-1, 0))[d]
        shape = (2, UP_X, 4, DOWN_X)[d]
        for k in range(5):
            lo, hi = G + STEP * k, G + STEP * (k + 1)
            for w in (-1, 0, 1):
                x = cx + step[0] * k + step[1] * w
                y = cy + step[1] * k + step[0] * w
                put(x, y, surf(lo, hi, shape, ZEBRA if k == 4 else 0x00))
    return cells
