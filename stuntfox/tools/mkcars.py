#!/usr/bin/env python3
"""Draws the merge build's vehicles (src/traffic.c includes the result, src/cars.h) so they can be changed in one place.

    python3 tools/mkcars.py > src/cars.h

A vehicle is two models. The body (at most 56 points: model_draw's limit) and its extras (wheels, lamps, signs: at most 56
points, drawn only when the car is near, and BEFORE the body). The order matters, since r_flush_fg draws a bucket of equal
depth (32 units) latest-queued first: whatever must lie over something goes earlier in its list, and a big panel that carries
decals is MF_BACK (sorted by its farthest point), so its decals stay over it from any side. Faces are written in layer order
(decals first, then bodies, then MF_BACK panels) to do exactly that. Everything is one-sided but the thin parts, so the
back faces are culled. y is given as the height over the road, as G + h.
"""
import sys

G = -58
(M_SKY, M_ROAD, M_KERB, M_GRASS, M_PLAZA, M_CONCRETE, M_GLASS, M_BRICK, M_TEAL, M_CREAM, M_STEEL, M_CAR, M_ACCENT, M_SHIP,
 M_GLOW, M_STUNT) = range(16)
MN = 'M_SKY M_ROAD M_KERB M_GRASS M_PLAZA M_CONCRETE M_GLASS M_BRICK M_TEAL M_CREAM M_STEEL M_CAR M_ACCENT M_SHIP M_GLOW M_STUNT'.split()
MF_TWO, MF_GLOW, MF_IN, MF_BACK, MF_WIND = 1, 2, 4, 8, 16
LAYER_DECAL, LAYER_BODY, LAYER_BASE = 0, 1, 2     # emitted in this order: earlier = drawn over the rest of its bucket


class Mdl:
    def __init__(s, name):
        s.name, s.v, s.f = name, [], []

    def V(s, x, h, z):
        p = (int(round(x)), int(round(h + G)), int(round(z)))
        if p not in s.v:
            s.v.append(p)
        return s.v.index(p)

    def face(s, mat, pts, fl=0, layer=LAYER_BODY):
        assert 3 <= len(pts) <= 6
        s.f.append((layer, len(s.f), mat, fl, [s.V(*p) for p in pts]))

    def both(s, mat, pts, fl=0, layer=LAYER_BODY):
        """a face and its mirror image"""
        s.face(mat, pts, fl, layer)
        s.face(mat, [(-x, h, z) for x, h, z in reversed(pts)], fl, layer)

    def C(s):
        out = []
        n = len(s.v)
        out.append('static const MVert %s_v[] = {' % s.name)
        for i in range(0, n, 4):
            out.append('    ' + ' '.join('{%d, %d, %d},' % p for p in s.v[i:i + 4]))
        out.append('};')
        out.append('static const MFace %s_f[] = {' % s.name)
        for layer, _, mat, fl, idx in sorted(s.f, key=lambda t: (t[0], t[1])):
            fn = '|'.join(n for n, b in (('MF_TWO', 1), ('MF_GLOW', 2), ('MF_IN', 4), ('MF_BACK', 8), ('MF_WIND', 16)) if fl & b) or '0'
            out.append('    F%d(%s, %s, %s),' % (len(idx), MN[mat], fn, ', '.join(map(str, idx))))
        out.append('};')
        return '\n'.join(out), n, len(s.f)


def mir(p):
    return (-p[0], p[1], p[2])


# ---- wheels: tyre (a hex, M_ROAD) and hub, on the outside of each wheel; the arch is part of the body
def wheels(m, x, zs, hub=True, r=36):
    for z in zs:
        for sx in (-1, 1):
            xo = sx * x
            ty = [(xo, 2 * r, z), (xo, 1.5 * r, z + 0.86 * r), (xo, 0.5 * r, z + 0.86 * r), (xo, 0, z), (xo, 0.5 * r, z - 0.86 * r),
                  (xo, 1.5 * r, z - 0.86 * r)]
            if sx < 0:
                ty.reverse()
            m.face(M_ROAD, ty, 0, LAYER_BODY)
            if hub:
                xh = xo + sx * 3
                hb = [(xh, r + 16, z), (xh + 0, r, z + 14), (xh, r - 16, z), (xh, r, z - 14)]
                m.face(M_STEEL, hb, 0, LAYER_DECAL)


