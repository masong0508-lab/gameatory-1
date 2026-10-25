"""The Killing Zone's validators AV1-AV9 (stage2.md 6.5), on the 128 x 128 columns mkarena painted. Each takes
what it needs and returns a list of problems; mkarena.build stops the build on any. They use Payback's own
collision as tools/mkworld.py models it (pb_floor, pb_blocked, the cell edges and heights)."""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import mkworld   # noqa: E402

N = 128
STREET = 0x100
KNEE = mkworld.PB_KNEE                # Payback stops a man by a wall only below his knee: the most a floor may step up without one
MID = 24                              # (and colcheck calls a floor that lifts him by over 192 units across an open edge a wall)
FLAT = 0x20                           # how far from the street a floor is still level ground (mksolo.CLIMB)
STEP = mkworld.EDGE_STEP              # edge 0 -y, 1 +x, 2 +y, 3 -x
EDGE_PTS = (((0, 0), (2047, 0)), ((2047, 0), (2047, 2047)), ((0, 2047), (2047, 2047)), ((0, 0), (0, 2047)))
LANE, ROADLIKE = 0x0f, 0x2f
AHEAD = 3                             # cells a spawn must have clear in front of it (AV6)
HEADING = {1: 0, 2: 1, 4: 2, 8: 3}    # a lane's bit -> the edge it runs toward


def prep(cols):
    return [mkworld.pb_records(c) for c in cols], [c[3] for c in cols]


def floor_edge(rec, e):
    """The heights (raw) of a floor record along its edge e, the same way round for both cells that share it."""
    return tuple(mkworld.pb_slope(rec, fx, fy) for fx, fy in EDGE_PTS[e])


def needs_wall(ha, hb):
    """Must the floor with edge heights ha have a wall against a neighbour whose floor has hb along the same edge?
    Yes where entering it would lift a man over his knee, or by more than a step he could see (colcheck's 192 units)."""
    return max(p - q for p, q in zip(ha, hb)) > KNEE or (sum(ha) - sum(hb)) / 2 > MID


def floor_rec(recs, k=0):
    r = recs[k]
    return r if r[3] and r[4] else None


def reach_graph(recs, lanes, car, mask):
    """Payback's walking rules as a graph: nodes (cell, record), edges to what one gets to across a cell edge, from
    every cell with a lane (mask). {node: set of nodes}, and each node's standing height."""
    adj, height, todo = collections.defaultdict(set), {}, []
    for i in range(N * N):
        if lanes[i] & mask:
            k, h = mkworld.pb_floor(recs[i], 1024, 1024, STREET)
            if k is not None and (i, k) not in height:
                height[i, k] = h
                todo.append((i, k))
    while todo:
        i, k = todo.pop()
        if recs[i][k][4] == 0x40:
            continue
        h = height[i, k]
        x, y = divmod(i, N)
        for e, (dx, dy) in enumerate(STEP):
            if not (0 <= x + dx < N and 0 <= y + dy < N):
                continue
            j = (x + dx) * N + y + dy
            he = mkworld.pb_floor(recs[i], *mkworld.PB_EXIT[e], h)[1]
            if mkworld.pb_blocked(recs[j], e, he, car):
                continue
            hin = mkworld.pb_floor(recs[j], *mkworld.PB_ENTRY[e], he)[1]
            kj, hj = mkworld.pb_floor(recs[j], 1024, 1024, hin)
            if kj is None:
                continue
            adj[i, k].add((j, kj))
            if (j, kj) not in height:
                height[j, kj] = hj
                todo.append((j, kj))
    return adj, height


def forward(adj, start):
    seen, todo = {start}, [start]
    while todo:
        for m in adj.get(todo.pop(), ()):
            if m not in seen:
                seen.add(m)
                todo.append(m)
    return seen


def reverse(adj):
    r = collections.defaultdict(set)
    for a, bs in adj.items():
        for b in bs:
            r[b].add(a)
    return r


