"""Colour tables for Stunt Fox inside Payback, made from the player's own Payback ROM.

Inside Payback the screen shows Payback's own palette, unchanged, so Payback's 32 x 32 tiles
can be drawn as they are. Stunt Fox's flat colours (materials x light x fog, see src/palette.c)
are matched to the nearest of Payback's colours; the sky uses Payback's own blues (space.c).

Output: C source with
    pb_pmap[256]      Stunt Fox colour -> Payback palette index
    pb_shade[3][256]  Payback index -> the same colour darker (light levels 0..2 of walls)
    pb_sky[16]        colours no tile of Payback's city uses (not needed any more by the game)
    pb_avg[TILE_IDS]  the average colour of each tile, for walls and roofs too far to texture
    pb_mesh[]         a bit per tile id: a fine mesh (a chain-link fence), drawn flat on walls
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'payback-mod'))
from paybackmod.rom import PaybackRom   # noqa: E402

PALETTE = 0x6367a8                  # Payback's BG palette in ROM (red and blue swapped)
TILE_BANK = 0x0ce0bc
TILE_IDS = 0x318
TEX_WATER, WATER = 0x317, 0x2f8de8  # our id for Payback's water, and the texels it shows (src/tex.h)
WATER_ID = 0x311                    # Payback's own water tile (a mesh by the measure below, never a wall)
# src/palette.c
BASE = [(0, 0, 0), (7, 7, 10), (19, 19, 18), (6, 17, 7), (21, 17, 12), (20, 20, 21), (8, 15, 25),
        (23, 10, 8), (5, 21, 20), (27, 25, 18), (12, 13, 17), (5, 10, 29), (31, 27, 4), (28, 28, 29),
        (31, 14, 3), (31, 6, 11)]
LIGHT = (12, 17, 22, 27)
FOG = (22, 26, 30)
SHADE = (0.58, 0.72, 0.86)


def palette(rom):
    out = []
    for i in range(256):
        c = struct.unpack_from('<H', rom, PALETTE + 2 * i)[0]
        out.append((c >> 10 & 31, c >> 5 & 31, c & 31))
    return out


def city_tiles(rom):
    """Ids of the tiles the city uses (tops and sides of its columns)."""
    r = PaybackRom(rom)
    ids = set()
    for c in set(r.grid(0)):
        col = r.column(c)
        for k in range(3):
            b = col[20 * k:20 * k + 20]
            if b[8]:
                ids.add(b[10] | (b[11] & 3) << 8)
                ids.update(s & 0x3ff for s in struct.unpack_from('<4H', b, 12))
    return {i for i in ids if 0 < i < TILE_IDS}


def mesh_tiles(rom, pal):
    """Tiles that are a fine high-contrast mesh (Payback's chain-link fences, 0x15 and 0x1a0):
    at our two pixels a texel they come out as a harsh checkerboard that reads as a missing
    texture, so walls draw them flat in their average colour instead."""
    lum = [(r * 299 + g * 587 + b * 114) / 1000 for r, g, b in pal]
    out = set()
    for t in range(1, TILE_IDS):
        a = TILE_BANK + t * 0x400
        L = [lum[p] for p in rom[a:a + 0x400]]
        m = sum(L) / 1024
        sd = (sum((l - m) ** 2 for l in L) / 1024) ** 0.5
        if sd < 3:
            continue
        d = (sum(abs(L[y * 32 + x] - L[y * 32 + x + 1]) for y in range(32) for x in range(31)) +
             sum(abs(L[y * 32 + x] - L[(y + 1) * 32 + x]) for y in range(31) for x in range(32))) / (2 * 32 * 31)
        if d > 1.1 * sd:            # neighbours differ by more than the tile's own spread: a mesh
            out.add(t)
    return out


def tables(rom):
    pal = palette(rom)
    used = set()
    for t in city_tiles(rom):
        a = TILE_BANK + t * 0x400
        used.update(rom[a:a + 0x400])
    free = [i for i in range(1, 256) if i not in used][:16]
    assert len(free) >= 8, 'Payback palette: too few free colours'
    solid = list(range(1, 256))       # (Payback's palette is never changed: any of its colours will do)

    def near(r, g, b):
        return min(solid, key=lambda i: 3 * (pal[i][0] - r) ** 2 + 4 * (pal[i][1] - g) ** 2 +
                   2 * (pal[i][2] - b) ** 2)
    pmap = [0] * 256
    for i in range(16):
        pmap[i] = free[i * len(free) // 16]
    for m in range(1, 16):
        for li in range(4):
            for f in range(4):
                r, g, b = (BASE[m][k] * LIGHT[li] / 27 for k in range(3))
                w = f * 5 / 16
                r, g, b = r + (FOG[0] - r) * w, g + (FOG[1] - g) * w, b + (FOG[2] - b) * w
                pmap[m * 16 + li * 4 + f] = near(r, g, b)
    shade = []
    for s in SHADE:
        shade.append([i if i in free else near(*(c * s for c in pal[i])) for i in range(256)])
    avg = []
    for t in range(TILE_IDS):
        a = WATER if t == TEX_WATER else TILE_BANK + t * 0x400
        px = [p for p in rom[a:a + 0x400] if p]
        if not px:
            avg.append(0)
            continue
        avg.append(near(*(sum(pal[p][k] for p in px) / len(px) for k in range(3))))
    mesh = [0] * ((TILE_IDS + 31) // 32)
    for t in mesh_tiles(rom, pal) - {WATER_ID}:
        mesh[t >> 5] |= 1 << (t & 31)
    return pmap, shade, pmap[:16], avg, free, mesh


def main(rom_path, out):
    rom = open(rom_path, 'rb').read() if isinstance(rom_path, str) else rom_path
    pmap, shade, sky, avg, free, mesh = tables(rom)

    def arr(v):
        return ',\n    '.join(', '.join('%d' % x for x in v[i:i + 16]) for i in range(0, len(v), 16))
    with open(out, 'w') as f:
        f.write('/* generated by tools/mkpal.py from the player\'s Payback ROM */\n')
        f.write('#include "../../src/gba.h"\n')
        f.write('const u8 pb_pmap[256] = {\n    %s};\n' % arr(pmap))
        f.write('u8 pb_shade[3][256] = {\n')
        for s in shade:
            f.write('  {%s},\n' % arr(s))
        f.write('};\n')
        f.write('const u8 pb_sky[16] = {%s};\n' % arr(sky))
        f.write('const u8 pb_avg[%d] = {\n    %s};\n' % (len(avg), arr(avg)))
        f.write('const u32 pb_mesh[%d] = {%s};\n' % (len(mesh), ', '.join('0x%08x' % v for v in mesh)))
    return free


if __name__ == '__main__':
    print(main(sys.argv[1], sys.argv[2]))
