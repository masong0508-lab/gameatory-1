"""The planet each map stands on, made from the map's own world and Payback's own tiles.

From high up a map is a patch on a planet (src/planet.c). The patch is the map as coloured
blocks: each cell's top tile averaged (as tools/mkmip.py does, water too), the blocks sorted into
a few classes by their colour, each class one of Payback's palette colours, and the blocks of one
class merged into rectangles (three block sizes, 4, 8 and 16 cells, for the three heights
the game draws them from). Round the map goes the rest of its planet: a 5 x 5 grid of 128-cell
tiles, corners nudged so they read as land and sea, their classes drawn from the map's own mix.

Output: C source with
    pl_col[map][9][8]     class -> Payback palette index, by time of day (day, dusk, night) and haze (0 near .. 2 far)
    pl_sun[map][3]        the terminator: the sun's direction (sx, sz, signed bytes) and its distance (cells) from the map's middle
    pl_ring[map][6]       atmosphere, limb haze, planet disc, cloud by day, at dusk, by night
    pl_sur[map][25]       the surround tiles' classes (5 x 5, the map itself in the middle)
    pl_jit[map][36][2]    each lattice corner's nudge, in cells
    pl_cld[map][8][3]     clouds: x, z (cells, 256 round the map) and radius (units / 64)
    pl_sb[map][4][65]     where each 16-cell square's rectangles start in pl_rect (per block size; the 4th: all of the map's, the squares not kept apart)
    pl_rect[][4]          x, z (in blocks), w << 4 | h, class
Pure numpy, like the other build tools.
"""
import os
import struct
import sys

import numpy as np

import mkpal

N = 128                             # cells a side (tools/mkworld.py)
CELLS, CTEX = 6, 10                 # the world's sections: the cells (lo, hi, shape, mat) and their top tiles
SHAPE_WATER = 6
BLOCKS = (4, 8, 16)                 # cells a block's side, for each size of rectangle
K = 7                               # classes a map's colours fall into
SB = 16                             # cells a square's side (rectangles never cross one: the game culls by square)
FAR_K, FAR_LONE = 4, 5              # the 16-cell blocks (drawn from the farthest, a mosaic of squares up close): at most this many classes, and a block with this many of its 8 neighbours alike joins them
ATM = (22, 26, 30)                  # the colour of the air (Payback's palette has a ramp of blues 193 ..)
CLOUD = (30, 30, 31)
TONE = (1.0, 0.62, 0.3)              # how bright the ground is by day, at dusk and by night
TINT = ((0, 0, 0), (2, 0, -1), (0, 1, 3))
HAZE = (0.0, 0.35, 0.75)             # how much of the ground's colour is the disc's, near .. far (see planet.c: the patch ends in the farthest)


def cell_colours(rom, pal, world):
    """(N, N, 3) the colour of each cell's top (water for water), [z][x]; and the water mask"""
    offs = struct.unpack_from('<17I', world, 36)
    cells = world[offs[CELLS]:offs[CELLS] + N * N * 6]
    ctex = struct.unpack_from('<%dH' % (N * N), world, offs[CTEX])
    cache = {}

    def tile(t):
        if t not in cache:
            a = mkpal.WATER if t == mkpal.TEX_WATER else mkpal.TILE_BANK + t * 0x400
            px = [pal[p] for p in rom[a:a + 0x400]]
            cache[t] = tuple(sum(c[k] for c in px) / len(px) for k in range(3))
        return cache[t]
    img = np.zeros((N, N, 3))
    wet = np.zeros((N, N), bool)
    for i in range(N * N):
        x, z = divmod(i, N)
        shape = cells[6 * i + 4]
        if shape == SHAPE_WATER:
            img[z, x] = tile(mkpal.TEX_WATER)
            wet[z, x] = True
        elif 0 < ctex[i] < mkpal.TILE_IDS:
            img[z, x] = tile(ctex[i])
        else:
            img[z, x] = np.array(tile(mkpal.TEX_WATER)) * 0.4          # (no top: dark)
    return img, wet


def lit(c):
    """the colour a lit planet wears for a map colour: a little brighter and more colourful, as seen through air"""
    c = np.asarray(c, float)
    g = c.mean(-1, keepdims=True)
    c = g + (c - g) * 1.25
    return np.clip(c * 1.1 + 1.0, 0, 31)


BIOME = {'sea': (3, 11, 24), 'grass': (7, 17, 6), 'wood': (4, 11, 5), 'sand': (23, 20, 12), 'clay': (19, 11, 7),
         'town': (17, 17, 18), 'ice': (28, 29, 31)}


