"""Payback's minimap of a level: 64 x 64 pixels of 4 bits, low nibble first, 2 x 2 cells to a pixel,
at 0x34c230 + level * 0x800 in the ROM (the ROM's own addresses; the table is not read from the repo).

Payback's own maps follow one rule, measured on Freedom City, Los Francos and Corona (road pixels agree
on all of them; the whole picture on 96.7 to 99.6%): a pixel is 2 if any of its four cells has a lane,
else 1 if the pixel to its west, north or north-west is road (the road's shadow), else 0. A small compass
mark (colour 7 and the row of 1s under it, at the top middle) is on every map's picture and is kept.
"""
import struct

BASE = 0x34c230
SIZE = 0x800
PX = 64
ROAD, SHADOW, EMPTY, MARK = 2, 1, 0, 7


def road_pixels(lanes):
    """lanes: 128 * 128 per-cell lane masks (index x * 128 + y). Returns [row][col] of 0 / 1 for a lane in the 2 x 2."""
    out = [[0] * PX for _ in range(PX)]
    for px in range(PX):
        for py in range(PX):
            out[py][px] = 1 if any(lanes[(2 * px + i) * 128 + 2 * py + j] for i in (0, 1) for j in (0, 1)) else 0
    return out


def pixels(lanes, stamp=()):
    """The picture as [row][col] of colours; stamp: (col, row, colour) overlaid last (the compass)."""
    road = road_pixels(lanes)
    out = [[EMPTY] * PX for _ in range(PX)]
    for py in range(PX):
        for px in range(PX):
            if road[py][px]:
                out[py][px] = ROAD
            elif (px and road[py][px - 1]) or (py and road[py - 1][px]) or (px and py and road[py - 1][px - 1]):
                out[py][px] = SHADOW
    for px, py, c in stamp:
        out[py][px] = c
    return out


def pack(pix):
    b = bytearray(SIZE)
    for py in range(PX):
        for px in range(PX):
            i = py * PX + px
            b[i >> 1] |= pix[py][px] << (4 * (i & 1))
    return bytes(b)


def unpack(data):
    flat = []
    for v in data[:SIZE]:
        flat += [v & 15, v >> 4]
    return [flat[py * PX:(py + 1) * PX] for py in range(PX)]


def read(rom_bytes, level):
    o = BASE + level * SIZE
    return unpack(rom_bytes[o:o + SIZE])


def compass(rom_bytes, level):
    """The compass mark of a shipped picture: its colour-7 pixels and the 1s in the row under them."""
    pix = read(rom_bytes, level)
    mark = [(px, py) for py in range(PX) for px in range(PX) if pix[py][px] == MARK]
    out = [(px, py, MARK) for px, py in mark]
    if mark:
        row = max(py for _, py in mark) + 1
        cols = [px for px, _ in mark]
        out += [(px, row, SHADOW) for px in range(min(cols), max(cols) + 1) if pix[row][px] == SHADOW]
    return out


def render(lanes, rom_bytes, level):
    """The bytes for level's picture from its lane masks, with the compass the shipped picture has."""
    return pack(pixels(lanes, compass(rom_bytes, level)))


def write(rom, level, data):
    assert len(data) == SIZE
    rom.d[BASE + level * SIZE:BASE + (level + 1) * SIZE] = data


def check(data, lanes, stamp=()):
    """AV8: the picture decodes to what was drawn, and its road pixels are the grid's: each lane cell is
    inside a road pixel and each road pixel holds one (the stamp's pixels excepted). Returns problems."""
    bad = []
    if len(data) != SIZE:
        return ['picture is %d bytes, not %d' % (len(data), SIZE)]
    pix = unpack(data)
    road = road_pixels(lanes)
    skip = {(px, py) for px, py, _ in stamp}
    hit = miss = 0
    for py in range(PX):
        for px in range(PX):
            if (px, py) in skip:
                continue
            if road[py][px] == (pix[py][px] == ROAD):
                hit += 1
            else:
                miss += 1
    prec = hit / (hit + miss)
    if prec < 0.99:
        bad.append('road pixels agree with the grid on %.2f%% (< 99%%)' % (100 * prec))
    return bad
