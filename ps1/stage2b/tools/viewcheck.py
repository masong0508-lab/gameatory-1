#!/usr/bin/env python3
"""viewcheck.py: a street-level picture from the dumped world alone (world.npz, world.json, tiles.npz of dumpworld.py),
through the GBA game's own camera, to set beside a GBA screenshot. It proves the dump holds what the game draws: heights,
boxes, which tile is on which side of which box and which way up, the tops' tiles, decks, water.

    viewcheck.py DIR OUT.png [--cam x y z] [--yaw DEG] [--pitch DEG] [--gba SHOT.png]

A ray per pixel (240 x 160, screen x = 120 + 136 x / z as src/render.h) walked cell by cell over the 128 x 128 grid: the
cell's top (flat, sloped or water), its sides (a box's tiles: side -z, +x, +z, -x, a tile for each cell along it from the
box's low corner, 32 texels to 1024 units, rows from the box's top down, as src/citydraw.c wall() and src/tex.c), and the
decks over it. No trees, railings, props or models. Not a renderer to keep: a check.
"""
import argparse
import json
import math
import os

import numpy as np
from PIL import Image

N, CELL, HBIAS, W, H, FOCAL = 128, 1024, 40, 240, 160, 136
SHADE = (0.58, 0.72, 0.86, 1.0)                 # light levels 0..3 (tools/mkpal.py)
SIDE_LIGHT = (1, 2, 1, 0)                       # sides -z, +x, +z, -x (citydraw.c draw_box)
MAT_RGB5 = [(0, 0, 0), (7, 7, 10), (19, 19, 18), (6, 17, 7), (21, 17, 12), (20, 20, 21), (8, 15, 25), (23, 10, 8),
            (5, 21, 20), (27, 25, 18), (12, 13, 17), (5, 10, 29), (31, 27, 4), (28, 28, 29), (31, 14, 3), (31, 6, 11)]
SKY = np.array((120, 170, 230), np.float32)


def load(d):
    z = np.load(os.path.join(d, 'world.npz'))
    t = np.load(os.path.join(d, 'tiles.npz'))
    w = {k: z[k] for k in z.files}
    slot = np.full(0x400, -1, np.int32)
    slot[t['ids']] = np.arange(len(t['ids']))
    w['tex'] = t['pal'][t['idx']].astype(np.float32)          # n x 32 x 32 x 3
    w['slot'] = slot
    # which box stands on each cell (a building), and which is the deck over it
    bld = np.full((N, N), -1, np.int32)
    dk = np.full((N, N), -1, np.int32)
    dk2 = np.full((N, N), -1, np.int32)
    for j, (x0, z0, x1, z1, h, mat, base) in enumerate(w['box']):
        if base == 0 and w['hi'][x0, z0] == h and w['shape'][x0, z0] == 1:
            bld[x0:x1, z0:z1] = j
        elif (int(w['deck'][x0, z0, 2]) + HBIAS) * 64 == h and (w['deck'][x0, z0, 0] | w['deck'][x0, z0, 1]):
            dk[x0:x1, z0:z1] = j
        else:
            dk2[x0:x1, z0:z1] = j
    w['bld'], w['dk'], w['dk2'] = bld, dk, dk2
    return w