def arches(m, x, zs, top=80, bot=22, hw=48):
    for z in zs:
        for sx in (-1, 1):
            xo = sx * (x + 2)
            a = [(xo, bot, z - hw + 2), (xo, bot + 26, z - hw), (xo, top, z - hw * 0.62), (xo, top, z + hw * 0.62), (xo, bot + 26, z + hw),
                 (xo, bot, z + hw - 2)]
            if sx < 0:
                a.reverse()
            m.face(M_ROAD, a, 0, LAYER_DECAL)


def lamps(m, kind, x0, x1, hts, surf, mat, off, strip=False):
    """a lamp (or a strip across) at height range hts on a sloped surface: surf(h) -> z; off pushes it out"""
    h0, h1 = hts
    for sx in (-1, 1) if not strip else (0,):
        xa, xb = (x0, x1) if not strip else (-x1, x1)
        if sx == -1:
            xa, xb = -x1, -x0
        elif sx == 1:
            xa, xb = x0, x1
        q = [(xa, h0, surf(h0) + off), (xb, h0, surf(h0) + off), (xb, h1, surf(h1) + off), (xa, h1, surf(h1) + off)]
        if (sx == -1) != (off < 0):
            q.reverse()
        m.face(mat, q, 0, LAYER_DECAL)


def saloon(L, cf, cb, rf, rb, w, hh, hd, ht, wz, kind='saloon', wx=None, split=0):
    """kind: saloon, taxi (roof sign), police (door stripes)"""
    wx = wx or w + 3
    body, ex = Mdl(kind + '_b' if kind != 'saloon' else 'saloon_b'), Mdl(kind + '_x')
    b = body
    nz = lambda h: L - 16 * (h - 44) / 18.0           # the grille band
    tz = lambda h: -L + 12 * (h - 44) / (ht - 44.0)    # the tail band

    def R(t, sx=1):
        return (sx * (w - 22), 150, rf + (rb - rf) * t)

    def B(t, sx=1):
        return (sx * w, hh + (hd - hh) * t, cf + (cb - cf) * t)
    tb, tp = 0.45, 0.55
    for sx in (-1, 1):
        A0, A1, A2 = (sx * (w - 6), 24, L), (sx * (w - 6), 44, L), (sx * (w - 14), 62, L - 16)
        T0, T1, T2 = (sx * (w - 6), 24, -L), (sx * (w - 6), 44, -L), (sx * (w - 10), ht, -L + 12)
        S0, S1 = (sx * w, 22, split), (sx * w, hh + (hd - hh) * (cf - split) / float(cf - cb), split)
        C1, D1 = B(0, sx), B(1, sx)
        fl = MF_BACK
        pts = [A0, S0, S1, C1, A2, A1]
        b.face(M_CAR, pts if sx > 0 else pts[::-1], fl, LAYER_BASE)
        pts = [S0, T0, T1, T2, D1, S1]
        b.face(M_CAR, pts if sx > 0 else pts[::-1], fl, LAYER_BASE)
        # greenhouse side: one pane, the B-pillar a strip over it (one more polygon, not two)
        pts = [C1, D1, R(1, sx), R(0, sx)]
        b.face(M_GLASS, pts if sx > 0 else pts[::-1], MF_BACK, LAYER_BASE)
        pts = [B(tb, sx), B(tp, sx), R(tp, sx), R(tb, sx)]
        b.face(M_CAR, pts if sx > 0 else pts[::-1], 0, LAYER_DECAL)
    # nose: bumper, grille band, bonnet; tail: bumper, band, boot
    A = lambda h, z, sx: (sx * (w - 6 if h < 50 else w - 14), h, z)
    b.face(M_STEEL, [(-(w - 6), 24, L), (w - 6, 24, L), (w - 6, 44, L), (-(w - 6), 44, L)])
    b.face(M_ROAD, [(-(w - 6), 44, L), (w - 6, 44, L), (w - 14, 62, L - 16), (-(w - 14), 62, L - 16)], MF_BACK, LAYER_BASE)
    b.face(M_CAR, [(-(w - 14), 62, L - 16), (w - 14, 62, L - 16), (w, hh, cf), (-w, hh, cf)])
    b.face(M_GLASS, [(-w, hh, cf), (w, hh, cf), (w - 22, 150, rf), (-(w - 22), 150, rf)])
    b.face(M_CAR, [(-(w - 22), 150, rf), (w - 22, 150, rf), (w - 22, 150, rb), (-(w - 22), 150, rb)])
    b.face(M_GLASS, [(-w, hd, cb), (w, hd, cb), (w - 22, 150, rb), (-(w - 22), 150, rb)])
    b.face(M_CAR, [(-w, hd, cb), (w, hd, cb), (w - 10, ht, -L + 12), (-(w - 10), ht, -L + 12)])
    b.face(M_CAR, [(-(w - 10), ht, -L + 12), (w - 10, ht, -L + 12), (w - 6, 44, -L), (-(w - 6), 44, -L)], MF_BACK, LAYER_BASE)
    b.face(M_STEEL, [(-(w - 6), 44, -L), (w - 6, 44, -L), (w - 6, 24, -L), (-(w - 6), 24, -L)])
    b.face(M_STEEL, [(-(w - 6), 24, L), (w - 6, 24, L), (w - 6, 24, -L), (-(w - 6), 24, -L)])
    arches(b, w, wz)
    # extras
    wheels(ex, wx, wz, hub=True)
    if kind == 'saloon':
        lamps(ex, 'h', w - 54, w - 22, (47, 59), nz, M_CREAM, 3)
        lamps(ex, 't', w - 54, w - 22, (51, ht - 12), tz, M_STUNT, -3)
    else:
        lamps(ex, 'h', 0, w - 22, (47, 59), nz, M_CREAM, 3, strip=True)
        lamps(ex, 't', 0, w - 22, (51, ht - 12), tz, M_STUNT, -3, strip=True)
    if kind == 'taxi':
        zc = (rf + rb) / 2.0
        s = Mdl('x')
        hh2 = 164
        a, bb = 24, 14
        pts = {(sx, sz, h): (sx * a, h, zc + sz * bb) for sx in (-1, 1) for sz in (-1, 1) for h in (150, hh2)}
        top = [pts[(-1, -1, hh2)], pts[(1, -1, hh2)], pts[(1, 1, hh2)], pts[(-1, 1, hh2)]]
        ex.face(M_CREAM, top, MF_GLOW)
        ex.face(M_CREAM, [pts[(-1, 1, 150)], pts[(1, 1, 150)], pts[(1, 1, hh2)], pts[(-1, 1, hh2)]], MF_GLOW)
        ex.face(M_CREAM, [pts[(1, -1, 150)], pts[(-1, -1, 150)], pts[(-1, -1, hh2)], pts[(1, -1, hh2)]], MF_GLOW)
        ex.face(M_CREAM, [pts[(1, 1, 150)], pts[(1, -1, 150)], pts[(1, -1, hh2)], pts[(1, 1, hh2)]], MF_GLOW)
        ex.face(M_CREAM, [pts[(-1, -1, 150)], pts[(-1, 1, 150)], pts[(-1, 1, hh2)], pts[(-1, -1, hh2)]], MF_GLOW)
    if kind == 'police':
        zs = (split + 90, split - 92)
        for sx in (-1, 1):
            q = [(sx * (w + 2), 38, zs[0]), (sx * (w + 2), 38, zs[1]), (sx * (w + 2), 54, zs[1]), (sx * (w + 2), 54, zs[0])]
            ex.face(M_ROAD, q if sx < 0 else q[::-1], 0, LAYER_DECAL)
    return body, ex


