"""Drive generators: races over the lane graph (a loop of four straight lane runs where the map has one, else a dogleg
across a crossing), the speed-gate dash, and the checkpoints they share. Checkpoints sit on cells a car stands on."""
import math

import atlas as A
from gen_common import lane_runs, lane_pt


def crossings(runs):
    """[(H run, V run, cx, cy)]: a run along x ('y' axis) and a run along y that cross."""
    hs = [r for r in runs if r[0] == 'y']
    vs = [r for r in runs if r[0] == 'x']
    out = []
    for h in hs:
        for v in vs:
            cx, cy = v[1], h[1]
            if h[2] <= cx <= h[3] and v[2] <= cy <= v[3]:
                out.append((h, v, cx + .5, cy + .5))
    return out


def loops(runs, lo=70, hi=250, side=14):
    """Rectangles whose four sides are lane runs: [(x0, y0, x1, y1)] (cell-centre corners), perimeter lo..hi."""
    hs = [r for r in runs if r[0] == 'y']
    vs = [r for r in runs if r[0] == 'x']
    out = []
    for i, h1 in enumerate(hs):
        for h2 in hs[i + 1:]:
            y1, y2 = sorted((h1[1], h2[1]))
            if y2 - y1 < side:
                continue
            xl, xh = max(h1[2], h2[2]), min(h1[3], h2[3])
            if xh - xl < side:
                continue
            ok = [v for v in vs if xl <= v[1] <= xh and v[2] <= y1 and y2 <= v[3]]
            for j, v1 in enumerate(ok):
                for v2 in ok[j + 1:]:
                    x1, x2 = sorted((v1[1], v2[1]))
                    if x2 - x1 < side:
                        continue
                    per = 2 * (x2 - x1 + y2 - y1)
                    if lo <= per <= hi:
                        out.append((x1 + .5, y1 + .5, x2 + .5, y2 + .5))
    return out


def snap(gm, x, y):
    g = gm.ground(x, y, 'car', rad=1)
    return (g[0], g[1], g[2]) if g else None


def along(seq, step):
    """Points along the polyline seq (without its first point), a point at every corner and at least every `step` cells."""
    pts = [seq[0]]
    for p, q in zip(seq, seq[1:]):
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        k = max(1, int(math.ceil(d / step)))
        for i in range(1, k + 1):
            pts.append((p[0] + (q[0] - p[0]) * i / k, p[1] + (q[1] - p[1]) * i / k))
    return pts[1:]


def gate_at(gm, p, q):
    """Where a start ring goes: 3 cells from p toward q, on a floor. -> (x, y, h, kind)"""
    dx, dy = q[0] - p[0], q[1] - p[1]
    d = math.hypot(dx, dy) or 1.0
    x, y = p[0] + dx / d * 3, p[1] + dy / d * 3
    g = snap(gm, x, y) or (x, y, 0)
    return g[0], g[1], g[2], ('ring_x' if abs(dx) >= abs(dy) else 'ring_y')


def put_gate(gm, name, g):
    gm.place(name + '.s', g[0], g[1], g[2] + 400, 1.6, g[3], 'car')
    gm.claim(g[0], g[1])


def put_points(gm, name, pts):
    for i, (x, y) in enumerate(pts, 1):
        q = snap(gm, x, y) or (x, y, 0)
        gm.place('%s.%d' % (name, i), q[0], q[1], q[2], 2.5, 'car')
    return '%s.1..%s.%d' % (name, name, len(pts)), len(pts)


def shapes(gm, kind):
    """Candidate routes, [(type, corner points, key)]: loops of four lane runs, doglegs across a crossing."""
    runs = lane_runs(gm.a, 12)
    out = []
    if kind != 'D':
        for (x0, y0, x1, y1) in loops(runs):
            out.append(('L', [(x0 + 4, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0), (x0 + 4, y0)], (x0, y0)))
            out.append(('L', [(x1 - 4, y1), (x0, y1), (x0, y0), (x1, y0), (x1, y1), (x1 - 4, y1)], (x0, y0)))
    if kind != 'L':
        for h, v, cx, cy in crossings(runs):
            ea = h[2] + 1.5 if cx - h[2] >= h[3] - cx else h[3] - .5
            eb = v[2] + 1.5 if cy - v[2] >= v[3] - cy else v[3] - .5
            ea = max(cx - 70, min(cx + 70, ea))
            eb = max(cy - 70, min(cy + 70, eb))
            if abs(ea - cx) >= 18 and abs(eb - cy) >= 18:
                out.append(('D', [(ea, cy), (cx, cy), (cx, eb)], (cx, cy)))
                out.append(('D', [(cx, eb), (cx, cy), (ea, cy)], (cx, cy)))
    return out


def race(gm, name, k, used, kind=None, step=18):
    """A race over the lane graph: a loop if the map has one that is not used yet (kind 'L'), else a dogleg ('D').
    -> (places range, n, type) or None. `used` collects (x, y, type) of what is taken."""
    rnd = gm.rng('%s%d' % (name, k))
    cand = shapes(gm, kind)
    rnd.shuffle(cand)
    for t, pts, key in cand:
        if any(math.hypot(key[0] - ux, key[1] - uy) < 8 for ux, uy, _t in used):
            continue
        if not all(snap(gm, *q) for q in pts) or not gm.beacon_ok(*pts[0]):
            continue
        g = gate_at(gm, pts[0], pts[1])
        if not gm.beacon_ok(g[0], g[1]):
            continue
        seq = [(g[0], g[1])] + pts[1:]
        cps = along(seq, step)
        if len(cps) > 16:
            cps = along(seq, step * len(cps) / 15.0)
        if not 3 <= len(cps) <= 16:
            continue
        put_gate(gm, name, g)
        rng, n = put_points(gm, name, cps)
        used.append((key[0], key[1], t))
        return rng, n, t
    return None


def dash(gm, name, k, used, length=(36, 60)):
    """A speed gate: a straight stretch of a lane run, a start ring and three or four checkpoints."""
    rnd = gm.rng('%s%d' % (name, k))
    runs = lane_runs(gm.a, 30)
    rnd.shuffle(runs)
    for r in runs:
        axis, c, lo, hi = r
        n = hi - lo
        L = min(rnd.randint(*length), n - 6)
        if L < 30:
            continue
        a0 = lo + 3 + rnd.randint(0, max(0, n - L - 6))
        if rnd.random() < 0.5:
            p, q = lane_pt(r, a0), lane_pt(r, a0 + L)
        else:
            p, q = lane_pt(r, a0 + L), lane_pt(r, a0)
        if not (snap(gm, *p) and snap(gm, *q)):
            continue
        g = gate_at(gm, p, q)
        if not gm.beacon_ok(g[0], g[1]) or any(math.hypot(p[0] - ux, p[1] - uy) < 10 for ux, uy, _t in used):
            continue
        kk = max(3, int(math.ceil(L / 14.0)))
        cps = [(g[0] + (q[0] - g[0]) * i / kk, g[1] + (q[1] - g[1]) * i / kk) for i in range(1, kk + 1)]
        put_gate(gm, name, g)
        rng, n = put_points(gm, name, cps)
        used.append((p[0], p[1], 'S'))
        return rng, n, math.hypot(cps[-1][0] - g[0], cps[-1][1] - g[1])
    return None
