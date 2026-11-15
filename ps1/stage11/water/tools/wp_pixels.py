#!/usr/bin/env python3
"""wp_pixels.py WPOSES.H NORMAL_DIR UNDERLAY_DIR MAPS_DIR [--json out]: pixel checks of the wp_run.py grabs (emulator-only screenshots).
 holes     the UNDERLAY disc (island = magenta 255,0,255): a magenta pixel whose view ray hits the y = 0 plane inside the map at Chebyshev ring < 7 cells
           of the camera cell (where ground is meant to be drawn, ring >= 7 is the island by design) and above (height) the horizon is not counted.
           Counted at 320x240 resolution (2x2 blocks) per pose; also the biggest blob.
 flicker   NORMAL grabs a/b/c of a held pose: mean abs difference between grabs and the number of pixels differing by > 24 levels in any channel.
 leak      pixels in the NORMAL grab that are the near-black of the empty clear colour (0,0,0) below the horizon line (the GPU clear shows only where no packet was drawn)."""
import sys, re, json, numpy as np
from PIL import Image
from scipy import ndimage as ndi
H = 181.0
def load_poses(path):
    out = []
    for l in open(path):
        m = re.match(r'\s*\{ (\d+), (\d+), (-?\d+), (-?\d+), (-?\d+), (-?\d+), (-?\d+) \},', l)
        if m: out.append(tuple(int(v) for v in m.groups()))
    return out
def cam(yaw, pitch):
    t = 2 * np.pi / 65536.0; yw = yaw * t; pt = pitch * t
    f = np.array([np.sin(yw) * np.cos(pt), np.sin(pt), np.cos(yw) * np.cos(pt)])
    u = np.array([-np.sin(yw) * np.sin(pt), np.cos(pt), -np.cos(yw) * np.sin(pt)])
    r = np.array([-np.cos(yw), 0.0, np.sin(yw)])
    return f, u, r
_S = {}
def surf(maps_dir, m):
    if (maps_dir, m) not in _S:
        import water_check as wc
        S = wc.surfaces('%s/world%d' % (maps_dir, m)); jb = S['j']['boxes']
        rid = np.full((128, 128), -1, int); bsol = np.full((128, 128), -1, int); bdk = np.full((128, 128), -1, int)
        for k, r in enumerate(S['ramps']):
            if not r['deck']: rid[r['x0']:r['x1'], r['z0']:r['z1']] = k
        for k, b in enumerate(jb):
            if b['bottom'] == 0: bsol[b['x0']:b['x1'], b['z0']:b['z1']] = k
            else: bdk[b['x0']:b['x1'], b['z0']:b['z1']] = k
        top = np.array([b['top'] for b in jb] + [0]); bot = np.array([b['bottom'] for b in jb] + [0])
        _S[(maps_dir, m)] = (S, rid, bsol, bdk, top, bot)
    return _S[(maps_dir, m)]
def rect_dist(x, z, x0, z0, x1, z1):
    dx = max(x0 * 1024 - x, 0, x - x1 * 1024); dz = max(z0 * 1024 - z, 0, z - z1 * 1024); return max(dx, dz)