def orient(sx):
    """a face written for the right side, turned round for the left"""
    return (lambda p: p) if sx > 0 else (lambda p: p[::-1])


def pickup(L=245, w=118, wz=(160, -160)):
    """cab forward, an open bed behind it: rails, inner walls, a floor and the cab's back wall"""
    b, ex = Mdl('pickup_b'), Mdl('pickup_x')
    cf, hh, rf, rb, cbk, rail, floor = 150, 88, 112, 22, -10, 94, 58
    nz = lambda h: L - 16 * (h - 44) / 18.0
    R = lambda t, sx: (sx * (w - 24), 150, rf + (rb - rf) * t)
    for sx in (-1, 1):
        o = orient(sx)
        A0, A1, A2 = (sx * (w - 6), 24, L), (sx * (w - 6), 44, L), (sx * (w - 14), 62, L - 16)
        T0, T1, T2 = (sx * (w - 6), 24, -L), (sx * (w - 6), 44, -L), (sx * (w - 4), rail, -L)
        S0, Rr, C1 = (sx * w, 22, cbk), (sx * w, rail, cbk), (sx * w, hh, cf)
        b.face(M_CAR, o([A0, S0, Rr, C1, A2, A1]), MF_BACK, LAYER_BASE)
        b.face(M_CAR, o([S0, T0, T1, T2, Rr]), MF_BACK, LAYER_BASE)
        b.face(M_GLASS, o([C1, Rr, R(1, sx), R(0, sx)]))                       # the cab's side glass
        ri_f, ri_r = (sx * (w - 14), rail, cbk), (sx * (w - 14), rail, -L + 8)  # the bed: a rail, the inside of its wall
        fl_f, fl_r = (sx * (w - 14), floor, cbk), (sx * (w - 14), floor, -L + 8)
        b.face(M_CAR, o([Rr, T2, ri_r, ri_f]))
        b.face(M_CAR, o([ri_f, ri_r, fl_r, fl_f]), MF_IN)
    b.face(M_GLASS, [(-w, hh, cf), (w, hh, cf), (w - 24, 150, rf), (-(w - 24), 150, rf)])
    b.face(M_CAR, [(-(w - 24), 150, rf), (w - 24, 150, rf), (w - 24, 150, rb), (-(w - 24), 150, rb)])
    b.face(M_GLASS, [(-(w - 14), rail, cbk), (w - 14, rail, cbk), (w - 24, 150, rb), (-(w - 24), 150, rb)])
    b.face(M_CAR, [(-(w - 14), floor, cbk), (w - 14, floor, cbk), (w - 14, rail, cbk), (-(w - 14), rail, cbk)], MF_IN)
    b.face(M_STEEL, [(-(w - 14), floor, cbk), (w - 14, floor, cbk), (w - 14, floor, -L + 8), (-(w - 14), floor, -L + 8)], MF_IN)
    b.face(M_STEEL, [(-(w - 6), 44, L), (w - 6, 44, L), (w - 6, 24, L), (-(w - 6), 24, L)][::-1])
    b.face(M_ROAD, [(-(w - 6), 44, L), (w - 6, 44, L), (w - 14, 62, L - 16), (-(w - 14), 62, L - 16)], MF_BACK, LAYER_BASE)
    b.face(M_CAR, [(-(w - 14), 62, L - 16), (w - 14, 62, L - 16), (w, hh, cf), (-w, hh, cf)])
    b.face(M_CAR, [(-(w - 4), rail, -L), (w - 4, rail, -L), (w - 6, 44, -L), (-(w - 6), 44, -L)], MF_BACK, LAYER_BASE)
    b.face(M_STEEL, [(-(w - 6), 44, -L), (w - 6, 44, -L), (w - 6, 24, -L), (-(w - 6), 24, -L)])
    b.face(M_STEEL, [(-(w - 6), 24, L), (w - 6, 24, L), (w - 6, 24, -L), (-(w - 6), 24, -L)])
    arches(b, w, wz)
    wheels(ex, w + 3, wz)
    lamps(ex, 'h', w - 54, w - 22, (47, 59), nz, M_CREAM, 3)
    lamps(ex, 't', w - 44, w - 14, (56, 76), lambda h: -L, M_STUNT, -3)
    return b, ex


