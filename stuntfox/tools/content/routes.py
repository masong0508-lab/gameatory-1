"""Route making over an atlas: what the authors and the generators share. Ring lines (clear discs along a way the Arwing
can fly), lane routes (a path over Payback's lane graph for a race), and the small geometry both use. Host tools only.
Units: cells are floats (x, y), heights world units; an atlas point is (x * 1024, z = y * 1024, height).
"""
import heapq
import math

import atlas as A

TURN_MAX = 100.0


def ring_axis(prev, cur, nxt):
    """'x' (the ring's plane is x = const: the course runs along x), 'y' or 'h' (a climb or dive), from the way it runs."""
    a = prev or cur
    b = nxt or cur
    dx, dz, dy = (b[0] - a[0]) * 1024, (b[1] - a[1]) * 1024, b[2] - a[2]
    if dx == 0 and dz == 0 and dy == 0:
        return 'x'
    if abs(dy) > 1.2 * max(abs(dx), abs(dz)):
        return 'h'
    return 'x' if abs(dx) >= abs(dz) else 'y'


def disc_clear(a, x, y, h, r, axis, margin=128):
    """The ring's disc (centre, an inner ring, 16 rim samples and the way through) clear of solids by margin: None, or the first blocked point."""
    return a.clear_disc(x * 1024, y * 1024, h, r * 1024, axis, margin)


def seg_clear(a, p, q, margin=256, step=256):
    return a.segment_clear((p[0] * 1024, p[1] * 1024, p[2]), (q[0] * 1024, q[1] * 1024, q[2]), margin, step)


def turn_deg(p, q, s):
    v1 = ((q[0] - p[0]) * 1024, (q[1] - p[1]) * 1024, q[2] - p[2])
    v2 = ((s[0] - q[0]) * 1024, (s[1] - q[1]) * 1024, s[2] - q[2])
    n1, n2 = math.sqrt(sum(c * c for c in v1)), math.sqrt(sum(c * c for c in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    d = sum(a * b for a, b in zip(v1, v2)) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, d))))


def ring_line(a, pts, h=900, step=6.0, r=1.0, hmax=9000, lift=128):
    """Rings along the polyline pts [(x, y) or (x, y, h)] every step cells. A point without a height gets h, raised in
    lift steps until its disc and the way to it are clear. -> ([(x, y, h, r, axis)], [problems])"""
    out, bad = [], []
    path = [pts[0]]
    for q in pts[1:]:
        p = path[-1]
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        k = max(1, int(round(d / step)))
        for i in range(1, k + 1):
            t = i / k
            hh = None
            if len(p) > 2 and len(q) > 2:
                hh = p[2] + (q[2] - p[2]) * t
            elif len(q) > 2 and i == k:
                hh = q[2]
            path.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t) + ((hh,) if hh is not None else ()))
    pts3 = []
    for i, p in enumerate(path):
        x, y = p[0], p[1]
        hh = p[2] if len(p) > 2 else h
        pts3.append([x, y, hh, len(p) > 2])
    for i, (x, y, hh, fixed) in enumerate(pts3):
        prev = pts3[i - 1] if i else None
        nxt = pts3[i + 1] if i + 1 < len(pts3) else None
        ax = ring_axis(prev, (x, y, hh), nxt)
        z = hh
        while True:
            bad_pt = disc_clear(a, x, y, z, r, ax)
            ok = bad_pt is None
            if ok and prev is not None:
                ok = seg_clear(a, (prev[0], prev[1], prev[2]), (x, y, z), 192) is None
            if ok or fixed or z >= hmax:
                break
            z += lift
        if not ok:
            bad.append('ring %d at (%.1f, %.1f, h%d) is not clear' % (i, x, y, z))
        pts3[i][2] = z
        out.append((round(x, 2), round(y, 2), int(z), r, ax))
    for i in range(1, len(out) - 1):
        t = turn_deg(out[i - 1], out[i], out[i + 1])
        if t > TURN_MAX:
            bad.append('turn of %d degrees at ring %d' % (t, i))
    return out, bad


# ---- lanes ----
def drive_graph(a):
    """The lane graph a driver may use: a lane cell leads along its lane bits, and straight on through a junction cell
    (a lane cell with other bits) into the lane the way it was going."""
    g = {}
    for i in a.main_car:
        b = a.lane[i] & 15
        if not b:
            continue
        x, y = divmod(i, A.N)
        out = []
        for e, (dx, dy) in enumerate(A.LANE_STEP):
            if not (0 <= x + dx < A.N and 0 <= y + dy < A.N):
                continue
            j = (x + dx) * A.N + y + dy
            bj = a.lane[j] & 15
            if bj and j in a.main_car and ((b & A.LANE_BIT[e]) or (bj & A.LANE_BIT[e])):
                out.append(j)
        g[i] = out
    return g