def lane_node(recs, lanes, x, y, mask=LANE, reach=6):
    """The node of the nearest cell with a lane (mask) to (x, y) within reach cells."""
    best = None
    for dx in range(-reach, reach + 1):
        for dy in range(-reach, reach + 1):
            if 0 <= x + dx < N and 0 <= y + dy < N and lanes[(x + dx) * N + y + dy] & mask \
                    and (best is None or abs(dx) + abs(dy) < best[0]):
                j = (x + dx) * N + y + dy
                k, _ = mkworld.pb_floor(recs[j], 1024, 1024, STREET)
                if k is not None:
                    best = (abs(dx) + abs(dy), (j, k))
    return best[1] if best else None


def av1(cols, spawns):
    """Every road cell is reachable on foot and by car from every spawn (and every spawn from every other: all reach
    spawn 0, which reaches all)."""
    recs, lanes = prep(cols)
    bad = []
    if not spawns:
        return ['no spawns']
    for car, mask, name in ((False, ROADLIKE, 'on foot'), (True, LANE, 'by car')):
        adj, height = reach_graph(recs, lanes, car, mask)
        roads = {n for n in height if lanes[n[0]] & LANE}
        s0 = lane_node(recs, lanes, spawns[0][0], spawns[0][1], mask)
        if s0 is None or s0 not in height:
            bad.append('spawn 0 is not on a road %s' % name)
            continue
        fw = forward(adj, s0)
        out = sorted(n[0] for n in roads - fw)
        if out:
            bad.append('%d road cells are out of reach %s from spawn 0, first (%d, %d)'
                       % (len(out), name, out[0] // N, out[0] % N))
        rv = forward(reverse(adj), s0)
        for sx, sy, _ in spawns:
            n = lane_node(recs, lanes, sx, sy, mask)
            if n is None or n not in rv:
                bad.append('spawn (%d, %d) cannot reach spawn 0 %s' % (sx, sy, name))
    return bad


def av2(cols, skip=lambda x, y: False):
    """No single isolated column inside a road: a gap between two lanes of one road, or a lane with no road beside it."""
    recs, lanes = prep(cols)
    bad = []
    for x in range(1, N - 1):
        for y in range(1, N - 1):
            if skip(x, y):
                continue
            i = x * N + y
            r = lambda dx, dy: bool(lanes[(x + dx) * N + y + dy] & ROADLIKE)
            ln = lambda dx, dy: bool(lanes[(x + dx) * N + y + dy] & LANE)
            if not lanes[i] & ROADLIKE and ((ln(-1, 0) and ln(1, 0)) or (ln(0, -1) and ln(0, 1))):
                bad.append('a gap in the road at (%d, %d)' % (x, y))
            elif lanes[i] & LANE and not any(r(dx, dy) for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))):
                bad.append('a lone lane cell at (%d, %d)' % (x, y))
    return bad


def av3(cols, skip=lambda x, y: False):
    """Floors are continuous: where one steps up from a neighbour by more than the climb limit that edge has a wall
    on the high side (so nobody is lifted across it), and two slopes of the same direction side by side meet exactly."""
    recs, lanes = prep(cols)
    bad = []
    for x in range(N):
        for y in range(N):
            if skip(x, y):
                continue
            i = x * N + y
            a = floor_rec(recs[i])
            if not a:
                continue
            for e in range(4):
                nx, ny = x + STEP[e][0], y + STEP[e][1]
                if not (0 <= nx < N and 0 <= ny < N):
                    continue
                b = floor_rec(recs[nx * N + ny])
                if not b:
                    continue
                ha, hb = floor_edge(a, e), floor_edge(b, e ^ 2)
                if a[4] == 0x40 or b[4] == 0x40:
                    continue
                walled = (a[5][e] >> 12) & 7 not in (0, 5)
                if needs_wall(ha, hb) and not walled:
                    bad.append('a step of %d over the edge %d of (%d, %d) without a wall'
                               % (max(p - q for p, q in zip(ha, hb)), e, x, y))
                if a[3] == b[3] and a[3] in (2, 3, 4, 5) and max(abs(p - q) for p, q in zip(ha, hb)) > 2:
                    bad.append('slopes (%d, %d) and (%d, %d) do not meet: %s vs %s' % (x, y, nx, ny, ha, hb))
    return bad


