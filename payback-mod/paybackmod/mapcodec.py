"""Payback (GBA) level grid codec.

A level is a 128x128 grid of pointers to 60-byte map columns. The ROM keeps
each level's grid as a bitstream (one pointer per level at LEVEL_TABLE) that
the game decodes into EWRAM when the level loads. Cells are stored with the
index ``x * 128 + y``; one cell is 2048 world units.

Bitstream: little-endian 32-bit words read MSB first. Per cell:

    0          -> neighbour 0 (first distinct cell in the scan order below)
    10         -> neighbour 1
    11 00      -> previous cell's column + 1
    11 01 n15  -> column number n
    11 10 m2   -> neighbour m + 2
    11 11 n5   -> neighbour n + 6

The neighbour scan replicates the routine at 0x0803c4cc: a zigzag walk over
already-decoded cells that collects distinct column pointers.
"""
import struct

GBA = 0x08000000
LEVEL_TABLE = 0x1aa8b4    # 11 pointers to grid bitstreams (level 0 = Freedom City)
COLUMN_BASE = 0x081aa8e0  # column table, 60 bytes per column
W = 128


class BitReader:
    def __init__(self, d, off):
        self.d, self.p = d, off
        self.word = struct.unpack_from('<I', d, off)[0]
        self.left = 32

    def read(self, n):
        v = 0
        for _ in range(n):
            if self.left == 0:
                self.p += 4
                self.word = struct.unpack_from('<I', self.d, self.p)[0]
                self.left = 32
            v = (v << 1) | (self.word >> 31)
            self.word = (self.word << 1) & 0xffffffff
            self.left -= 1
        return v


def neighbours(grid, row, x, kmax):
    """First kmax+1 distinct cells in the decoder's scan order, starting next to (row, x)."""
    r7, r6, r4, r5 = 1, -1, row - 1, x
    seen = []
    while True:
        if 0 <= r4 < W and 0 <= r5 < W:
            cell = grid[r4 * W + r5]
            if cell not in seen:
                seen.append(cell)
                if len(seen) > kmax:
                    return seen
        r4 += r7
        r5 += r6
        if r4 > row:
            r4 -= 1
            r7, r6 = -r7, -r6
        elif r5 > x:
            r5 -= 1
            r7, r6 = -r7, -r6
        if r4 < 0 and r5 < 0:
            return seen


def neighbour(grid, row, x, k):
    nb = neighbours(grid, row, x, k)
    return nb[k] if len(nb) > k else grid[0]


def decode(d, level):
    """Decode a level's grid from ROM bytes. Returns (16384 column pointers, stream length)."""
    ptr = struct.unpack_from('<I', d, LEVEL_TABLE + 4 * level)[0]
    br = BitReader(d, ptr - GBA)
    grid = [0] * (W * W)
    prev = COLUMN_BASE
    for row in range(W):
        for x in range(W):
            if br.read(1) == 0:
                c = neighbour(grid, row, x, 0)
            elif br.read(1) == 0:
                c = neighbour(grid, row, x, 1)
            else:
                t = br.read(2)
                if t == 0:
                    c = prev + 60
                elif t == 1:
                    c = COLUMN_BASE + 60 * br.read(15)
                elif t == 2:
                    c = neighbour(grid, row, x, 2 + br.read(2))
                else:
                    c = neighbour(grid, row, x, 6 + br.read(5))
            grid[row * W + x] = c
            prev = c
    return grid, br.p + 4 - (ptr - GBA)


class BitWriter:
    def __init__(self):
        self.bits = []

    def write(self, v, n):
        self.bits += [(v >> (n - 1 - i)) & 1 for i in range(n)]

    def data(self):
        b = self.bits + [0] * (-len(self.bits) % 32)
        out = bytearray()
        for i in range(0, len(b), 32):
            w = 0
            for bit in b[i:i + 32]:
                w = (w << 1) | bit
            out += struct.pack('<I', w)
        return bytes(out + b'\0\0\0\0')


def encode(grid_idx):
    """Encode 16384 column numbers (relative to the column base) into a grid bitstream."""
    bw = BitWriter()
    grid = [None] * (W * W)
    prev = 0
    for row in range(W):
        for x in range(W):
            c = grid_idx[row * W + x]
            nb = neighbours(grid, row, x, 37)
            if nb and (row or x) and nb[0] == c:
                bw.write(0, 1)
            elif len(nb) > 1 and nb[1] == c:
                bw.write(0b10, 2)
            elif (row or x) and c == prev + 1:
                bw.write(0b1100, 4)
            elif c in nb[2:6]:
                bw.write(0b1110, 4)
                bw.write(nb.index(c) - 2, 2)
            elif c in nb[6:38]:
                bw.write(0b1111, 4)
                bw.write(nb.index(c) - 6, 5)
            else:
                bw.write(0b1101, 4)
                bw.write(c, 15)
            grid[row * W + x] = c
            prev = c
    return bw.data()
