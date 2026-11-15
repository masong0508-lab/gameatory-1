#!/usr/bin/env python3
"""dumpworld.py: one map's world of a Star-FlyBack build as neutral files (JSON + NPZ + PNG), with a top-down preview.

Two sources (both read the player's own files; everything written is derived data: keep it in the scratchpad):

  --rom BUILT.gba [--elf stuntfox-merge.elf]   the SFW4 blob as build.py --merge linked it into the cartridge
                                               (found through the ELF's world_table, else by its 'SFW4' magic)
  --payback PAYBACK.gba [--amiga DIR]          the blob made now by the repo's own tools (tools/mkworld.py after the
                                               same steps build.py takes: phones, the arena, the Amiga water, stunt spots)
  both                                         the two must be byte for byte the same (the check of this tool)

Output in --out (default ../world0 next to this tool), for --map N (default 0, Freedom City):
  world.bin        the SFW4 blob as is (src/world.h reads it; little endian, every field aligned: a PS1 can load it as it is)
  world.json       header, counts, section sizes, boxes, lots, ramps, loops, lines, trees/fences/props, ladders,
                   Payback's street objects, start points and phones, the tiles used
  world.npz        per cell arrays (128 x 128, index [x, z]): lo hi shape mat ctex dtex deck deck2 wall swim; per box: btex
  tiles.npz        ids, idx (n x 32 x 32 palette indices), pal555 (256 x u16, r | g << 5 | b << 10), pal (256 x RGB8), avg555
  atlas.png        those tiles, 16 a row, 32 x 32 each, 8-bit paletted (Payback's palette): PS1 8-bit CLUT ready
  atlas_rgb.png    the same in RGB
  preview.png      top-down, 8 pixels a cell, x right, z down: the tops' tiles, height shade, trees, railings, loops, phones
  preview_kinds.png  the same from the materials alone (no tiles)
  sizes.json       with --all-maps: every map's counts and bytes (of a --rom)
"""
import argparse
import json
import os
import struct
import subprocess
import sys

sys.dont_write_bytecode = True      # (the repo is read only for us: no __pycache__ there)
import numpy as np                  # noqa: E402
from PIL import Image, ImageDraw    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = '/home/user/gameatory-1'
GBA = 0x08000000
N, CELL, HBIAS, NWORLD = 128, 1024, 40, 11
TILE_BANK, TILE_IDS, TEX_WATER, WATER_IMG, PALETTE = 0x0ce0bc, 0x318, 0x317, 0x2f8de8, 0x6367a8
NEW_COLUMNS, LEVEL_TABLE = 0x800000, 0x1aa8b4
OBJ_DESC, OBJ_SIN, OBJ_COS = 0x353f00, 0x666daa, 0x669aaa
STARTS, START_COUNT, PHONE_TABLE, PHONE_COUNT = 0x1928e0, 0x193490, 0x193940, 0x193d08
SECTIONS = ('box', 'lot', 'ramp', 'loop', 'sector', 'item', 'cell', 'far', 'line', 'tree', 'ctex', 'btex', 'deck',
            'wall', 'deck2', 'dtex', 'swim')
MATS = ('sky', 'road', 'kerb', 'grass', 'plaza', 'concrete', 'glass', 'brick', 'teal', 'cream', 'steel', 'car',
        'accent', 'ship', 'glow', 'stunt')
MAT_RGB5 = [(0, 0, 0), (7, 7, 10), (19, 19, 18), (6, 17, 7), (21, 17, 12), (20, 20, 21), (8, 15, 25), (23, 10, 8),
            (5, 21, 20), (27, 25, 18), (12, 13, 17), (5, 10, 29), (31, 27, 4), (28, 28, 29), (31, 14, 3), (31, 6, 11)]
TREE_KINDS = {0: 'tree', 1: 'tree', 2: 'rail -z', 3: 'rail +x', 4: 'rail +z', 5: 'rail -x', 6: 'bench', 7: 'bin',
              8: 'lamp', 9: 'live object (post only)'}