def render(w, pos, r, u, f):
    px, py = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    a, b = (px - W / 2).ravel(), (H / 2 - py).ravel()
    d = a[:, None] * r + b[:, None] * u + FOCAL * f              # ray directions (world)
    n = len(a)
    ox, oy, oz = pos
    dx, dy, dz = d[:, 0], d[:, 1], d[:, 2]
    dx = np.where(np.abs(dx) < 1e-6, 1e-6, dx)
    dz = np.where(np.abs(dz) < 1e-6, 1e-6, dz)
    cx, cz = np.full(n, int(ox // CELL)), np.full(n, int(oz // CELL))
    sx, sz = np.where(dx > 0, 1, -1), np.where(dz > 0, 1, -1)
    tmx = ((cx + (sx > 0)) * CELL - ox) / dx
    tmz = ((cz + (sz > 0)) * CELL - oz) / dz
    tdx, tdz = CELL / np.abs(dx), CELL / np.abs(dz)
    t0 = np.zeros(n)
    face = np.full(n, -1)                                        # the side of the cell the ray came in through
    out = np.tile(SKY, (n, 1))
    live = np.ones(n, bool)
    box, btex, slot, tex = w['box'], w['btex'], w['slot'], w['tex']

    def texel(tid, uu, vv, fallback):
        """colour of tile tid at texel (column uu, row vv), or the fallback colour where there is no tile"""
        s = np.where(tid < 0x400, slot[np.minimum(tid, 0x3ff)], -1)
        c = tex[np.maximum(s, 0), vv.astype(int) & 31, uu.astype(int) & 31]
        return np.where((s >= 0)[:, None], c, fallback)

    def mat_rgb(m):
        return (np.array(MAT_RGB5, np.float32)[m] * 8.2)

    def wall(i, t, y, j, fc, top):
        """a hit on side fc of box j at ray parameter t (rays i)"""
        hx, hz = ox + dx[i] * t, oz + dz[i] * t
        along_x = (fc % 2 == 0)
        s = np.where(along_x, hx - box[j, 0] * CELL, hz - box[j, 1] * CELL)
        k = np.clip((s // CELL).astype(int), 0, 3)
        tid = btex[j, fc, k].astype(int)
        tid = np.where(tid >= 0x400, np.where(btex[j, fc, 0] < 0x400, btex[j, fc, 0], btex[j, fc, 1]).astype(int), tid)
        c = texel(tid, s / 32, (top - y) / 32, mat_rgb(box[j, 5] & 15))
        return c * np.array(SHADE)[np.array(SIDE_LIGHT)[fc]][:, None]

    for _ in range(200):
        i = np.nonzero(live)[0]
        if not len(i):
            break
        t1 = np.minimum(tmx[i], tmz[i])
        x, z = cx[i], cz[i]
        inside = (x >= 0) & (x < N) & (z >= 0) & (z < N)
        xi, zi = np.clip(x, 0, N - 1), np.clip(z, 0, N - 1)
        lo, hi, shp = w['lo'][xi, zi].astype(float), w['hi'][xi, zi].astype(float), w['shape'][xi, zi]
        lo, hi = np.where(inside, lo, 0), np.where(inside, hi, 0)
        shp = np.where(inside, shp, 1)

        def top_at(t):
            fx = np.clip((ox + dx[i] * t) / CELL - x, 0, 1)
            fz = np.clip((oz + dz[i] * t) / CELL - z, 0, 1)
            k = np.select([shp == 2, shp == 3, shp == 4, shp == 5], [fz, fx, 1 - fz, 1 - fx], 1.0)
            return lo + (hi - lo) * k
        y0, y1 = oy + dy[i] * t0[i], oy + dy[i] * t1
        g0, g1 = y0 - top_at(t0[i]), y1 - top_at(t1)
        done = np.zeros(len(i), bool)
        col = np.zeros((len(i), 3), np.float32)
        # decks over the cell: a slab bottom..top
        for dname, bname in (('deck', 'dk'), ('deck2', 'dk2')):
            dd = w[dname][xi, zi].astype(int)
            has = inside & ((dd[:, 0] | dd[:, 1]) != 0) & ~done
            db, dt = (dd[:, 0] + HBIAS) * 64.0, (dd[:, 2] + HBIAS) * 64.0          # (its low end: slopes drawn flat)
            j = w[bname][xi, zi]
            side = has & (face[i] >= 0) & (y0 > db) & (y0 < dt) & (j >= 0)
            if side.any():
                q = np.nonzero(side)[0]
                col[q] = wall(i[q], t0[i][q], y0[q], j[q], face[i][q], dt[q])
                done |= side
            tt = t0[i] + (t1 - t0[i]) * (y0 - dt) / np.where(y0 - y1 == 0, 1, y0 - y1)
            ontop = has & ~done & (y0 >= dt) & (y1 < dt) & (g0 >= 0) & (oy + dy[i] * tt > top_at(tt))
            if ontop.any():
                q = np.nonzero(ontop)[0]
                hx, hz = ox + dx[i[q]] * tt[q], oz + dz[i[q]] * tt[q]
                m = np.where(j[q] >= 0, box[np.maximum(j[q], 0), 5] & 15, 5)
                col[q] = texel(w['dtex'][xi[q], zi[q]].astype(int), hx / 32, hz / 32, mat_rgb(m))
                done |= ontop
            tb = t0[i] + (t1 - t0[i]) * (y0 - db) / np.where(y0 - y1 == 0, 1, y0 - y1)
            under = has & ~done & (y0 <= db) & (y1 > db)
            if under.any():
                q = np.nonzero(under)[0]
                m = np.where(j[q] >= 0, box[np.maximum(j[q], 0), 5] & 15, 5)
                col[q] = mat_rgb(m) * SHADE[0]
                done |= under
        # the cell's side, where the ray comes in under its top
        side = ~done & (g0 < 0) & (face[i] >= 0)
        if side.any():
            q = np.nonzero(side)[0]
            j = w['bld'][xi[q], zi[q]]
            isb = inside[q] & (j >= 0)
            c = mat_rgb(np.where(inside[q], w['mat'][xi[q], zi[q]], 1)) * np.array(SHADE)[np.array(SIDE_LIGHT)[face[i][q]]][:, None]
            if isb.any():
                p = q[isb]
                c[isb] = wall(i[p], t0[i][p], y0[p], j[isb], face[i][p], box[j[isb], 4].astype(float))
            col[q] = c
            done |= side
        # its top
        tt = t0[i] + (t1 - t0[i]) * g0 / np.where(g0 - g1 == 0, 1, g0 - g1)
        ontop = ~done & (g0 >= 0) & (g1 < 0)
        if ontop.any():
            q = np.nonzero(ontop)[0]
            hx, hz = ox + dx[i[q]] * tt[q], oz + dz[i[q]] * tt[q]
            m = np.where(inside[q], w['mat'][xi[q], zi[q]], 1)
            tid = np.where(inside[q], w['ctex'][xi[q], zi[q]].astype(int), 0xffff)
            col[q] = texel(tid, hx / 32, hz / 32, mat_rgb(m))
            done |= ontop
        far = ~done & (t1 > 60 * CELL / FOCAL)                    # (t is in units of FOCAL along the lens)
        out[i[done]] = col[done]
        live[i[done | far]] = False
        # on to the next cell
        stepx = tmx[i] <= tmz[i]
        face[i] = np.where(stepx, np.where(sx[i] > 0, 3, 1), np.where(sz[i] > 0, 0, 2))
        t0[i] = t1
        cx[i] += np.where(stepx, sx[i], 0)
        cz[i] += np.where(stepx, 0, sz[i])
        tmx[i] += np.where(stepx, tdx[i], 0)
        tmz[i] += np.where(stepx, 0, tdz[i])
    return np.clip(out, 0, 255).astype(np.uint8).reshape(H, W, 3)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('dir')
    ap.add_argument('out')
    ap.add_argument('--cam', type=float, nargs=3, default=(9728, 403, 2070), help='x y z (units); default: the rampage start')
    ap.add_argument('--yaw', type=float, default=0, help='degrees: 0 looks along +z, 90 along +x')
    ap.add_argument('--pitch', type=float, default=-20.13, help='degrees, down is negative (the game on foot: -20)')
    ap.add_argument('--gba', help='a GBA screenshot to put beside it')
    a = ap.parse_args()
    w = load(a.dir)
    ya, pi = math.radians(a.yaw), math.radians(a.pitch)
    f0 = np.array((math.sin(ya), 0, math.cos(ya)))
    r = np.array((-math.cos(ya), 0, math.sin(ya)))               # (the game's camera at yaw 0: right = -x)
    f = f0 * math.cos(pi) + np.array((0, 1, 0)) * math.sin(pi)
    u = np.cross(r, f) * -1
    if u[1] < 0:
        u = -u
    img = render(w, a.cam, r, u, f)
    im = Image.fromarray(img).resize((W * 3, H * 3), Image.NEAREST)
    if a.gba:
        g = Image.open(a.gba).convert('RGB').resize((W * 3, H * 3), Image.NEAREST)
        both = Image.new('RGB', (W * 6 + 8, H * 3), (255, 255, 255))
        both.paste(im, (0, 0))
        both.paste(g, (W * 3 + 8, 0))
        im = both
    im.save(a.out)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