def hits(pose, maps_dir, reach=12288):
    """exact first hit of every pixel's ray with the world (solid boxes, raised decks, ramps with their slope, ground at 0): returns
    (expect, typ, ring, cell a, cell b); expect = the renderer must have drawn that surface (box/deck/ramp whose rectangle is within the reach, ground inside ring 7);
    typ 0 none (outside the map) 1 ground 2 solid box 3 deck 4 ramp"""
    import water_check as wc
    m, kind, x, y, z, yaw, pitch = pose
    y = max(y, 60)           # the renderer's fly camera never goes below y 60 (drive_tick)
    S, rid, bsol, bdk, top, bot = surf(maps_dir, m)
    Rm = S['ramps']; RD = np.array([r_['dirv'] for r_ in Rm] + [0]); RLO = np.array([r_['lo'] for r_ in Rm] + [0], float); RHI = np.array([r_['hi'] for r_ in Rm] + [0], float)
    RX0 = np.array([r_['x0'] * 1024 for r_ in Rm] + [0], float); RX1 = np.array([r_['x1'] * 1024 for r_ in Rm] + [0], float)
    RZ0 = np.array([r_['z0'] * 1024 for r_ in Rm] + [0], float); RZ1 = np.array([r_['z1'] * 1024 for r_ in Rm] + [0], float); RXL = RX1 - RX0; RZL = RZ1 - RZ0
    f, u, r = cam(yaw, pitch)
    px, py = np.meshgrid(np.arange(320) + 0.5, np.arange(240) + 0.5)
    d = f[None, None, :] + ((px - 160) / H)[..., None] * r + ((120 - py) / H)[..., None] * u
    dn = d / np.linalg.norm(d, axis=2, keepdims=True)
    cx, cz = int(x) // 1024, int(z) // 1024
    typ = np.zeros((240, 320), np.int8); oid = np.full((240, 320), -1, np.int32); hax = np.full((240, 320), -1, np.int32); hbz = np.full((240, 320), -1, np.int32)
    done = np.zeros((240, 320), bool)
    for t in np.arange(48.0, 17000.0, 48.0):
        X = x + t * dn[..., 0]; Y = y + t * dn[..., 1]; Z = z + t * dn[..., 2]
        a = np.floor(X / 1024).astype(int); b = np.floor(Z / 1024).astype(int)
        ok = (a >= 0) & (a < 128) & (b >= 0) & (b < 128) & ~done
        done |= ((a < 0) | (a >= 128) | (b < 0) | (b >= 128)) & ~done
        aa = np.clip(a, 0, 127); bb = np.clip(b, 0, 127)
        bs = bsol[aa, bb]; bd = bdk[aa, bb]; ri = rid[aa, bb]
        h1 = ok & (bs >= 0) & (Y <= top[bs]); h2 = ok & (bd >= 0) & (Y <= top[bd]) & (Y >= bot[bd])
        rk = np.clip(ri, 0, max(len(S['ramps']) - 1, 0)); dv = RD[rk]
        ln = np.where((dv == 2) | (dv == 4), RZL[rk], RXL[rk]).astype(np.float64); ln[ln == 0] = 1
        pos = np.where(dv == 2, Z - RZ0[rk], np.where(dv == 3, X - RX0[rk], np.where(dv == 4, RZ1[rk] - Z, np.where(dv == 5, RX1[rk] - X, 0.0))))
        ry = np.where((dv >= 2) & (dv <= 5), RLO[rk] + (RHI[rk] - RLO[rk]) * pos / ln, RLO[rk])
        h3 = ok & (ri >= 0) & (Y <= ry); h0 = ok & (ri < 0) & (bs < 0) & (Y <= 0)
        for code, hh, ids in ((2, h1, bs), (3, h2, bd), (4, h3, ri), (1, h0, np.full(Y.shape, -1))):
            new = hh & ~done
            typ[new] = code; oid[new] = ids[new]; hax[new] = a[new]; hbz[new] = b[new]; done |= new
        if done.all(): break
    ring = np.maximum(np.abs(hax - cx), np.abs(hbz - cz))
    okr = np.array([rect_dist(x, z, r_['x0'], r_['z0'], r_['x1'], r_['z1']) <= reach for r_ in S['ramps']] + [False])
    jb = S['j']['boxes']
    okb = np.array([rect_dist(x, z, b_['x0'], b_['z0'], b_['x1'], b_['z1']) <= reach for b_ in jb] + [False])
    e4 = np.zeros(typ.shape, bool); m4 = typ == 4; e4[m4] = okr[oid[m4]]
    e23 = np.zeros(typ.shape, bool); m23 = (typ == 2) | (typ == 3); e23[m23] = okb[oid[m23]]
    exp = ((typ == 1) & (ring < 7)) | e4 | e23
    return exp, typ, ring, hax, hbz
