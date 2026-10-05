"""Map column records.

A column is 60 bytes: three 20-byte block records stacked on one grid cell.
Record 0 is the floor that vehicles drive on; ramps only work there (a sloped
record 1 acts as a wall).

    +0  b0 b1 b2 b3   flags
    +4  u16 h0        height at the low edge   (0x100 = street level)
    +6  u16 h1        height at the high edge
    +8  shape         0 none, 1 flat, 2 rises to +y, 3 rises to +x, 4 rises to -y, 5 rises to -x
    +9  flags         0x60 for drivable surfaces
    +10 top texture
    +11 attr          0x90
    +12 4 x u16 side textures (low byte texture, 0x10 in the high byte)

World z for a height h is 19904 - 16 * (h - 0x100). Cars can climb at most
0x20 per cell; 0x30 per cell stops them.
"""
import struct


def rec(h0=0x100, h1=None, shape=0, flags=0x20, tex=0x28, attr=0x90, sides=(0, 0, 0, 0), b0=0, b1=0, b2=0, b3=0):
    h1 = h0 if h1 is None else h1
    return struct.pack('<BBBBHHBBBB4H', b0, b1, b2, b3, h0, h1, shape, flags, tex, attr, *sides)


EMPTY = rec()


def column(*recs):
    recs = list(recs) + [EMPTY] * (3 - len(recs))
    return b''.join(recs)