def van(L=245, w=118, wz=(160, -160)):
    """a tall box, a cab window each side, the rear doors' seam and two panes"""
    b, ex = Mdl('van_b'), Mdl('van_x')
    top, rft = 215, 205
    for sx in (-1, 1):
        o = orient(sx)
        N0, N1, N2 = (sx * (w - 4), 24, L), (sx * (w - 4), 52, L), (sx * w, 112, L - 4)
        RF = (sx * w, rft, L - 62)
        S0, S1 = (sx * w, 22, 0), (sx * w, 210, 0)
        T0, T3 = (sx * w, 24, -L), (sx * w, top, -L)
        b.face(M_CAR, o([N0, S0, S1, RF, N2, N1]), MF_BACK, LAYER_BASE)
        b.face(M_CAR, o([S0, T0, T3, S1]), MF_BACK, LAYER_BASE)
        xs = sx * (w + 2)
        b.face(M_GLASS, o([(xs, 120, L - 30), (xs, 120, 118), (xs, 186, 126), (xs, 186, L - 74)]), 0, LAYER_DECAL)
    b.face(M_STEEL, [(-(w - 4), 24, L), (w - 4, 24, L), (w - 4, 52, L), (-(w - 4), 52, L)][::-1])
    b.face(M_ROAD, [(-(w - 4), 52, L), (w - 4, 52, L), (w, 112, L - 4), (-w, 112, L - 4)], MF_BACK, LAYER_BASE)
    b.face(M_GLASS, [(-w, 112, L - 4), (w, 112, L - 4), (w, rft, L - 62), (-w, rft, L - 62)])
    b.face(M_CAR, [(-w, rft, L - 62), (w, rft, L - 62), (w, top, -L), (-w, top, -L)])
    b.face(M_CAR, [(-w, 44, -L), (w, 44, -L), (w, top, -L), (-w, top, -L)], MF_BACK, LAYER_BASE)
    b.face(M_STEEL, [(-w, 24, -L), (w, 24, -L), (w, 44, -L), (-w, 44, -L)])
    b.face(M_STEEL, [(-(w - 4), 24, L), (w - 4, 24, L), (w, 24, -L), (-w, 24, -L)])
    arches(b, w, wz)
    wheels(ex, w + 3, wz)
    for sx in (-1, 1):                                                   # the doors' panes
        q = [(sx * 10, 128, -L - 2), (sx * 50, 128, -L - 2), (sx * 50, 188, -L - 2), (sx * 10, 188, -L - 2)]
        ex.face(M_GLASS, q if sx < 0 else q[::-1], 0, LAYER_DECAL)
    lamps(ex, 'h', 0, w - 22, (30, 46), lambda h: L, M_CREAM, 3, strip=True)
    lamps(ex, 't', 0, w - 20, (50, 62), lambda h: -L, M_STUNT, -3, strip=True)
    return b, ex


