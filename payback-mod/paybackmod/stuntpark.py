"""Stage 1: a Race Drivin / Stunt Race FX style stunt park in Freedom City's football stadium.

Grid coordinates are cells (x, y); the stadium block spans x 40..79, y 24..43.
The stands are flattened into an open arena with low walls along y = 24 and
y = 43, and both ends are open to the streets so cars can drive straight in.

    Lane A  y 27..29, drive +x from the west street:
            kicker to 0x1c0 (jump), open landing, whoops, tabletop
    Lane B  y 39..41, drive -x from the east street:
            long climb to a 0x200 deck, run along it, drop off the striped lip
    Middle  y 32..35: a spine west of the helipad and a tabletop east of it

Landings are always flat or downhill so a short jump never hits a wall.
"""
from .blocks import rec, EMPTY

ROAD, ZEBRA, CHECKER, ARENA = 0x00, 0x72, 0x15, 0x2b
CONCRETE_TOP, CONCRETE_SIDE = 0x3c, 0x103c
SIDES = (CONCRETE_SIDE,) * 4
UP_X, DOWN_X = 3, 5      # slope shapes: rising toward +x / toward -x
G = 0x100                # street level
STEP = 0x20              # steepest slope a car can climb, per cell

# Lane start points for testing: (x, y, heading); heading units are 5760 per turn, 0 = +y, 1440 = +x
LANE_A_START = (36.5, 28.5, 1400)
LANE_B_START = (86.0, 40.5, 4320)


def surf(h0, h1=None, shape=1, tex=ROAD):
    raised = max(h0, h1 or h0) > G
    return rec(h0, h1, shape=shape, flags=0x60, tex=tex, attr=0x90, sides=SIDES if raised else (0, 0, 0, 0)) + EMPTY + EMPTY


def flat(xs, ys, h, cells, tex=ROAD):
    for x in xs:
        for y in ys:
            cells[(x, y)] = surf(h, tex=tex)


def ramp(xs, ys, base, step, cells, rising_x=True, lip=False):
    """Cells along xs, each `step` higher than the last. Rising toward +x, or toward -x."""
    xs = list(xs)
    for i, x in enumerate(xs):
        a = base + step * i
        lo, hi = (a, a + step) if step > 0 else (a + step, a)
        up = (step > 0) == rising_x
        tex = ZEBRA if lip and i == len(xs) - 1 else ROAD
        for y in ys:
            cells[(x, y)] = surf(lo, hi, UP_X if up else DOWN_X, tex)
    return base + step * len(xs)


def build():
    """Returns {(x, y): 60-byte column} for Freedom City (level 0)."""
    c = {}
    flat(range(40, 80), range(25, 43), G, c, ARENA)               # open arena floor
    flat(range(40, 80), (24, 43), G + 0x30, c, CONCRETE_TOP)      # low side walls

    A = range(27, 30)
    flat([41], A, G, c, CHECKER)                                  # start line
    ramp(range(45, 51), A, G, STEP, c, lip=True)                  # kicker, 0x100 -> 0x1c0
    for i, x in enumerate(range(61, 65)):                         # whoops
        for y in A:
            c[(x, y)] = surf(G, G + 0x18, UP_X if i % 2 == 0 else DOWN_X)
    top = ramp(range(67, 69), A, G, STEP, c)                      # tabletop
    flat([69, 70], A, top, c)
    ramp((71, 72), A, top, -STEP, c)

    B = range(39, 42)
    deck = ramp(range(77, 69, -1), B, G, STEP, c, rising_x=False)  # climb to 0x200
    flat(range(59, 70), B, deck, c)
    flat([58], B, deck, c, ZEBRA)                                 # lip, then a drop to the floor
    flat([45], B, G, c, CHECKER)                                  # finish line

    M = range(32, 36)
    top = ramp(range(43, 46), M, G, STEP, c)                      # spine
    flat([46], M, top, c, CHECKER)
    ramp(range(47, 50), M, top, -STEP, c)
    top = ramp(range(63, 66), M, G, STEP, c)                      # tabletop
    flat(range(66, 69), M, top, c, CHECKER)
    ramp(range(69, 72), M, top, -STEP, c)
    return c


def build_mode_columns():
    """Pieces the in-game build mode places: 17 flat heights, then 16 ramp steps per direction."""
    flats = [surf(G, tex=ROAD)] + [surf(G + STEP * i, tex=CHECKER) for i in range(1, 17)]
    ramps = []
    for shape in (2, UP_X, 4, DOWN_X):            # rising toward +y, +x, -y, -x
        ramps.append([surf(G + STEP * k, G + STEP * (k + 1), shape, ZEBRA if k == 3 else ROAD) for k in range(16)])
    return flats, ramps