OBJ_NAMES = {1: 'traffic light', 2: 'lamp', 3: 'rock', 4: 'monument', 5: 'tree', 6: 'crate', 7: 'tree', 8: 'tree',
             14: 'phone', 15: 'beacon', 16: 'beacon', 17: 'chimney', 18: 'bench', 19: 'phone (ringing)', 20: 'radar',
             25: 'tree', 32: 'shrub', 33: 'lamp', 36: 'lamp'}


# ---- finding and making the blob ----
def blob_at(rom, o):
    """The SFW4 blob that starts at rom[o] (its length from its own header)."""
    assert rom[o:o + 4] == b'SFW4', 'no world at %x' % o
    first = struct.unpack_from('<I', rom, o + 36)[0]
    nsec = (first - 36) // 4
    assert nsec == len(SECTIONS), 'expected %d sections, found %d' % (len(SECTIONS), nsec)
    swim = struct.unpack_from('<I', rom, o + 36 + 4 * (nsec - 1))[0]
    nlad = struct.unpack_from('<H', rom, o + swim + N * N)[0]
    return bytes(rom[o:o + swim + N * N + 4 + 8 * nlad])


def worlds_in_rom(rom, elf=None):
    """Offsets of the 11 worlds in a built cartridge, in map order."""
    scan, o = [], rom.find(b'SFW4', 0x800000)
    while o >= 0:
        if o % 4 == 0 and struct.unpack_from('<I', rom, o + 36)[0] == 36 + 4 * len(SECTIONS):
            scan.append(o)
        o = rom.find(b'SFW4', o + 4)
    if elf:
        nm = subprocess.run(['llvm-nm', elf], capture_output=True, text=True).stdout
        sym = {p[2]: int(p[0], 16) for p in (l.split() for l in nm.splitlines()) if len(p) == 3}
        tab = [p - GBA for p in struct.unpack_from('<%dI' % NWORLD, rom, sym['world_table'] - GBA)]
        assert tab == scan, 'world_table and the SFW4 blobs found disagree'
        return tab
    assert len(scan) == NWORLD, 'expected %d worlds, found %d' % (NWORLD, len(scan))
    return scan                    # (build.py allocates them in map order)


def repo_paths(repo):
    for p in (os.path.join(repo, 'stuntfox', 'tools'), os.path.join(repo, 'payback-mod')):
        if p not in sys.path:
            sys.path.insert(0, p)


def build_blob(payback, amiga, level, repo):
    """The world as build.py --merge makes it: the same steps before mkworld.build (build_merge)."""
    repo_paths(repo)
    import mkworld, mksolo, s2build, amiga_classify, stunt_spots
    from paybackmod.rom import PaybackRom
    orig = open(payback, 'rb').read()
    rom = PaybackRom(orig)
    mksolo.offer_every_map(rom.d)
    mksolo.add_phones(rom)
    loops = s2build.pre_world(rom, orig)
    if amiga:
        mkworld.AMIGA = {g: amiga_classify.classify(amiga, g) for g in range(4)}
        stunt_spots.add(rom)
    data, stats = mkworld.build(orig, merge=True, level=level, rom=rom, loops=loops)
    return data, stats, bytes(rom.d)


