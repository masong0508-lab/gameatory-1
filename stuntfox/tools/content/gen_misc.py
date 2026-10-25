"""Ground generators: collect scatter, blast zones over box clusters, stunt and jump zones over ramp clusters, tower-top
medals, and the contracts' places."""
import math

import atlas as A
import gen_races
import gen_rings


def window_scores(cells, size, step=2):
    """[(count, x0, y0, x1, y1)] best first, for sliding size x size windows over a set of (x, y) cells."""
    n = A.N
    grid = [[0] * (n + 1) for _ in range(n + 1)]
    for (x, y) in cells:
        if 0 <= x < n and 0 <= y < n:
            grid[x + 1][y + 1] = 1
    for x in range(1, n + 1):
        for y in range(1, n + 1):
            grid[x][y] += grid[x - 1][y] + grid[x][y - 1] - grid[x - 1][y - 1]
    out = []
    for x0 in range(0, n - size, step):
        for y0 in range(0, n - size, step):
            x1, y1 = x0 + size, y0 + size
            c = grid[x1][y1] - grid[x0][y1] - grid[x1][y0] + grid[x0][y0]
            if c:
                out.append((c, x0, y0, x1 - 1, y1 - 1))
    out.sort(key=lambda t: (-t[0], t[1], t[2]))
    return out


def apart(picks, w, gap):
    cx, cy = (w[1] + w[3]) / 2.0, (w[2] + w[4]) / 2.0
    return all(math.hypot(cx - (p[1] + p[3]) / 2.0, cy - (p[2] + p[4]) / 2.0) >= gap for p in picks)


HUNT_ROUTE_MAX = 120.0          # cells: the longest walk a hunt on foot may ask (par stays under 300 s at the man's measured pace; V6 checks)


def tour(pts, start):
    """The points in nearest-neighbour order from start and the walk's length in cells (the length par.route measures)."""
    left, cur, out, d = list(pts), start, [], 0.0
    while left:
        k = min(range(len(left)), key=lambda i: (math.hypot(left[i][0] - cur[0], left[i][1] - cur[1]), left[i]))
        p = left.pop(k)
        d += math.hypot(p[0] - cur[0], p[1] - cur[1])
        out.append(p)
        cur = p
    return out, d


