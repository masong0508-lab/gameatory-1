"""Stunt ramps for the city maps, built into Payback's own grids (build.py --amiga).

A spot is a wide, flat plaza or park lawn with a kicker in it, not a ramp in a street: Payback's top-down view hardly
shows the raised side of a block, so a ramp in a traffic lane reads as an invisible wall (the player met that twice).
So every spot is
    1 cell of flat full-width approach (untouched ground)
    4 cells of run-up, 6.25 % up the middle (0x10 a cell: a low kick, the car lands inside the 4 cells at any speed), 5 wide
      and crowned (the sides lower), the last cell striped: the lip
    2 cells of gap (untouched ground)
    4 cells of flat landing, 5 wide, chequered
with a cell of free ground on every side of the whole 7 x 13 (7 x 10 with a 1 cell gap), which no road, building, tree,
railing, water, bridge, roof or traffic lane touches (the cities have few plazas that big). The raised cells have Payback's own concrete sides, which the world
draws, and nothing on them is a trigger: the car meets the lip as a slope up from the ground, as it meets any ramp.

Payback's own collision follows because the ramps are painted into the grid (PaybackRom.paint); mkworld then draws
and collides them like any floor, and tools/colcheck.py checks that it does.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..', 'payback-mod'))
import mkworld   # noqa: E402
import amiga_classify   # noqa: E402
from paybackmod.stuntpark import surf, G, ROAD, ZEBRA, CHECKER   # noqa: E402

N = 128
# (cells of approach, run-up, gap, landing; width of the block with its margin, of the ramp; the margin at each end)
PROFILES = ((1, 4, 2, 4, 7, 5, 1), (1, 4, 1, 4, 7, 5, 0))
RISES = {(0, 1): 2, (1, 0): 3, (0, -1): 4, (-1, 0): 5}      # direction -> the slope shape that rises that way
OVER = 1                                                     # free cells past the landing (a car that lands long rolls out)
# The run-up is crowned: the height (steps over the street) at the start of each of its 4 cells and at its end, by column out from the
# middle. A man is let walk onto a floor Payback allows (about 62 steps up, not 64) and is stood on the top we draw there, so no
# walkable edge may have a face between 24 steps (192 units) and that: the columns step down at most 24 at the middle of a cell, the
# outermost end low (24) and the others' ends high (a wall to Payback, as the middle's 64 always was). The long edge of a cell
# of the middle sees 40 and 56 over the street: the columns in between, 21 and 43, stand there.
CROWN = ((0, 16, 32, 48, 64), (0, 9, 18, 24, 64), (0, 6, 12, 18, 24))
APART = 24                                                   # cells between two spots of a map
SKIP = {0: ((40, 24, 80, 44),)}                              # (Freedom City's stadium has its own stunt park)


def open_cells(rom, level, grid):
    """Cells of flat open ground nothing stands on or touches: the plaza and lawn cells at street level that are no
    lane, have no scenery or railing, are not under a deck and are not water."""
    mkworld.STREET = mkworld.street_level(rom, grid)
    # (the Amiga map's say, as the build has it: merged() draws a span by it, and a cell it calls water, span, ramp or
    # roof is no plaza however Payback's grid looks, nor is a cell next to water or a span)
    am = mkworld.AMIGA.get(level) if mkworld.AMIGA else None
    mkworld.AMIGA_LEVEL = am
    try:
        cells, decks, walls, tiles, objs, decks2, swim = mkworld.merged(rom, grid)
    finally:
        mkworld.AMIGA_LEVEL = None
    bad = {i for i, _, _ in walls}
    if am:
        wet = amiga_classify.WATER | amiga_classify.DECK
        for i in range(N * N):
            f = am['flags'][i]
            if f & (amiga_classify.RAMP | amiga_classify.ROOF):
                bad.add(i)
            if f & wet or am['under'][i]:            # (and a cell of margin round water and spans)
                x, y = divmod(i, N)
                bad.update((x + a) * N + y + b for a in (-1, 0, 1) for b in (-1, 0, 1) if 0 <= x + a < N and 0 <= y + b < N)
    ok = [False] * (N * N)
    for i in range(N * N):
        col = rom.column(grid[i])
        c = cells[i]
        ok[i] = (c[0] == 'ground' and c[3] == 1 and c[1] == 0 and c[2] == 0 and c[4] in (mkworld.M_PLAZA, mkworld.M_GRASS)
                 and i not in decks and i not in decks2 and i not in bad and not col[3] and col[8] == 1
                 and not (col[1] or col[21] or col[41]) and all(col[20 * k + 8] == 0 for k in (1, 2)))
    return ok


def find(ok, level, n):
    """Up to n spots (x, y of the first cell of the approach, direction, profile) far apart, the biggest profile and the
    nearest to the middle first."""
    pre = [[0] * (N + 1) for _ in range(N + 1)]
    for x in range(N):
        for y in range(N):
            pre[x + 1][y + 1] = pre[x][y + 1] + pre[x + 1][y] - pre[x][y] + (not ok[x * N + y])

    def clear(x0, y0, x1, y1):      # cells x0..x1, y0..y1 inclusive all open
        if x0 < 0 or y0 < 0 or x1 >= N or y1 >= N:
            return False
        return pre[x1 + 1][y1 + 1] - pre[x0][y1 + 1] - pre[x1 + 1][y0] + pre[x0][y0] == 0

    mid, out = N / 2, []
    for pi, (ap, run, gap, land, wide, ramp, end) in enumerate(PROFILES):
        length = ap + run + gap + land
        found = []
        for d in RISES:
            for x in range(N):
                for y in range(N):
                    ex, ey = x + d[0] * (length - 1), y + d[1] * (length - 1)
                    px, py = (0, 1) if d[0] else (1, 0)
                    h = wide // 2
                    x0, x1 = sorted((x - d[0] * end - px * h, ex + d[0] * (end + OVER) + px * h))
                    y0, y1 = sorted((y - d[1] * end - py * h, ey + d[1] * (end + OVER) + py * h))
                    if clear(x0, y0, x1, y1) and not any(
                            x0 <= b[2] and x1 >= b[0] and y0 <= b[3] and y1 >= b[1] for b in SKIP.get(level, ())):
                        found.append((x, y, d, pi))
        found.sort(key=lambda s: (abs(s[0] + s[2][0] * length / 2 - mid) + abs(s[1] + s[2][1] * length / 2 - mid), s))
        for s in found:
            if all(abs(s[0] - o[0]) + abs(s[1] - o[1]) >= APART for o in out):
                out.append(s)
                if len(out) == n:
                    return out
    return out


def paint(spot):
    """{(x, y): column} of one spot (the run-up crowned: CROWN)."""
    x, y, d, pi = spot
    ap, run, gap, land, wide, ramp, end = PROFILES[pi]
    px, py = (0, 1) if d[0] else (1, 0)
    cells = {}
    for u in range(ap + run + gap + land):
        for v in range(-(ramp // 2), ramp // 2 + 1):
            c = (x + d[0] * u + px * v, y + d[1] * u + py * v)
            k = u - ap
            if 0 <= k < run:
                h = CROWN[abs(v)]
                cells[c] = surf(G + h[k], G + h[k + 1], RISES[d], ZEBRA if k == run - 1 else ROAD)
            elif u >= ap + run + gap:
                cells[c] = surf(G, tex=CHECKER)
    return cells


def add(rom, per_level=3):
    """Paint the spots into the grids of levels 0..3 (as many as fit); returns {level: [spots]}."""
    done = {}
    for level in range(4):
        grid = rom.painted.get(level) or rom.grid(level)
        spots = find(open_cells(rom, level, grid), level, per_level)
        cells = {}
        for s in spots:
            cells.update(paint(s))
        if cells:
            rom.paint(level, cells)
        done[level] = spots
    return done


if __name__ == '__main__':
    from paybackmod.rom import PaybackRom
    rom = PaybackRom(open(sys.argv[1], 'rb').read())
    for lv, sp in add(rom).items():
        print('level', lv, sp)