def lane_path(a, start, goal, turn_cost=6.0, avoid=None, g=None):
    """A route over the lane graph from one lane cell to another: [cell indices]. Dijkstra on (cell, heading) with a cost for
    turning, so a course keeps to straights; avoid: cells to leave alone (a loop's other half)."""
    g = g or drive_graph(a)
    if start not in g or goal not in g:
        return None
    best = {(start, -1): 0.0}
    prev = {}
    pq = [(0.0, start, -1)]
    while pq:
        c, i, hd = heapq.heappop(pq)
        if best.get((i, hd), 1e18) < c:
            continue
        if i == goal:
            path = [i]
            k = (i, hd)
            while k in prev:
                k = prev[k]
                path.append(k[0])
            return path[::-1]
        x, y = divmod(i, A.N)
        for j in g[i]:
            if avoid and j in avoid and j != goal:
                continue
            jx, jy = divmod(j, A.N)
            h2 = {(0, -1): 0, (1, 0): 1, (0, 1): 2, (-1, 0): 3}.get((jx - x, jy - y), 0)
            cost = c + 1.0 + (turn_cost if hd >= 0 and h2 != hd else 0.0) + (6.0 if hd >= 0 and (h2 - hd) % 4 == 2 else 0.0)
            if cost < best.get((j, h2), 1e18):
                best[(j, h2)] = cost
                prev[(j, h2)] = (i, hd)
                heapq.heappush(pq, (cost, j, h2))
    return None


def checkpoints(path, step=12, a=None):
    """Checkpoints along a cell path: every turn corner and a place at least every step cells on the straights.
    -> [(x, y)] at cell centres (the lane's own line)."""
    pts = [divmod(i, A.N) for i in path]
    out = [pts[0]]
    last = 0
    for k in range(1, len(pts) - 1):
        d0 = (pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1])
        d1 = (pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])
        if d0 != d1 or k - last >= step:
            out.append(pts[k])
            last = k
    out.append(pts[-1])
    return [(x + 0.5, y + 0.5) for x, y in out]


# ---- air: A* through free air on a 1-cell by 512-unit grid ----
import numpy as np  # noqa: E402

LEVEL = 512
NLEV = 32                       # up to 16384