def scatter_cells(gm, rect, n, mode='foot', rnd=None, mind=8.0, near=None):
    """n spread open cells in rect: farthest-point picks from a seeded start, or with near=(x, y) the nearest ones to it that keep
    mind apart (a cluster round a pad, the order a little shuffled). -> [(x, y)] or None."""
    src = gm.a.main_foot if mode == 'foot' else gm.a.main_car
    x0, y0, x1, y1 = rect
    cand = []
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if not (5 <= x <= 122 and 5 <= y <= 122):
                continue
            i = A.idx(x, y)
            if src.get(i) != [0] or gm.a.kind[i] != 'ground' or gm.a.water[i]:
                continue
            if all(src.get(A.idx(x + dx, y + dy)) == [0] and not gm.a.water[A.idx(x + dx, y + dy)] for dx in (-1, 0, 1) for dy in (-1, 0, 1)) \
                    and all((x - px) ** 2 + (y - py) ** 2 > 9 for px, py in gm.a.phones):
                cand.append((x, y))
    if len(cand) < n:
        return None
    if near is not None:
        cand = [c for c in cand if (c[0] + .5 - near[0]) ** 2 + (c[1] + .5 - near[1]) ** 2 >= 25]          # (not on the pad: 5 cells off)
        cand.sort(key=lambda c: ((c[0] + .5 - near[0]) ** 2 + (c[1] + .5 - near[1]) ** 2) * rnd.uniform(0.7, 1.3))
        pick = []
        for c in cand:
            if all((c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2 >= mind * mind for p in pick):
                pick.append(c)
                if len(pick) == n:
                    return pick
        return None
    pick = [cand[rnd.randrange(len(cand))]]
    while len(pick) < n:
        best = max(cand, key=lambda c: min((c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2 for p in pick))
        if min((best[0] - p[0]) ** 2 + (best[1] - p[1]) ** 2 for p in pick) < mind * mind:
            return None
        pick.append(best)
    return pick


def scatter(gm, name, rect, n, mode='foot', rnd=None, mind=8.0, r=1.5, flags='pick', start=None):
    """n spread open cells in rect, named name.1..n (in a walking order from start, else by row). -> (range, n) or None."""
    pick = scatter_cells(gm, rect, n, mode, rnd, mind)
    if pick is None:
        return None
    pick = tour([(x + .5, y + .5) for x, y in pick], start)[0] if start else [(x + .5, y + .5) for x, y in sorted(pick, key=lambda c: (c[1], c[0]))]
    for i, (x, y) in enumerate(pick, 1):
        gm.place('%s.%d' % (name, i), x, y, 'ground', r, flags)
    return '%s.1..%s.%d' % (name, name, n), n


def collect(gm, name, k, n=6, win=28, mind=6.0, cap=HUNT_ROUTE_MAX):
    """A pickup hunt: n parts clustered in a window of open ground round a pad to start from, numbered in a walking order from the
    pad; the walk is at most cap cells (the man's pace is a cell a second, a limit over 300 s is no fun). -> (range, n) or None."""
    rnd = gm.rng('%s%d' % (name, k))
    for attempt in range(120):
        cx, cy = rnd.randint(20, 108), rnd.randint(20, 108)
        sp = gm.beacon_spot(cx, cy, 'foot', 1, 6)
        if not sp:
            continue
        rect = (int(sp[0]) - win // 2, int(sp[1]) - win // 2, int(sp[0]) + win // 2, int(sp[1]) + win // 2)
        pick = scatter_cells(gm, rect, n, 'foot', rnd, mind, near=sp)
        if pick is None:
            continue
        order, length = tour([(x + .5, y + .5) for x, y in pick], sp)
        if length > cap:
            continue
        for i, (x, y) in enumerate(order, 1):
            gm.place('%s.%d' % (name, i), x, y, 'ground', 1.5, 'pick')
        gm.place(name + '.s', sp[0], sp[1], 'ground', 1.5, 'pad', 'foot')
        gm.claim(*sp)
        return '%s.1..%s.%d' % (name, name, n), n
    return None


def blast_zones(gm, size=12):
    """[(count, x0, y0, x1, y1)] windows over the box clusters, best first, apart from each other."""
    ws = window_scores(gm.a.crates, size, 1)
    out = []
    for w in ws:
        if w[0] < 6:
            break
        if apart(out, w, 14):
            out.append(w)
        if len(out) >= 3:
            break
    return out


def put_blast(gm, name, w, mode='car'):
    """A blast zone (the box bounding the crates of the window, padded) and a start pad near it. -> (zone name, n) or None."""
    cr = [(x, y) for (x, y) in gm.a.crates if w[1] <= x <= w[3] and w[2] <= y <= w[4]]
    x0, y0 = min(c[0] for c in cr) - 1, min(c[1] for c in cr) - 1
    x1, y1 = max(c[0] for c in cr) + 1, max(c[1] for c in cr) + 1
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    sp = None
    for md in (mode, 'foot'):
        sp = gm.beacon_spot(cx, cy, md, 1, 18)
        if sp:
            break
    if not sp:
        return None
    gm.zone(name + '.z', x0, y0, x1, y1)
    n = max(4, min(8, int(len(cr) * 0.8)))
    return name + '.z', n, sp, md


def ramp_windows(gm, size=14):
    a = gm.a
    cells = [(i >> 7, i & 127) for i in range(A.N * A.N)
             if a.kind[i] == 'ramp' and i in a.main_car and a.hi[i] - a.lo[i] >= 256]
    ws = [w for w in window_scores(cells, size, 2) if w[0] >= 8]
    out = []
    for w in ws:
        if apart(out, w, 16):
            out.append(w)
        if len(out) >= 4:
            break
    return out


def put_zone_start(gm, name, w):
    """A stunt zone over the window (its zone box) and a pad just outside it. -> (zone name, spot) or None."""
    cx, cy = (w[1] + w[3]) / 2.0, (w[2] + w[4]) / 2.0
    sp = gm.beacon_spot(cx, cy, 'car', 1, 22)
    if not sp:
        return None
    gm.zone(name + '.z', w[1], w[2], w[3], w[4])
    return name + '.z', sp


def tower_tops(gm, count=3):
    """The tallest distinct flat tops (area 9 and up) the hand acts do not land on, tallest first."""
    a = gm.a
    tops = [rf for rf in list(a.towers) + list(a.roofs) + list(a.decks) if rf.pad and rf.area >= 9 and gm.land_ok(rf)]
    tops.sort(key=lambda r: (-r.h, -r.area, r.pad))
    out = []
    for rf in tops:
        p = (rf.pad[0] + .5, rf.pad[1] + .5)
        if any(math.hypot(p[0] - ux, p[1] - uy) < 4 for ux, uy in gm.lands):
            continue
        if any(math.hypot(p[0] - q.pad[0] - .5, p[1] - q.pad[1] - .5) < 5 for q in out):
            continue
        out.append(rf)
        if len(out) >= count:
            break
    return out


def lane_points(gm, rnd, n, within=40, runs=None):
    """n car spawn points on lane runs near each other: [(x, y)]."""
    from gen_common import lane_runs, lane_pt
    runs = runs or lane_runs(gm.a, 14)
    rnd.shuffle(runs)
    for r0 in runs:
        t0 = rnd.randint(r0[2] + 2, r0[3] - 2)
        c0 = lane_pt(r0, t0)
        near = [r for r in runs if r is not r0 and any(math.hypot(lane_pt(r, t)[0] - c0[0], lane_pt(r, t)[1] - c0[1]) < within
                                                      for t in range(r[2], r[3] + 1, 4))]
        pts = [c0]
        for r in [r0] + near:
            for _ in range(3):
                t = rnd.randint(r[2] + 2, r[3] - 2)
                p = lane_pt(r, t)
                if math.hypot(p[0] - c0[0], p[1] - c0[1]) < within and all(math.hypot(p[0] - q[0], p[1] - q[1]) >= 9 for q in pts):
                    pts.append(p)
                    break
            if len(pts) >= n:
                break
        if len(pts) >= n:
            return pts[:n]
    return None