def bus(L=520, w=130, wz=(380, -380)):
    """long and tall: a band of four panes each side, a windscreen and a destination board in front, two lamps"""
    b, ex = Mdl('bus_b'), Mdl('bus_x')
    top = 290
    for sx in (-1, 1):
        o = orient(sx)
        b.face(M_CAR, o([(sx * w, 22, L), (sx * w, 22, -L), (sx * w, top, -L), (sx * w, top, L)]), MF_BACK, LAYER_BASE)
        xs = sx * (w + 2)
        for z0, z1 in ((410, 250), (200, 20), (-30, -250), (-300, -480)):
            b.face(M_GLASS, o([(xs, 170, z0), (xs, 170, z1), (xs, 252, z1), (xs, 252, z0)]), 0, LAYER_DECAL)
    for z, sgn in ((L, 1), (-L, -1)):                                    # front and back, in bands
        rows = [(22, 60, M_STEEL), (60, 150, M_CAR), (150, 252, M_GLASS), (252, top, M_ROAD)]
        for h0, h1, mat in rows:
            q = [(-w, h0, z), (w, h0, z), (w, h1, z), (-w, h1, z)]
            b.face(mat, q if sgn > 0 else q[::-1], MF_BACK if mat == M_CAR else 0, LAYER_BASE if mat == M_CAR else LAYER_BODY)
    b.face(M_CAR, [(-w, top, L), (w, top, L), (w, top, -L), (-w, top, -L)])
    b.face(M_STEEL, [(-w, 22, L), (w, 22, L), (w, 22, -L), (-w, 22, -L)])
    wheels(ex, w + 3, wz, r=50)
    lamps(ex, 'h', w - 60, w - 24, (84, 112), lambda h: L, M_CREAM, 3)
    lamps(ex, 't', w - 60, w - 24, (84, 112), lambda h: -L, M_STUNT, -3)
    return b, ex


def sport(w=125):
    """the Blue Falcon wedge: a nose with a yellow stripe, a canopy, two yellow fins; arches, and wheels with hubs and lamps"""
    b, ex = Mdl('sport_b'), Mdl('sport_x')
    P = lambda x, y, z: (x, y - G, z)          # (the old model's own y is already the real one)
    n = [(-115, -38, 235), (115, -38, 235), (125, -38, -225), (-125, -38, -225),
         (-105, 12, 140), (105, 12, 140), (118, 32, -225), (-118, 32, -225),
         (-26, -38, 238), (26, -38, 238), (-24, 12, 140), (24, 12, 140),
         (-55, 16, 95), (55, 16, 95), (0, 64, -40), (-62, 28, -150), (62, 28, -150)]
    p = lambda i: P(*n[i])
    # the old model's twelve body faces
    b.face(M_CAR, [p(0), p(8), p(10), p(4)])
    b.face(M_ACCENT, [p(8), p(9), p(11), p(10)])
    b.face(M_CAR, [p(9), p(1), p(5), p(11)])
    b.face(M_CAR, [p(4), p(5), p(6), p(7)])
    b.face(M_CAR, [p(0), p(4), p(7), p(3)], MF_BACK, LAYER_BASE)
    b.face(M_CAR, [p(1), p(2), p(6), p(5)], MF_BACK, LAYER_BASE)
    b.face(M_STEEL, [p(3), p(2), p(6), p(7)])
    b.face(M_GLASS, [p(12), p(13), p(14)])
    b.face(M_GLASS, [p(13), p(16), p(14)])
    b.face(M_CAR, [p(16), p(15), p(14)])
    b.face(M_GLASS, [p(15), p(12), p(14)])
    b.face(M_ACCENT, [P(100, 32, -165), P(100, 98, -245), P(100, 32, -235)], MF_TWO)
    b.face(M_ACCENT, [P(-100, 32, -165), P(-100, 98, -245), P(-100, 32, -235)], MF_TWO)
    b.face(M_STEEL, [p(0), p(1), p(2), p(3)])
    b.face(M_STUNT, [P(-100, -4, -228), P(100, -4, -228), P(100, 18, -228), P(-100, 18, -228)][::-1], 0, LAYER_DECAL)
    arches(b, 118, (160, -150), top=64, bot=20, hw=46)
    wheels(ex, w + 2, (160, -150))
    surf = lambda h: 235 - 95 * (h - 20) / 50.0
    lamps(ex, 'h', 52, 92, (28, 38), surf, M_CREAM, 3)
    return b, ex