class AirGrid:
    """Occupancy of the air over an atlas: node (x, z, k) is the middle of cell (x, z) at height k * 512; it is free when
    the Arwing (a box of 384 units clear all round) fits there. Near-wall cost helps pick a course that hugs the city."""
    def __init__(self, a, margin=384, dilate=1):
        self.a = a
        n = A.N
        top = np.zeros((n, n), dtype=np.int32)
        d0 = np.full((n, n), 1 << 20, dtype=np.int32)
        d1 = np.full((n, n), -1, dtype=np.int32)
        e0 = np.full((n, n), 1 << 20, dtype=np.int32)
        e1 = np.full((n, n), -1, dtype=np.int32)
        for i in range(n * n):
            x, z = divmod(i, n)
            t = max(a.hi[i], a.lo[i])
            top[x, z] = t
            d = a.deck.get(i)
            if d:
                d0[x, z], d1[x, z] = d[0], d[1]
            d = a.deck2.get(i)
            if d:
                e0[x, z], e1[x, z] = d[0], d[1]
        ks = (np.arange(NLEV) * LEVEL).astype(np.int32)[None, None, :]
        occ = ks < (top[:, :, None] + margin)
        occ |= (ks >= d0[:, :, None] - margin) & (ks <= d1[:, :, None] + margin)
        occ |= (ks >= e0[:, :, None] - margin) & (ks <= e1[:, :, None] + margin)
        occ[:, :, 0] = True
        for _ in range(dilate):                 # (a node's neighbours are clear too: the ring's disc is in the same air)
            d = occ.copy()
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    d |= np.roll(occ, (dx, dz), (0, 1))
            occ = d
        self.occ = occ
        # cells nearer than a cell to a blocked node at the same level: a wall is close
        near = np.zeros_like(occ)
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(occ, (dx, dz), (0, 1))
            near |= sh
        self.near = near & ~occ

    def free(self, x, z, k):
        return 0 <= x < A.N and 0 <= z < A.N and 0 < k < NLEV and not self.occ[x, z, k]

    def seg_free(self, p, q, step=0.25):
        """The straight way from p to q ((x, y, h) in cells and units) through free nodes (both heights either side of it)."""
        n = max(1, int(max(abs(q[0] - p[0]), abs(q[1] - p[1])) / step))
        for i in range(n + 1):
            t = i / n
            x, y, h = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t
            k0 = int(h // LEVEL)
            if not (self.free(int(x), int(y), k0) and self.free(int(x), int(y), k0 + 1)):
                return False
        return True


_NB = [(dx, dz, dk) for dx in (-1, 0, 1) for dz in (-1, 0, 1) for dk in (-1, 0, 1) if (dx, dz, dk) != (0, 0, 0)]


def astar(g, s, t, low=0.00025, hug=0.35, max_nodes=250000, kmax=None):
    """The cheapest free path from node s to node t (x, z, k tuples) over the air grid. Cost: length, a little for
    height (low flying is more fun and a better test), a rebate for passing close to a wall. -> [(x, z, k)] or None."""
    def hcost(n):
        return math.sqrt((n[0] - t[0]) ** 2 + (n[1] - t[1]) ** 2 + ((n[2] - t[2]) * 0.5) ** 2)
    if not g.free(*s) or not g.free(*t):
        return None
    best = {s: 0.0}
    prev = {}
    pq = [(hcost(s), 0.0, s)]
    n = 0
    while pq:
        f, c, u = heapq.heappop(pq)
        if u == t:
            path = [u]
            while u in prev:
                u = prev[u]
                path.append(u)
            return path[::-1]
        if c > best.get(u, 1e18):
            continue
        n += 1
        if n > max_nodes:
            return None
        for dx, dz, dk in _NB:
            v = (u[0] + dx, u[1] + dz, u[2] + dk)
            if not g.free(*v) or (kmax is not None and v[2] > kmax):
                continue
            if dx and dz and not (g.free(u[0] + dx, u[1], u[2]) and g.free(u[0], u[1] + dz, u[2])):
                continue
            step = math.sqrt(dx * dx + dz * dz + (dk * 0.5) ** 2)
            cost = c + step * (1.0 + low * v[2] * LEVEL / 1.0 - (hug * 0.25 if g.near[v[0], v[1], v[2]] else 0.0))
            if cost < best.get(v, 1e18):
                best[v] = cost
                prev[v] = u
                heapq.heappush(pq, (cost + hcost(v), cost, v))
    return None


def simplify(g, pts):
    """Cut corners: keep the farthest point each point can see in a straight clear line. pts: [(x, y, h)] in cells and units."""
    out = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1 and not g.seg_free(pts[i], pts[j]):
            j -= 1
        out.append(pts[j])
        i = j
    return out


def node_pt(n):
    return (n[0] + 0.5, n[1] + 0.5, n[2] * LEVEL)


def snap(g, p, rad=4, up=8):
    """The free node nearest a point (x, y, h): in the same cell column first, then out to rad cells, then higher."""
    k0 = max(1, int(round(p[2] / LEVEL)))
    best = None
    for dx in range(-rad, rad + 1):
        for dz in range(-rad, rad + 1):
            for dk in range(0, up + 1):
                n = (int(p[0]) + dx, int(p[1]) + dz, k0 + dk)
                if g.free(*n):
                    d = dx * dx + dz * dz + dk * dk * 0.5
                    if best is None or d < best[0]:
                        best = (d, n)
                    break
    return best[1] if best else None


def air_path(g, p, q, exact=False, hmax=None):
    """A clear way from point p to q ((x, y, h) in cells and units), simplified. The ends are moved to the nearest free
    node unless exact. -> [(x, y, h)] or None."""
    s = snap(g, p)
    t = snap(g, q)
    if s is None or t is None:
        return None
    path = astar(g, s, t, kmax=None if hmax is None else int(hmax // LEVEL))
    if path is None:
        return None
    pts = [node_pt(n) for n in path]
    if exact:
        pts[0] = (p[0], p[1], p[2])
        pts[-1] = (q[0], q[1], q[2])
    return simplify(g, pts)


def polyline_len(pts):
    return sum(math.sqrt((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 + ((q[2] - p[2]) / 1024.0) ** 2) for p, q in zip(pts, pts[1:]))


def resample(pts, spacing):
    """Points every `spacing` (cells; height counts in cells) along a polyline, first and last included."""
    total = polyline_len(pts)
    n = max(1, int(round(total / spacing)))
    out = [pts[0]]
    want = [total * i / n for i in range(1, n + 1)]
    acc, k = 0.0, 0
    for p, q in zip(pts, pts[1:]):
        d = math.sqrt((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 + ((q[2] - p[2]) / 1024.0) ** 2)
        while k < len(want) and want[k] <= acc + d + 1e-9:
            t = (want[k] - acc) / d if d else 0.0
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t))
            k += 1
        acc += d
    return out


def fit_ring(a, x, y, h, r, rmin, ax, prev=None):
    """A ring near (x, y, h) with its disc clear (and the way from the previous ring): a smaller ring, a nudge up or aside.
    -> (x, y, h, r) or None."""
    rr = r
    while rr >= rmin - 1e-9:
        for ox, oy in [(0, 0)] + [(sx * d, sy * d) for d in (0.25, 0.5, 0.75) for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1))]:
            for dh in (0, 128, 256, -128, 384, 512, 768):
                if disc_clear(a, x + ox, y + oy, h + dh, rr, ax) is None and \
                        (prev is None or seg_clear(a, prev, (x + ox, y + oy, h + dh), 192) is None):
                    return (x + ox, y + oy, h + dh, rr)
        rr = round(rr - 0.1, 2)
    return None


def straight_rings(a, p, q, n, r=2.0, rmin=0.8):
    """n rings on the straight line p -> q (the last one at q): for a dive through open sky. -> (rings, problems)"""
    rings, bad = [], []
    for i in range(1, n + 1):
        t = i / n
        x, y, h = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t
        nx = (p[0] + (q[0] - p[0]) * (i + 1) / n, p[1] + (q[1] - p[1]) * (i + 1) / n, p[2] + (q[2] - p[2]) * (i + 1) / n)
        ax = ring_axis(rings[-1] if rings else p, (x, y, h), nx)
        got = fit_ring(a, x, y, h, r, rmin, ax, rings[-1] if rings else None)
        if got is None:
            bad.append('dive ring %d at (%.1f, %.1f, h%d) is not clear' % (i, x, y, h))
            got = (x, y, h, rmin)
        rings.append((round(got[0], 2), round(got[1], 2), int(got[2]), round(got[3], 2), ax))
    return rings, bad


def ring_course(a, g, anchors, spacing=7.0, r=1.1, rmin=0.7, last_ring=False, hmax=None):
    """A ring course through the anchors ((x, y, h): the air between them found by A*): rings about every `spacing` cells
    on the way, each with its disc clear (a smaller ring, or a nudge up, where the air is tight).
    -> (rings [(x, y, h, r, axis)], problems [str])"""
    poly = []
    for p, q in zip(anchors, anchors[1:]):
        seg = air_path(g, p, q, hmax=hmax)
        if seg is None:
            return [], ['no way from %s to %s' % (p, q)]
        poly += seg if not poly else seg[1:]
    pts = resample(poly, spacing)
    if not last_ring:
        pts = pts[:-1]
    rings, bad = [], []
    for i, (x, y, h) in enumerate(pts):
        prev = rings[-1] if rings else None
        nxt = pts[i + 1] if i + 1 < len(pts) else None
        ax = ring_axis(prev, (x, y, h), nxt)
        got = fit_ring(a, x, y, h, r, rmin, ax, prev)
        if got is None:
            bad.append('ring %d at (%.1f, %.1f, h%d) is not clear' % (i, x, y, h))
            got = (x, y, h, rmin)
        rings.append((round(got[0], 2), round(got[1], 2), int(got[2]), round(got[3], 2), ax))
    for _ in range(3):                                                  # smooth the heights where the air allows
        for i in range(1, len(rings) - 1):
            x, y, h, rr, ax = rings[i]
            hs = int((rings[i - 1][2] + 2 * h + rings[i + 1][2]) / 4)
            if hs != h and disc_clear(a, x, y, hs, rr, ax) is None and seg_clear(a, rings[i - 1], (x, y, hs), 192) is None \
                    and seg_clear(a, (x, y, hs), rings[i + 1], 192) is None:
                rings[i] = (x, y, hs, rr, ax)
    for i in range(1, len(rings) - 1):
        t = turn_deg(rings[i - 1], rings[i], rings[i + 1])
        if t > TURN_MAX:
            bad.append('turn of %d degrees at ring %d' % (t, i))
    return rings, bad


def places_text(prefix, rings, kind='ring', start=1):
    """The .places lines for rings, as NAME.N."""
    return ''.join('place %s.%d x=%g y=%g h=%d r=%g %s\n' % (prefix, i, x, y, h, r, kind) for i, (x, y, h, r, ax) in enumerate(rings, start))
