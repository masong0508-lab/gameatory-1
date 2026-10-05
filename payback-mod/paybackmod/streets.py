"""Jump ramps in Freedom City's traffic lanes.

Streets are three cells wide: two traffic lanes and a kerb-side strip. The
lane flag in byte 3 of a column says which way traffic drives (measured in
the emulator): 1 = -y, 4 = +y, 2 = +x, 8 = -x; 0x20 marks the kerb strip.

Payback only throws a car into the air when the ground drops away under it,
so a jump has to be a kicker ramp followed by a drop. Each ramp faces the
traffic in its own lane, so cars driving the right way (traffic included)
launch off it and land on the flat road beyond; the other lane stays clear,
with its own ramp facing the other way further along.
"""
import struct

from .stuntpark import ZEBRA, SIDES

# lane texture, lane flag, axis, direction of travel, texture of the kerb strip beside it (if any)
LANES = ((0x71, 0x01, 'y', -1, None), (0x7d, 0x04, 'y', +1, 0x6a),
         (0x89, 0x02, 'x', +1, None), (0x8b, 0x08, 'x', -1, 0x53))
KICKER = 5        # cells, rising 0x20 each: 0x100 -> 0x1a0
LANDING = 7       # flat lane cells needed after the lip
GAP = 20          # cells between ramps in the same lane
SHAPE = {('x', 1): 3, ('x', -1): 5, ('y', 1): 2, ('y', -1): 4}   # block shape rising toward travel


def _flat_lane(col, tex, flag):
    h0, h1, shape = struct.unpack_from('<HHB', col, 4)
    return col[10] == tex and col[3] & flag and h0 == h1 == 0x100 and shape == 1 and col[28] == 0


def find(rom, level=0, avoid=()):
    """Ramp spots as (x, y, axis, direction, kerb texture): (x, y) is the first kicker cell."""
    g = rom.grid(level)
    col = lambda x, y: rom.column(g[x * 128 + y])
    taken = set(avoid)
    out = []
    for tex, flag, axis, d, kerb in LANES:
        step = (d, 0) if axis == 'x' else (0, d)
        for x in range(2, 126):
            for y in range(2, 126):
                cells = [(x + step[0] * k, y + step[1] * k) for k in range(-1, KICKER + LANDING)]
                if not all(1 <= cx < 127 and 1 <= cy < 127 for cx, cy in cells):
                    continue
                if taken & set(cells) or not all(_flat_lane(col(cx, cy), tex, flag) for cx, cy in cells):
                    continue
                out.append((x, y, axis, d, kerb))
                for k in range(-GAP, GAP + KICKER + LANDING):   # keep GAP cells free along this lane
                    taken.add((x + step[0] * k, y + step[1] * k))
    return out


def build(rom, level=0, avoid=()):
    """Returns {(x, y): column} for every ramp find() places."""
    g = rom.grid(level)
    cells = {}
    for x, y, axis, d, kerb in find(rom, level, avoid):
        step = (d, 0) if axis == 'x' else (0, d)
        side = (0, 1) if axis == 'x' else (1, 0)
        for k in range(KICKER):
            lo, hi = 0x100 + 0x20 * k, 0x120 + 0x20 * k
            cx, cy = x + step[0] * k, y + step[1] * k
            spots = [(cx, cy)]
            if kerb is not None:
                kx, ky = cx + side[0], cy + side[1]
                c = rom.column(g[kx * 128 + ky])
                if c[10] == kerb and struct.unpack_from('<HH', c, 4) == (0x100, 0x100) and c[28] == 0:
                    spots.append((kx, ky))
            for px, py in spots:
                c = bytearray(rom.column(g[px * 128 + py]))
                struct.pack_into('<HHB', c, 4, lo, hi, SHAPE[axis, d])
                if k == KICKER - 1:
                    c[10] = ZEBRA
                struct.pack_into('<4H', c, 12, *SIDES)
                cells[(px, py)] = bytes(c)
    return cells