def tank():
    """tracks with a plate along each, fenders, a hull with a sloped front, a turret with a hatch, and a gun"""
    b = Mdl('tank_b')
    for sx in (-1, 1):
        o = orient(sx)
        x = sx * 152
        trk = [(x, 6, -295), (x, 6, 285), (x, 50, 325), (x, 82, 290), (x, 82, -290), (x, 50, -305)]
        b.face(M_ROAD, o(trk), MF_BACK, LAYER_BASE)
        xs = sx * 154
        b.face(M_STEEL, o([(xs, 18, -265), (xs, 18, 255), (xs, 58, 255), (xs, 58, -265)]), 0, LAYER_DECAL)
        b.face(M_STEEL, o([(sx * 152, 82, 290), (sx * 152, 82, -290), (sx * 108, 82, -290), (sx * 108, 82, 290)]))   # the fender
        b.face(M_CAR, o([(sx * 108, 82, 290), (sx * 108, 82, -290), (sx * 104, 130, -285), (sx * 104, 130, 200)]))   # the hull's side
    b.face(M_CAR, [(-108, 82, 290), (108, 82, 290), (104, 130, 200), (-104, 130, 200)])
    b.face(M_CAR, [(-104, 130, 200), (104, 130, 200), (104, 130, -285), (-104, 130, -285)])
    b.face(M_CAR, [(-108, 82, -290), (108, 82, -290), (104, 130, -285), (-104, 130, -285)][::-1])
    # the turret: a frustum
    tb = [(-78, 130, 70), (78, 130, 70), (78, 130, -110), (-78, 130, -110)]
    tt = [(-58, 172, 40), (58, 172, 40), (58, 172, -90), (-58, 172, -90)]
    b.face(M_CAR, [tb[0], tb[1], tt[1], tt[0]])
    b.face(M_CAR, [tb[1], tb[2], tt[2], tt[1]])
    b.face(M_CAR, [tb[2], tb[3], tt[3], tt[2]])
    b.face(M_CAR, [tb[3], tb[0], tt[0], tt[3]])
    b.face(M_CAR, tt[:])
    b.face(M_STEEL, [(14, 174, -30), (40, 174, -30), (40, 174, -60), (14, 174, -60)], 0, LAYER_DECAL)   # the hatch
    # the gun: a square barrel
    g0 = [(-8, 142, 450), (8, 142, 450), (8, 158, 450), (-8, 158, 450)]
    g1 = [(-8, 142, 70), (8, 142, 70), (8, 158, 70), (-8, 158, 70)]
    b.face(M_STEEL, [g1[3], g1[2], g0[2], g0[3]])
    b.face(M_STEEL, [g1[0], g1[3], g0[3], g0[0]])
    b.face(M_STEEL, [g1[2], g1[1], g0[1], g0[2]])
    b.face(M_ROAD, g0[:])
    return b, None