# ---- the blob as arrays ----
def parse(blob):
    h = struct.unpack_from('<4s7Ii', blob, 0)
    cnt = dict(zip(('box', 'lot', 'ramp', 'loop', 'item', 'line', 'tree'), h[1:8]))
    off = list(struct.unpack_from('<%dI' % len(SECTIONS), blob, 36)) + [len(blob)]
    sec = {n: (off[i], off[i + 1] - off[i]) for i, n in enumerate(SECTIONS)}
    at = lambda n: sec[n][0]
    w = dict(magic=h[0].decode(), yoff=h[8], counts=cnt, sections=sec)
    w['box'] = [struct.unpack_from('<BBBBhBb', blob, at('box') + 8 * i) for i in range(cnt['box'])]
    w['lot'] = [struct.unpack_from('<BBBBB', blob, at('lot') + 5 * i) for i in range(cnt['lot'])]
    w['ramp'] = [struct.unpack_from('<BBBBhhBB', blob, at('ramp') + 10 * i) for i in range(cnt['ramp'])]
    w['loop'] = [struct.unpack_from('<iiBxhh', blob, at('loop') + 16 * i) for i in range(cnt['loop'])]
    w['sector'] = np.frombuffer(blob, '<u2', 512, at('sector')).reshape(16, 16, 2)      # [sx, sz] -> (start, count)
    w['item'] = np.frombuffer(blob, '<u2', cnt['item'], at('item'))                    # kind << 13 | index
    cell = np.frombuffer(blob, np.dtype([('lo', '<i2'), ('hi', '<i2'), ('shape', 'u1'), ('mat', 'u1')]), N * N, at('cell'))
    w['cell'] = cell.reshape(N, N)
    w['far'] = np.frombuffer(blob, np.dtype([('mat', 'u1'), ('pad', 'u1'), ('h', '<i2')]), 256, at('far')).reshape(16, 16)
    w['line'] = [struct.unpack_from('<BBBB', blob, at('line') + 4 * i) for i in range(cnt['line'])]
    w['tree'] = [struct.unpack_from('<HHBBbB', blob, at('tree') + 8 * i) for i in range(cnt['tree'])]
    u = at('tree') + 8 * cnt['tree']
    nu = struct.unpack_from('<H', blob, u)[0]
    w['undrawn'] = list(struct.unpack_from('<%dH' % nu, blob, u + 2))                  # cell << 2 | record
    w['ctex'] = np.frombuffer(blob, '<u2', N * N, at('ctex')).reshape(N, N)
    w['btex'] = np.frombuffer(blob, '<u2', 16 * cnt['box'], at('btex')).reshape(cnt['box'], 4, 4)
    w['deck'] = np.frombuffer(blob, 'i1', 4 * N * N, at('deck')).reshape(N, N, 4)
    w['wall_bits'] = np.frombuffer(blob, 'u1', N * N, at('wall')).reshape(N, N)
    w['wall_range'] = np.frombuffer(blob, 'i1', 2 * N * N, at('wall') + N * N).reshape(N, N, 2)
    w['deck2'] = np.frombuffer(blob, 'i1', 4 * N * N, at('deck2')).reshape(N, N, 4)
    w['dtex'] = np.frombuffer(blob, '<u2', N * N, at('dtex')).reshape(N, N)
    w['swim'] = np.frombuffer(blob, 'u1', N * N, at('swim')).reshape(N, N)
    nl = struct.unpack_from('<H', blob, at('swim') + N * N)[0]
    w['ladder'] = [struct.unpack_from('<BBBxhh', blob, at('swim') + N * N + 4 + 8 * i) for i in range(nl)]
    return w


def tile_ids(w):
    ids = set(np.unique(w['ctex'])) | set(np.unique(w['dtex'])) | set(np.unique(w['btex']))
    return sorted(int(t) for t in ids if t < TILE_IDS)


# ---- Payback's tiles and palette (from the cartridge, below 8 MiB: the same bytes in a built one) ----
def palette(rom):
    """(pal555 as the screen has it: r | g << 5 | b << 10, RGB8). The ROM keeps red at bit 10."""
    raw = np.frombuffer(rom, '<u2', 256, PALETTE).astype(np.uint16)
    r, g, b = raw >> 10 & 31, raw >> 5 & 31, raw & 31
    rgb = np.stack([r, g, b], 1).astype(np.uint8)
    return (r | g << 5 | b << 10).astype(np.uint16), (rgb << 3 | rgb >> 2).astype(np.uint8)


def tile(rom, tid):
    a = WATER_IMG if tid == TEX_WATER else TILE_BANK + tid * 0x400
    return np.frombuffer(rom, 'u1', 0x400, a).reshape(32, 32)       # [row = z or down, column = x or along]