def grab(dirn, k, c):
    im = np.asarray(Image.open('%s/p%02d_%s.png' % (dirn, k, c)).convert('RGB'), np.int32)
    return im[::2, ::2]          # 640x480 -> 320x240 (nearest: the game is drawn 2x)
def main():
    poses = load_poses(sys.argv[1]); nd, ud = sys.argv[2], sys.argv[3]; maps_dir = sys.argv[4]; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
    res = []
    for k, p in enumerate(poses):
        try: u = grab(ud, k, 'a'); n = [grab(nd, k, c) for c in 'abc']
        except FileNotFoundError: continue
        exp, hitk, ring, hax, hbz = hits(p, maps_dir)
        mag = (u[..., 0] > 200) & (u[..., 2] > 200) & (u[..., 1] < 80)
        near = exp
        hole = mag & near
        lab, nl = ndi.label(hole, np.ones((3, 3)))
        big = max([int((lab == i + 1).sum()) for i in range(nl)], default=0)
        blk = np.zeros_like(mag)
        hair = 0
        for i, sl in enumerate(ndi.find_objects(lab)):
            a_ = int((lab[sl] == i + 1).sum()); h_ = sl[0].stop - sl[0].start; w_ = sl[1].stop - sl[1].start
            if a_ < 600 and min(h_, w_) <= 2: hair += a_
        pit = False
        d01 = np.abs(n[0] - n[1]).max(2); d12 = np.abs(n[1] - n[2]).max(2)
        r = dict(pose=k, map=p[0], kind=p[1], pit=bool(pit), hair_px=hair, hole_px=int(hole.sum()), hole_blob=big, magenta_far_px=int((mag & ~near).sum()), black_near_px=int(blk.sum()),
                 flick_px=int(max((d01 > 24).sum(), (d12 > 24).sum())), flick_mean=round(float(max(d01.mean(), d12.mean())), 3))
        from collections import Counter
        r['cells'] = [[int(a), int(b), c] for (a, b), c in Counter(zip(hax[hole].tolist(), hbz[hole].tolist())).most_common(4)]
        inm = hax >= 0
        wcell = np.zeros_like(mag); lc = np.zeros_like(mag)
        wcell[inm] = surf(maps_dir, p[0])[0]['water'][hax[inm], hbz[inm]]
        far = mag & ~near
        r['far_water_px'] = int((far & wcell).sum()); r['far_land_px'] = int((far & inm & ~wcell).sum()); r['far_void_px'] = int((far & ~inm).sum())
        res.append(r)
        print('pose %2d map %2d kind %d  hole px %5d (biggest blob %5d)  far-island px %6d (water %5d land %5d void %5d)  flicker px %4d mean %.3f %s' % (k, p[0], p[1], r['hole_px'], big, r['magenta_far_px'], r['far_water_px'], r['far_land_px'], r['far_void_px'], r['flick_px'], r['flick_mean'], r['cells'] if r['hole_px'] > 20 else ''))
    if '--json' in sys.argv: json.dump(res, open(sys.argv[sys.argv.index('--json') + 1], 'w'), indent=1)
    permap = {}
    for r in res:
        pm = permap.setdefault(r['map'], dict(n=0, hole=0, hair=0, pit=0, flick=0, far_water=0)); pm['n'] += 1
        if r['pit']: pm['pit'] += r['hole_px']
        else: pm['hole'] += r['hole_px']; pm['hair'] += r['hair_px']
        pm['flick'] += r['flick_px']; pm['far_water'] += r['far_water_px']
    for m in sorted(permap): q = permap[m]; print('map %2d: %2d poses, hole px %5d (hairline <=2px wide %4d), pit-camera hole px %5d, far-water-as-island px %5d, flicker px %d' % (m, q['n'], q['hole'], q['hair'], q['pit'], q['far_water'], q['flick']))
    print('TOTAL hole px %d (hairline %d), far-water px %d' % (sum(q['hole'] for q in permap.values()), sum(q['hair'] for q in permap.values()), sum(q['far_water'] for q in permap.values())))
if __name__ == '__main__': main()