class Raw(Mdl):
    """no merging of equal points: the same index in every pose of the player, so the faces are shared"""
    def V(s, x, h, z):
        s.v.append((int(round(x)), int(round(h)), int(round(z))))      # (the player's y is the height over his feet)
        return len(s.v) - 1

    def ring(s, c, u, v, axis):
        """4 points round c, +-u and +-v along the two axes other than axis (0 x, 1 y, 2 z), always in the same order"""
        ax = [i for i in range(3) if i != axis]
        out = []
        for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            p = list(c)
            p[ax[0]] += su * u
            p[ax[1]] += sv * v
            out.append(s.V(*p))
        return out

    def cen(s, r):
        return tuple(sum(s.v[i][k] for i in r) / float(len(r)) for k in range(3))

    def oriented(s, mat, idx, away, fl, layer):
        """the points in the order that makes the normal point along away (MF_WIND: model_init keeps it)"""
        P = [s.v[i] for i in idx]
        e1 = [P[1][k] - P[0][k] for k in range(3)]
        e2 = [P[2][k] - P[0][k] for k in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        if sum(n[k] * away[k] for k in range(3)) < 0:
            idx = idx[::-1]
        s.f.append((layer, len(s.f), mat, fl | MF_WIND, list(idx)))

    def sides(s, mat, r0, r1, fl=(0, 0, 0, 0), layer=LAYER_BODY, skip=()):
        """skip: sides (0 -v, 1 +u, 2 +v, 3 -u) left out: those that lie against the body or the other leg"""
        c0, c1 = s.cen(r0), s.cen(r1)
        for k in range(4):
            if k in skip:
                continue
            idx = [r0[k], r0[(k + 1) % 4], r1[(k + 1) % 4], r1[k]]
            fc = s.cen(idx)
            ax = [(c0[i] + c1[i]) / 2.0 for i in range(3)]
            # the axis point at the face's own level along the limb
            d = [c1[i] - c0[i] for i in range(3)]
            dd = sum(x * x for x in d) or 1.0
            t = sum((fc[i] - c0[i]) * d[i] for i in range(3)) / dd
            ax = [c0[i] + d[i] * t for i in range(3)]
            s.oriented(mat, idx, [fc[i] - ax[i] for i in range(3)], fl[k], layer)

    def cap(s, mat, r, prev, fl=0, layer=LAYER_BODY):
        """the end ring r of a limb whose previous ring is prev"""
        c, p = s.cen(r), s.cen(prev)
        s.oriented(mat, list(r), [c[i] - p[i] for i in range(3)], fl, layer)

    def quad(s, mat, pts, away, fl=0, layer=LAYER_BODY):
        idx = [s.V(*p) for p in pts]
        s.oriented(mat, idx, away, fl, layer)



def hero(pose):
    """The player, standing on his origin (y up from the feet, +z the way he faces): legs, the body and head, the arms.
    pose 0 stands, 1 and 2 stride, 3 punches (the right arm straight out)."""
    s, a = [(0, 0), (36, 26), (-36, -26), (22, 0)][pose]
    lo, mid, arm = Raw('hero_lo'), Raw('hero_mid'), Raw('hero_arm')
    # legs: one tapered block from hip to ankle (leaning s forward) and a shoe
    for sx in (-1, 1):
        fz = -s if sx > 0 else s                    # (the right leg goes the other way)
        x0, x1 = (5, 24) if sx > 0 else (-24, -5)
        xc, xh = (x0 + x1) / 2.0, (x1 - x0) / 2.0
        hip = lo.ring((xc, 100, 0), xh, 11, 1)
        ank = lo.ring((xc, 16, fz), xh - 2, 9, 1)
        lo.sides(M_SKY, hip, ank)
        toe = lo.ring((xc, 0, fz + 8), xh + 1, 16, 1)         # the shoe's sole, longer than the ankle's width
        top = lo.ring((xc, 15, fz + 3), xh + 1, 11, 1)
        lo.sides(M_ROAD, toe, top)
        lo.cap(M_ROAD, top, toe)
    # the body and head
    belt0 = mid.ring((0, 96, 0), 28, 15, 1)
    chest = mid.ring((0, 168, 0), 38, 17, 1)
    shld = mid.ring((0, 180, 0), 36, 15, 1)
    mid.sides(M_CAR, belt0, chest)
    mid.sides(M_CAR, chest, shld)
    mid.cap(M_CAR, shld, chest)
    head0 = mid.ring((0, 184, 2), 15, 15, 1)
    head1 = mid.ring((0, 224, 2), 15, 15, 1)
    mid.sides(M_CREAM, head0, head1, (MF_BACK, 0, 0, 0))                # (the front: its eyes and fringe lie over it)
    h0 = mid.ring((0, 198, -6), 17, 14, 1)
    h1 = mid.ring((0, 236, -6), 17, 14, 1)
    mid.sides(M_ROAD, h0, h1)
    mid.cap(M_ROAD, h1, h0)
    for ex_ in (-1, 1):
        mid.quad(M_ROAD, [(ex_ * 5, 204, 17.5), (ex_ * 10, 204, 17.5), (ex_ * 10, 211, 17.5), (ex_ * 5, 211, 17.5)], (0, 0, 1), 0, LAYER_DECAL)
    mid.quad(M_ROAD, [(-15, 214, 17.5), (15, 214, 17.5), (15, 224, 17.5), (-15, 224, 17.5)], (0, 0, 1), 0, LAYER_DECAL)
    # the arms: a sleeve (shoulder to wrist) and a hand
    for sx in (-1, 1):
        x = sx * 43
        sw = a if sx > 0 else -a                    # (a hand swings with the opposite foot)
        sw = -sw
        if pose == 3 and sx > 0:
            c = [(x, 174, 0), (x, 172, 104), (x, 172, 126)]
            u, v = [6, 5, 7], [8, 6, 9]
            rg = [arm.ring(c[k], u[k], v[k], 2) for k in range(3)]
        else:
            if pose == 3:
                sw = -18
            c = [(x, 176, 0), (x, 98, sw + (12 if sw > 0 else 8)), (x, 80, sw * 1.1 + 12)]
            u, v = [6, 4.5, 5.5], [8, 6, 7.5]
            rg = [arm.ring(c[k], u[k], v[k], 1) for k in range(3)]
        inner = () if pose == 3 and sx > 0 else ((3,) if sx > 0 else (1,))     # (the side that lies against his body)
        arm.sides(M_CAR, rg[0], rg[1], skip=inner)
        arm.sides(M_CREAM, rg[1], rg[2], skip=inner)
    return lo, mid, arm


def build():
    models = {}
    sal = dict(L=235, cf=70, cb=-120, rf=30, rb=-95, w=112, hh=84, hd=86, ht=78, wz=(150, -150))
    for kind in ('saloon', 'taxi', 'police'):
        models[kind] = saloon(kind=kind, **sal)
    models['limo'] = saloon(kind='limo', L=340, cf=120, cb=-230, rf=80, rb=-205, w=112, hh=84, hd=86, ht=78, wz=(250, -250))
    models['pickup'] = pickup()
    models['van'] = van()
    models['bus'] = bus()
    models['sport'] = sport()
    models['tank'] = tank()
    return models


def hero_C():
    """the player's three parts in four poses, an array of points and of faces for each (the faces' winding follows the limbs, and
    the arms of the punch have a side more): hero_<part>_v<pose>, hero_<part>_f<pose>; the body is the same in all of them"""
    parts = [hero(p) for p in range(4)]
    out = []
    for k, nm in enumerate(('lo', 'mid', 'arm')):
        ms = [p[k] for p in parts]
        for m in ms:
            assert len(m.v) <= 56 and len(m.v) == len(ms[0].v), nm
        if nm == 'mid':
            for m in ms[1:]:
                assert m.v == ms[0].v and m.f == ms[0].f, 'the body must not change with the pose'
            ms = ms[:1]
        for pi, m in enumerate(ms):
            sfx = '' if nm == 'mid' else str(pi)
            n = len(m.v)
            body = ',\n    '.join(', '.join('{%d, %d, %d}' % p for p in m.v[i:i + 4]) for i in range(0, n, 4))
            out.append('static const MVert hero_%s_v%s[%d] = {\n    %s,\n};' % (nm, sfx, n, body))
            fs = []
            for layer, _, mat, fl, idx in sorted(m.f, key=lambda t: (t[0], t[1])):
                fn = '|'.join(nn for nn, b in (('MF_TWO', 1), ('MF_GLOW', 2), ('MF_IN', 4), ('MF_BACK', 8), ('MF_WIND', 16)) if fl & b) or '0'
                fs.append('F%d(%s, %s, %s)' % (len(idx), MN[mat], fn, ', '.join(map(str, idx))))
            out.append('static const MFace hero_%s_f%s[%d] = {\n    %s,\n};' % (nm, sfx, len(m.f), ',\n    '.join(fs)))
    return '\n'.join(out)


if __name__ == '__main__':
    mods = build()
    print('/* generated by tools/mkcars.py (python3 tools/mkcars.py > src/cars.h): the vehicles and the player. Points and faces in the macros of traffic.c. */')
    info = []
    for k, (b, x) in mods.items():
        for m in (b, x):
            if m is None or m.name in ('taxi_b', 'police_b'):
                continue
            c, nv, nf = m.C()
            assert nv <= 56, (m.name, nv)
            print(c)
            info.append((m.name, nv, nf))
    print(hero_C())
    print('/* ' + ', '.join('%s %dv %df' % t for t in info) + ' */')