# ---- Payback's own records, for the street objects, starts and phones ----
def grid_of(rom, level, repo):
    repo_paths(repo)
    from paybackmod.mapcodec import decode, COLUMN_BASE
    g, _ = decode(rom, level)
    return [(p - COLUMN_BASE) // 60 for p in g]


def column(rom, idx):
    return rom[NEW_COLUMNS + 60 * idx:NEW_COLUMNS + 60 * idx + 60]


def record_top(col, k, street):
    """Units (our y) of the top of record k at the cell's middle (mkworld.pb_slope)."""
    base = 0
    for j in range(k + 1):
        h0, h1 = struct.unpack_from('<hh', col, 20 * j + 4)
        if j < k:
            base += h0
    shape, typ = col[20 * k + 8], col[20 * k + 11] & 0x70
    t0, t1 = base + h0, base + h1
    top = t1 if typ == 0x40 else t0 if shape == 1 else (t0 + t1) // 2
    return (top - street) * 8


def street_objects(rom, grid, street):
    """Every object Payback's map holds (byte 1 of a floor record; byte 0 its turn), where Payback puts it."""
    out = []
    for i, c in enumerate(grid):
        col = column(rom, c)
        for k in range(3):
            turn, typ = col[20 * k], col[20 * k + 1]
            if not typ or not col[20 * k + 8]:
                continue
            ox, oy, r = struct.unpack_from('<hhh', rom, OBJ_DESC + typ * 0x3c - 0x14)
            a = turn * 5760 // 256
            c_, s_ = struct.unpack_from('<h', rom, OBJ_COS + 2 * a)[0], struct.unpack_from('<h', rom, OBJ_SIN + 2 * a)[0]
            x, z = divmod(i, N)
            out.append(dict(type=typ, name=OBJ_NAMES.get(typ, ''), cell=[x, z], record=k, turn=turn,
                            x=x * CELL + CELL // 2 + ((c_ * ox + s_ * oy) >> 9),
                            z=z * CELL + CELL // 2 + ((c_ * oy - s_ * ox) >> 9),
                            y=record_top(col, k, street), radius=r // 4))
    return out


def places(rom, grid, level, street, table, count, per, bias):
    n = min(struct.unpack_from('<b', rom, count + level)[0] + bias, per)
    out = []
    for i in range(max(n, 0)):
        x, z, k = rom[table + 4 * (per * level + i):][:3]
        out.append(dict(cell=[x, z], record=k, y=record_top(column(rom, grid[x * N + z]), min(k, 2), street)))
    return out


# ---- pictures ----
def rgb8(c5):
    return tuple(v << 3 | v >> 2 for v in c5)


def preview(w, rom, pal, S=8, tiles=True, extra=None):
    """Top-down: x right, z down (a true plan: facing +z, +x is on your left)."""
    img = np.zeros((N * S, N * S, 3), np.float32)
    cell = w['cell']
    top = cell['hi'].astype(np.int32).copy()
    topmat = cell['mat'].astype(np.int32).copy()
    decked = np.zeros((N, N), bool)
    for x0, z0, x1, z1, h, mat, base in w['box']:
        if base:                                   # a deck: over whatever the cells have
            decked[x0:x1, z0:z1] = True
            sl = (slice(x0, x1), slice(z0, z1))
            topmat[sl] = np.where(h >= top[sl], mat & 15, topmat[sl])
            top[sl] = np.maximum(top[sl], h)
    small = {}

    def tex(tid):
        if tid not in small:
            t = pal[tile(rom, tid)].astype(np.float32)
            small[tid] = t.reshape(S, 32 // S, S, 32 // S, 3).mean((1, 3))
        return small[tid]
    for x in range(N):
        for z in range(N):
            tid = w['dtex'][x, z] if decked[x, z] else w['ctex'][x, z]
            if tiles and tid < TILE_IDS:
                px = tex(int(tid))
            else:
                m = topmat[x, z]
                if cell['shape'][x, z] == 6 and not decked[x, z]:
                    m = 6
                px = np.array(rgb8(MAT_RGB5[m]), np.float32)
            shade = 0.66 + 0.34 * min(1.0, max(0.0, (top[x, z] + 512) / 4096))
            img[z * S:(z + 1) * S, x * S:(x + 1) * S] = px * shade
    # a dark line where the top steps by more than a kerb: the outlines of buildings, decks, pits
    for x in range(N):
        for z in range(N):
            if x + 1 < N and abs(int(top[x, z]) - int(top[x + 1, z])) >= 192:
                img[z * S:(z + 1) * S, (x + 1) * S - 1] *= 0.45
            if z + 1 < N and abs(int(top[x, z]) - int(top[x, z + 1])) >= 192:
                img[(z + 1) * S - 1, x * S:(x + 1) * S] *= 0.45
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    k = S / CELL
    for x0, z0, x1, z1, h0, h1, dr, mat in w['ramp']:          # a tick on a slope's high side
        if h0 != h1:
            e = {2: (x0, z1, x1, z1), 3: (x1, z0, x1, z1), 4: (x0, z0, x1, z0), 5: (x0, z0, x0, z1)}[dr & 7]
            d.line([e[0] * S, e[1] * S, e[2] * S, e[3] * S], fill=(255, 255, 255))
    for x, z, h, kind, base, r in w['tree']:
        if kind < 2:
            px, pz, rr = x * 4 * k, z * 4 * k, max(1.5, max(h * 3, r * 4) * k)
            d.ellipse([px - rr, pz - rr, px + rr, pz + rr], fill=(24, 96 + 40 * kind, 32))
        elif kind < 6:
            cx, e = x & 127, kind - 2
            a = ((0, 0, 1, 0), (1, 0, 1, 1), (1, 1, 0, 1), (0, 1, 0, 0))[e]
            d.line([(cx + a[0]) * S, (z + a[1]) * S, (cx + a[2]) * S, (z + a[3]) * S],
                   fill=(255, 160, 0) if x & 128 else (230, 230, 240))
        else:
            px, pz = x * 4 * k, z * 4 * k
            d.rectangle([px - 1, pz - 1, px + 1, pz + 1], fill={6: (150, 90, 40), 7: (60, 120, 220), 8: (255, 255, 200)}.get(kind, (255, 0, 255)))
    for x, z, dr, r, wd in w['loop']:
        dx, dz = ((0, 1), (1, 0), (0, -1), (-1, 0))[dr & 3]
        d.line([x * k, z * k, (x + dx * 2 * r) * k, (z + dz * 2 * r) * k], fill=(255, 120, 0), width=3)
    for x, z, e, lo, hi in w['ladder']:
        a = ((0, 0, 1, 0), (1, 0, 1, 1), (1, 1, 0, 1), (0, 1, 0, 0))[e]
        d.line([(x + a[0]) * S, (z + a[1]) * S, (x + a[2]) * S, (z + a[3]) * S], fill=(255, 255, 0), width=3)
    for p in (extra or {}).get('phones', []):
        x, z = p['cell']
        d.rectangle([x * S + 1, z * S + 1, x * S + S - 2, z * S + S - 2], outline=(255, 0, 0))
    for p in (extra or {}).get('starts', []):
        x, z = p['cell']
        d.point([x * S + S // 2, z * S + S // 2], fill=(0, 255, 255))
    return im


def atlas(rom, ids, pal, cols=16):
    rows = (len(ids) + cols - 1) // cols
    a = np.zeros((rows * 32, cols * 32), np.uint8)
    for n, t in enumerate(ids):
        a[n // cols * 32:n // cols * 32 + 32, n % cols * 32:n % cols * 32 + 32] = tile(rom, t)
    im = Image.fromarray(a, 'P')
    im.putpalette(pal.reshape(-1).tolist())
    return im, a


def dump(blob, rom, level, out, repo, source):
    os.makedirs(out, exist_ok=True)
    w = parse(blob)
    pal555, pal = palette(rom)
    ids = tile_ids(w)
    street = 0x100 - w['yoff'] // 8
    grid = grid_of(rom, level, repo) if len(rom) > NEW_COLUMNS else None
    extra = {}
    if grid:
        extra['objects'] = street_objects(rom, grid, street)
        extra['starts'] = places(rom, grid, level, street, STARTS, START_COUNT, 68, 1)
        extra['phones'] = places(rom, grid, level, street, PHONE_TABLE, PHONE_COUNT, 22, 0)
    open(os.path.join(out, 'world.bin'), 'wb').write(blob)
    trees, rails, props, posts = [], [], [], []
    for x, z, h, kind, base, r in w['tree']:
        if kind < 2:
            trees.append(dict(x=x * 4, z=z * 4, y=base * 64, height=h * 8, kind=kind, radius=r * 4))
        elif kind < 6:
            rails.append(dict(cell=[x & 127, z], edge=kind - 2, one_way=x >> 7, y=((base << 8) | h) << 5))
        elif kind < 9:
            props.append(dict(x=x * 4, z=z * 4, y=base * 64, kind=TREE_KINDS[kind], turn=h, radius=r * 4))
        else:
            posts.append(dict(x=x * 4, z=z * 4, y=base * 64, height=h * 8, radius=r * 4))
    js = dict(
        format='sfworld-dump-1', map=level, source=source, magic=w['magic'], bytes=len(blob), yoff=w['yoff'],
        units='1024 = one cell (about 8 m); x = Payback x, z = Payback y, y up; cell index x * 128 + z; edges and box '
              'sides in the order -z, +x, +z, -x',
        counts=dict(w['counts'], ladder=len(w['ladder']), undrawn=len(w['undrawn'])),
        sections={n: dict(offset=o, bytes=b) for n, (o, b) in w['sections'].items()},
        materials=[dict(id=i, name=n, rgb5=MAT_RGB5[i]) for i, n in enumerate(MATS)],
        boxes=[dict(x0=b[0], z0=b[1], x1=b[2], z1=b[3], top=b[4], bottom=b[6] * 64, mat=b[5] & 15, hidden_sides=b[5] >> 4)
               for b in w['box']],
        lots=[dict(x0=l[0], z0=l[1], x1=l[2], z1=l[3], mat=l[4]) for l in w['lot']],
        ramps=[dict(x0=r[0], z0=r[1], x1=r[2], z1=r[3], lo=r[4], hi=r[5], rises=('+z', '+x', '-z', '-x')[(r[6] & 7) - 2]
                    if 2 <= r[6] & 7 <= 5 else 'flat', on_deck=r[6] >> 7, mat=r[7]) for r in w['ramp']],
        loops=[dict(x=l[0], z=l[1], dir=l[2], radius=l[3], width=l[4]) for l in w['loop']],
        lines=[dict(at=l[0], start=l[1], end=l[2], along='x' if l[3] & 1 else 'z', crossings=l[3] >> 1) for l in w['line']],
        trees=trees, rails=rails, props=props, live_posts=posts,
        ladders=[dict(cell=[l[0], l[1]], edge=l[2], lo=l[3], hi=l[4]) for l in w['ladder']],
        undrawn=w['undrawn'],
        far=[[int(w['far'][sx, sz]['mat']), int(w['far'][sx, sz]['h'])] for sx in range(16) for sz in range(16)],
        tiles=dict(size=32, bits=8, ids=ids, atlas_columns=16, water_id=TEX_WATER,
                   rom_bank='0x%x + id * 0x400' % TILE_BANK, water_texels='0x%x' % WATER_IMG, palette_rom='0x%x' % PALETTE),
        **extra)
    json.dump(js, open(os.path.join(out, 'world.json'), 'w'), separators=(',', ':'))
    c = w['cell']
    np.savez_compressed(os.path.join(out, 'world.npz'), lo=c['lo'], hi=c['hi'], shape=c['shape'], mat=c['mat'],
                        ctex=w['ctex'], dtex=w['dtex'], deck=w['deck'], deck2=w['deck2'], wall_bits=w['wall_bits'],
                        wall_range=w['wall_range'], swim=w['swim'], btex=w['btex'],
                        box=np.array(w['box'], np.int32), lot=np.array(w['lot'], np.int32),
                        ramp=np.array(w['ramp'], np.int32), tree=np.array(w['tree'], np.int32),
                        sector=w['sector'], item=w['item'])
    im, _ = atlas(rom, ids, pal)
    im.save(os.path.join(out, 'atlas.png'))
    im.convert('RGB').save(os.path.join(out, 'atlas_rgb.png'))
    idx = np.stack([tile(rom, t) for t in ids])
    lin = pal.astype(np.float64)
    avg = []
    for t in idx:                                   # (the average of what is not see-through, as tools/mkpal.py)
        px = t[t > 0]
        m = lin[px].mean(0) if len(px) else np.zeros(3)
        r, g, b = (int(v) >> 3 for v in m)
        avg.append(r | g << 5 | b << 10)
    np.savez_compressed(os.path.join(out, 'tiles.npz'), ids=np.array(ids, np.uint16), idx=idx, pal555=pal555, pal=pal,
                        avg555=np.array(avg, np.uint16))
    preview(w, rom, pal, extra=extra).save(os.path.join(out, 'preview.png'))
    preview(w, rom, pal, tiles=False, extra=extra).save(os.path.join(out, 'preview_kinds.png'))
    ncol = [len(np.unique(t)) for t in idx]
    return dict(counts=js['counts'], bytes=len(blob), tiles=len(ids), tiles_16_colours_or_fewer=sum(n <= 16 for n in ncol),
                most_colours=max(ncol), objects=len(extra.get('objects', [])), starts=len(extra.get('starts', [])),
                phones=len(extra.get('phones', [])))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', help='a cartridge built by build.py --merge')
    ap.add_argument('--elf', help='its stuntfox-merge.elf (world_table)')
    ap.add_argument('--payback', help="the player's Payback ROM: build the world with the repo's tools")
    ap.add_argument('--amiga', help="with --payback: the player's Amiga Payback folder, as build.py --amiga")
    ap.add_argument('--repo', default=REPO)
    ap.add_argument('--map', type=int, default=0)
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'world0'))
    ap.add_argument('--all-maps', action='store_true', help='with --rom: sizes.json for all 11 maps')
    a = ap.parse_args()
    if not (a.rom or a.payback):
        ap.error('give --rom, --payback or both')
    blob = rom = None
    src = []
    if a.rom:
        rom = open(a.rom, 'rb').read()
        offs = worlds_in_rom(rom, a.elf)
        blob = blob_at(rom, offs[a.map])
        src.append('%s world %d at 0x%08x' % (os.path.basename(a.rom), a.map, GBA + offs[a.map]))
        if a.all_maps:
            sizes = []
            for m, o in enumerate(offs):
                b = blob_at(rom, o)
                w = parse(b)
                sizes.append(dict(map=m, address='0x%08x' % (GBA + o), bytes=len(b), yoff=w['yoff'], tiles=len(tile_ids(w)),
                                  counts=dict(w['counts'], ladder=len(w['ladder'])),
                                  sections={n: s[1] for n, s in w['sections'].items()}))
                print('map %2d  0x%08x  %6d bytes  %s  tiles %d' % (m, GBA + o, len(b), sizes[-1]['counts'], sizes[-1]['tiles']))
            used = sorted(set().union(*(tile_ids(parse(blob_at(rom, o))) for o in offs)))
            os.makedirs(a.out, exist_ok=True)
            json.dump(dict(maps=sizes, total=sum(s['bytes'] for s in sizes), tiles_all_maps=len(used)),
                      open(os.path.join(a.out, 'sizes.json'), 'w'), indent=1)
            print('all maps: %d bytes, %d different tiles' % (sum(s['bytes'] for s in sizes), len(used)))
    if a.payback:
        made, stats, prom = build_blob(a.payback, a.amiga, a.map, a.repo)
        src.append('mkworld.build(%s%s, level %d)' % (os.path.basename(a.payback), ' + amiga' if a.amiga else '', a.map))
        if blob is not None:
            same = made == blob
            print('built by the repo\'s tools: %d bytes; in the cartridge: %d bytes; %s' % (
                len(made), len(blob), 'IDENTICAL' if same else 'DIFFERENT'))
            if not same:
                return 1
        else:
            blob, rom = made, prom
    info = dump(blob, rom, a.map, a.out, a.repo, '; '.join(src))
    print('map %d -> %s: %s' % (a.map, os.path.abspath(a.out), info))
    return 0


if __name__ == '__main__':
    sys.exit(main())