def planet_rgb(c):
    """what a map colour is as ground seen from orbit: nearer a coast, a field, a desert, a town, so the planets read as planets"""
    r, g, b = c
    lum = (r + g + b) / 3
    if b > r + 4 and b >= g - 1:
        k = 'sea'
    elif g > r + 1.5 and g > b + 2:
        k = 'grass' if lum > 9 else 'wood'
    elif r > g + 3.5 and r > b + 6:
        k = 'clay'
    elif r > b + 3 and lum > 11:
        k = 'sand'
    elif lum > 24:
        k = 'ice'
    else:
        k = 'town'
    return 0.6 * np.array(BIOME[k]) + 0.4 * np.asarray(c, float)


def kmeans(x, k):
    # (a fixed start: the farthest colours first, so a map's look never changes between builds)
    cen = [x[np.argmax(((x - x.mean(0)) ** 2).sum(1))]]
    while len(cen) < k:
        d = np.min([((x - c) ** 2).sum(1) for c in cen], 0)
        cen.append(x[np.argmax(d)])
    cen = np.array(cen)
    for _ in range(14):
        a = np.argmin(((x[:, None] - cen[None]) ** 2).sum(2), 1)
        for j in range(k):
            if (a == j).any():
                cen[j] = x[a == j].mean(0)
    return cen


def nearest(pal, rgb, lo=1, hi=256):
    best, bi = 1e9, 1
    for i in range(lo, hi):
        p = pal[i]
        d = 3 * (p[0] - rgb[0]) ** 2 + 4 * (p[1] - rgb[1]) ** 2 + 2 * (p[2] - rgb[2]) ** 2
        if d < best:
            best, bi = d, i
    return bi


def blocks_of(img, s):
    n = N // s
    return img.reshape(n, s, n, s, 3).mean((1, 3))