def av4(cols, clearance=256):
    """A deck over a floor has at least 2048 units (256 steps) under it, or is solid to that floor."""
    recs, _ = prep(cols)
    bad = []
    for i, rs in enumerate(recs):
        f = floor_rec(rs, 0)
        if not f:
            continue
        top = max(f[1], f[2])
        for k in (1, 2):
            r = rs[k]
            if r[3] and r[4] and r[4] != 0x40:
                gap = r[0] - top
                if 0 < gap < clearance:
                    bad.append('a deck at (%d, %d) with %d units under it' % (i // N, i % N, gap * 8))
    return bad


def walkable_flat(recs, i):
    f = floor_rec(recs[i])
    return bool(f) and f[3] == 1 and f[4] != 0x40 and abs(f[1] - STREET) <= FLAT


def av5(cols, phones):
    """Phones are on walkable flat cells beside a road with the 3 x 3 round them clear."""
    recs, lanes = prep(cols)
    adj, height = reach_graph(recs, lanes, False, ROADLIKE)
    bad = []
    for x, y, k in phones:
        i = x * N + y
        if cols[i][20 * k + 1] != 0x0e:
            bad.append('phone (%d, %d) has no phone in its column' % (x, y))
        if (i, k) not in height:
            bad.append('phone (%d, %d) is not on a floor people reach' % (x, y))
        if not any(lanes[(x + dx) * N + y + dy] & ROADLIKE for dx, dy in STEP):
            bad.append('phone (%d, %d) is not beside a road' % (x, y))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                j = (x + dx) * N + y + dy
                if not (0 <= x + dx < N and 0 <= y + dy < N) or not walkable_flat(recs, j) or (j, 0) not in height:
                    bad.append('phone (%d, %d): the cell (%d, %d) round it is not clear ground' % (x, y, x + dx, y + dy))
    return bad


def heading(cols, x, y):
    """The edge a start at (x, y) faces: along its lane, or along the lane beside a kerb."""
    for dx, dy in ((0, 0),) + tuple(STEP):
        b = cols[(x + dx) * N + y + dy][3] & LANE
        if b in HEADING:
            return HEADING[b]
    return None


def clear_ahead(recs, x, y, e):
    """AHEAD cells from (x, y) toward edge e that a man can stand on: no wall, no step, no building. None if all are,
    else the number of the first that is not (1 for the next cell)."""
    cx, cy = x, y
    for step in range(AHEAD):
        cx, cy = cx + STEP[e][0], cy + STEP[e][1]
        if not (0 <= cx < N and 0 <= cy < N):
            return step + 1
        j = cx * N + cy
        f = floor_rec(recs[j])
        if not f or max(f[1], f[2]) > STREET + FLAT or mkworld.pb_blocked(recs[j], e, STREET, True):
            return step + 1
    return None


def av6(cols, spawns, pre=None):
    """Spawns are on a road or its kerb and have AHEAD cells clear in front of them: along the lane beside them,
    or (Payback's own starts at a kerb with no lane by it) toward at least one side."""
    recs, lanes = pre or prep(cols)
    bad = []
    for x, y, k in spawns:
        if not lanes[x * N + y] & ROADLIKE:
            bad.append('spawn (%d, %d) is not on a road' % (x, y))
            continue
        e = heading(cols, x, y)
        if e is None:
            if all(clear_ahead(recs, x, y, d) for d in range(4)):
                bad.append('spawn (%d, %d) is walled in on every side' % (x, y))
        else:
            n = clear_ahead(recs, x, y, e)
            if n:
                bad.append('spawn (%d, %d) faces a wall at %d cells' % (x, y, n))
    return bad


def av7(arena):
    """The density governor holds in every 16 x 16 sector: at most 70 boxes and 6 towers of 6144 or more."""
    boxes, tall = arena.sector_boxes((0, 0, N - 1, N - 1))
    bad = ['sector %s has %d boxes' % (s, n) for s, n in sorted(boxes.items()) if n > 70]
    bad += ['sector %s has %d tall towers' % (s, n) for s, n in sorted(tall.items()) if n > 6]
    return bad


def av8(data, cols, stamp, minimap):
    return minimap.check(data, [c[3] & LANE for c in cols], stamp)


def av9(cols, gates, pit):
    """Each gate carries its two lanes from the street into the Pit, at least 4 cells past its wall, level."""
    recs, lanes = prep(cols)
    bad = []
    px0, py0, px1, py1 = pit
    for g in gates:
        x0, y0, x1, y1 = g['road']
        horizontal = (y1 - y0) == 3
        if horizontal:
            across = (y0 + 1, y0 + 2)
            west = x0 < px0
            path = list(range(x0 + 1, px0 + 4)) if west else list(range(x1 - 1, px1 - 4, -1))
            cells = [[(x, a) for x in path] for a in across]
            inside = sum(1 for x in path if px0 <= x <= px1)
        else:
            across = (x0 + 1, x0 + 2)
            north = y0 < py0
            path = list(range(y0 + 1, py0 + 4)) if north else list(range(y1 - 1, py1 - 4, -1))
            cells = [[(a, y) for y in path] for a in across]
            inside = sum(1 for y in path if py0 <= y <= py1)
        if inside < 4:
            bad.append('%s: only %d cells inside the Pit' % (g['name'], inside))
        for line in cells:
            hs = set()
            for x, y in line:
                i = x * N + y
                f = floor_rec(recs[i])
                if not lanes[i] & LANE or not f:
                    bad.append('%s: no lane at (%d, %d)' % (g['name'], x, y))
                else:
                    hs.add(f[1])
            if len(hs) > 1:
                bad.append('%s: the lane changes height along its way' % g['name'])
    return bad


def loops_clear(cols, loops):
    """A loop needs its 14 x 5 cells of open flat ground (mkworld.pick_loop): nothing but flat street-level floor."""
    recs, _ = prep(cols)
    bad = []
    for x, z, d, r, w in loops:
        cx, cz = x / mkworld.CELL, z / mkworld.CELL
        x0, z0 = int(cx - 6.5), int(cz - 3.25)
        for xx in range(x0, x0 + 14):
            for zz in range(z0, z0 + 5):
                f = floor_rec(recs[xx * N + zz])
                if not f or f[3] != 1 or max(f[1], f[2]) != STREET or cols[xx * N + zz][3] & ROADLIKE:
                    bad.append('loop at (%.1f, %.1f): (%d, %d) is not open flat ground' % (cx, cz, xx, zz))
                    break
    return bad


def check(arena, cols, spawns, phones, minimap_data, stamp, minimap):
    """All validators; {name: problems}."""
    pit, gates = tuple(arena.plan['pit']), arena.plan['gates']
    skip = lambda x, y: arena.in_pit(x, y) and arena.kind[x * N + y] == 'pit'
    return collections.OrderedDict([
        ('AV1', av1(cols, spawns)), ('AV2', av2(cols, skip)), ('AV3', av3(cols, skip)), ('AV4', av4(cols)),
        ('AV5', av5(cols, phones)), ('AV6', av6(cols, spawns)), ('AV7', av7(arena)),
        ('AV8', av8(minimap_data, cols, stamp, minimap)), ('AV9', av9(cols, gates, pit)),
        ('loops', loops_clear(cols, arena.loops))])