def rects(cls, per):
    """cls: (n, n) classes. Merge same-class blocks into rectangles inside each square of `per` blocks. -> per-square lists"""
    n = cls.shape[0]
    done = np.zeros((n, n), bool)
    out = [[] for _ in range((n // per) ** 2)]
    for sz in range(0, n, per):
        for sx in range(0, n, per):
            for z in range(sz, sz + per):
                for x in range(sx, sx + per):
                    if done[z, x]:
                        continue
                    c = cls[z, x]
                    w = 1
                    while x + w < sx + per and not done[z, x + w] and cls[z, x + w] == c:
                        w += 1
                    h = 1
                    while z + h < sz + per and all(not done[z + h, x + i] and cls[z + h, x + i] == c for i in range(w)):
                        h += 1
                    done[z:z + h, x:x + w] = True
                    out[(sz // per) * (n // per) + sx // per].append((x, z, w << 4 | h, int(c)))
    return out


def coarsen(cls, cen, dom):
    """the 16-cell blocks as continents rather than a mosaic: the smallest classes fold into the nearest colour left (the disc's
    class stays) down to FAR_K, then lone blocks join their neighbours. The fewer, bigger rectangles are far less to draw."""
    cls = cls.copy()
    area = np.bincount(cls.ravel(), minlength=K).astype(float)
    alive = [j for j in range(K) if area[j] > 0]
    pr = [planet_rgb(cen[j]) for j in range(K)]
    while len(alive) > FAR_K:
        small = min((j for j in alive if j != dom), key=lambda j: area[j])
        to = min((j for j in alive if j != small), key=lambda j: ((pr[j] - pr[small]) ** 2).sum())
        cls[cls == small] = to
        area[to] += area[small]
        area[small] = 0
        alive.remove(small)
    for _ in range(2):
        pad = np.pad(cls, 1, mode='edge')
        out = cls.copy()
        for z in range(cls.shape[0]):
            for x in range(cls.shape[1]):
                nb = [pad[z + dz, x + dx] for dz in range(3) for dx in range(3) if dz != 1 or dx != 1]
                k = max(set(nb), key=nb.count)
                if nb.count(k) >= FAR_LONE and k != cls[z, x]:
                    out[z, x] = k
        cls = out
    return cls


def rnd0(m, k):
    x = (m * 2654435761 + k * 40503 + 12345) & 0xffffffff
    x = (x ^ (x >> 15)) * 2246822519 & 0xffffffff
    return (x ^ (x >> 13)) >> 4


def one(rom, pal, world, m):
    img, wet = cell_colours(rom, pal, world)
    b0 = blocks_of(img, BLOCKS[0])
    sm = b0.copy()                                          # (a little smoothing: fewer, bigger regions)
    sm[1:-1, 1:-1] = (4 * b0[1:-1, 1:-1] + b0[:-2, 1:-1] + b0[2:, 1:-1] + b0[1:-1, :-2] + b0[1:-1, 2:]) / 8
    cen = kmeans(sm.reshape(-1, 3), K)
    cls_by = []
    for s in BLOCKS:
        bl = blocks_of(img, s)
        cls_by.append(np.argmin(((bl[:, :, None] - cen[None, None]) ** 2).sum(3), 2))
    c0 = cls_by[0]                                          # (a lone block among others of one class joins them)
    pad = np.pad(c0, 1, mode='edge')
    for z in range(c0.shape[0]):
        for x in range(c0.shape[1]):
            nb = [pad[z + dz, x + dx] for dz in range(3) for dx in range(3) if dz != 1 or dx != 1]
            k = max(set(nb), key=nb.count)
            if nb.count(k) >= 6 and k != c0[z, x]:
                c0[z, x] = k
    # the planet's rings: the disc is the class of most of the map's edge (the land round it goes on),
    # the air blends toward the map's mean colour
    edge = np.concatenate([cls_by[1][0], cls_by[1][-1], cls_by[1][:, 0], cls_by[1][:, -1]])
    dom = np.bincount(edge, minlength=K).argmax()
    cls_by[2] = coarsen(cls_by[2], cen, dom)
    area = np.bincount(cls_by[2].ravel(), minlength=K) / cls_by[2].size
    # classes: the planet-lit colour of each centre, by haze: toward the disc's own colour, where the patch gives out into the disc
    # (the farthest band is most of the way there, so the patch's edge is lost in it)
    cols = np.zeros((9, K), int)                            # (by time of day: day, dusk, night; each by haze)
    for t_ in range(3):
        dsc = lit(planet_rgb(cen[dom])) * TONE[t_] + TINT[t_]
        for j in range(K):
            for b in range(3):
                c = (lit(planet_rgb(cen[j])) * TONE[t_] + TINT[t_]) * (1 - HAZE[b]) + dsc * HAZE[b]
                cols[3 * t_ + b, j] = nearest(pal, np.clip(c, 0, 31))
    mean = np.array(lit(img.reshape(-1, 3).mean(0)))
    disc = int(cols[1, dom])
    # (the sun: the terminator is a line over the planet, T cells from the map's middle along (sx, sz), the dusk 45 wide)
    ang = (rnd0(m, 1) % 360) * np.pi / 180
    sun = [int(round(127 * np.cos(ang))), int(round(127 * np.sin(ang))), 70 + rnd0(m, 2) % 160]
    atm_rgb = np.array(pal[199]) * 0.75 + mean * 0.25
    ring = [nearest(pal, np.array(pal[196]) * 0.8 + mean * 0.2), nearest(pal, atm_rgb), disc, nearest(pal, CLOUD, 200, 256),
            nearest(pal, np.array(CLOUD) * 0.75 + np.array((2, 0, -1)), 200, 256), nearest(pal, np.array(CLOUD) * 0.35 + np.array((0, 1, 3)), 190, 256)]
    # the surround, from the map's mix
    seed = [0x9e3779b9 * (m + 1) & 0xffffffff]

    def rnd():
        seed[0] = (seed[0] * 1664525 + 1013904223) & 0xffffffff
        return seed[0] >> 8
    cum = np.cumsum(area)
    sur = [0] * 25
    for j in range(5):
        for i in range(5):
            if (i, j) == (2, 2):
                continue
            k = int(np.searchsorted(cum, (rnd() % 1000) / 1000.0 * cum[-1]))
            sur[j * 5 + i] = min(k, K - 1)
    # (the ring next to the map goes on with the map's own edge there)
    sur[2 * 5 + 1] = int(np.bincount(cls_by[1][:, 0], minlength=K).argmax())
    sur[2 * 5 + 3] = int(np.bincount(cls_by[1][:, -1], minlength=K).argmax())
    sur[1 * 5 + 2] = int(np.bincount(cls_by[1][0], minlength=K).argmax())
    sur[3 * 5 + 2] = int(np.bincount(cls_by[1][-1], minlength=K).argmax())
    jit = []
    for j in range(6):
        for i in range(6):
            if i in (2, 3) and j in (2, 3):
                jit += [0, 0]                               # (the map's corners stay put)
            else:
                jit += [(rnd() % 57) - 28, (rnd() % 57) - 28]
    cld = []
    for i in range(8):
        cld += [rnd() % 256, rnd() % 256, 20 + rnd() % 40]
    rl = []
    for lod, s in enumerate(BLOCKS):
        if lod == 0:                                        # (the 4-cell blocks are not drawn: the lattice is 8 cells)
            rl.append([[] for _ in range((N // SB) ** 2)])
            continue
        rl.append(rects(cls_by[lod], SB // s))
    rl.append(rects(cls_by[2], cls_by[2].shape[0]))         # (from the highest, the 16-cell blocks merged across the squares)

    def sunrow(x, z, w, h, s):                              # the row of the sun's side at a rectangle's middle (day, dusk, night), as planet.c reads it
        cx, cz = (x + w / 2) * s, (z + h / 2) * s
        d = (int((cx - 64) * sun[0] + (cz - 64) * sun[1]) >> 7) - sun[2]
        return 0 if d < 0 else 1 if d < 45 else 2
    for lod in (1, 2, 3):
        s = BLOCKS[lod] if lod < 3 else BLOCKS[2]
        for sq in rl[lod]:
            for i, (x, z, wh, c) in enumerate(sq):
                sq[i] = (x, z, wh, c | sunrow(x, z, wh >> 4, wh & 15, s) << 3)
    return dict(sun=sun, cols=cols, ring=ring, sur=sur, jit=jit, cld=cld, rl=rl, cls=cls_by, cen=cen, img=img)


def main(rom_path, worlds, out, preview=None):
    rom = open(rom_path, 'rb').read() if isinstance(rom_path, str) else rom_path
    pal = mkpal.palette(rom)
    maps = [one(rom, pal, w, m) for m, w in enumerate(worlds)]
    flat = []
    sb = []
    for mp in maps:
        per = []
        for lod in range(4):
            idx = [len(flat)]
            for sq in mp['rl'][lod]:
                flat += sq
                idx.append(len(flat))
            per.append(idx + [idx[-1]] * (65 - len(idx)))
        sb.append(per)
    assert len(flat) < 65536

    def arr(v, w=16):
        return ',\n    '.join(', '.join('%d' % x for x in v[i:i + w]) for i in range(0, len(v), w))
    with open(out, 'w') as f:
        f.write("/* generated by tools/mkplanet.py from the player's Payback ROM and the maps' worlds */\n")
        f.write('#include "../../src/gba.h"\n')
        f.write('const u8 pl_col[%d][9][8] = {\n' % len(maps))
        for mp in maps:
            f.write('  {%s},\n' % ', '.join('{%s}' % ', '.join(str(int(v)) for v in row) for row in mp['cols']))
        f.write('};\nconst s16 pl_sun[%d][3] = {\n' % len(maps))
        for mp in maps:
            f.write('  {%s},\n' % ', '.join(str(v) for v in mp['sun']))
        f.write('};\nconst u8 pl_ring[%d][6] = {\n' % len(maps))
        for mp in maps:
            f.write('  {%s},\n' % ', '.join(str(v) for v in mp['ring']))
        f.write('};\nconst u8 pl_sur[%d][25] = {\n' % len(maps))
        for mp in maps:
            f.write('  {%s},\n' % ', '.join(str(v) for v in mp['sur']))
        f.write('};\nconst s8 pl_jit[%d][72] = {\n' % len(maps))
        for mp in maps:
            f.write('  {%s},\n' % ', '.join(str(v) for v in mp['jit']))
        f.write('};\nconst u8 pl_cld[%d][24] = {\n' % len(maps))
        for mp in maps:
            f.write('  {%s},\n' % ', '.join(str(v) for v in mp['cld']))
        f.write('};\nconst u16 pl_sb[%d][4][65] = {\n' % len(maps))
        for per in sb:
            f.write('  {%s},\n' % ', '.join('{%s}' % ', '.join(str(v) for v in idx) for idx in per))
        f.write('};\nconst u8 pl_rect[%d][4] = {\n    %s};\n' % (len(flat), ',\n    '.join('{%s}' % ', '.join(str(v) for v in r) for r in flat)))
    if preview:
        preview_png(maps, pal, preview)
    return len(flat)


def preview_png(maps, pal, path):
    from PIL import Image
    s = 4
    sheet = Image.new('RGB', (4 * (N * s * 2 + 8), 3 * (N * s + 8)))
    for m, mp in enumerate(maps):
        img = np.zeros((N * s, N * s * 2, 3), np.uint8)
        for lod in (0, 1):
            bs = BLOCKS[lod]
            c = mp['cls'][lod]
            for z in range(c.shape[0]):
                for x in range(c.shape[1]):
                    p = pal[mp['cols'][0, c[z, x]]]
                    img[z * bs * s:(z + 1) * bs * s, lod * N * s + x * bs * s:lod * N * s + (x + 1) * bs * s] = [v * 255 // 31 for v in p]
        sheet.paste(Image.fromarray(img), ((m % 4) * (N * s * 2 + 8), (m // 4) * (N * s + 8)))
    sheet.save(path)


if __name__ == '__main__':
    # tools/mkplanet.py PAYBACK_ROM out.c [preview.png]: the worlds are made as build.py makes them
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'payback-mod'))
    import mkworld
    from paybackmod.rom import PaybackRom
    orig = open(sys.argv[1], 'rb').read()
    r = PaybackRom(orig)
    ws = [mkworld.build(orig, merge=True, level=m, rom=r)[0] for m in range(11)]
    print(main(orig, ws, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
