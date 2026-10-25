"""Fly generators: ring courses (A* through free air), rooftop chains (landings on roofs a short hop apart) and the
start rings they share. All deterministic from the map and a name."""
import math

import atlas as A
import routes

RING_NAME = {'x': 'ring_x', 'y': 'ring_y', 'h': 'ring_h'}


def start_ring(gm, name, near, toward, dist=9.0, lift=1200, tries=16, rnd=None):
    """A start ring for a fly mission: `dist` cells from `near` (x, y, h) on a side where the air is clear, facing `toward`
    (x, y, h), 1000 and more over whatever is below it, and a beacon spot. -> (x, y, h, r, axis) or None."""
    best = None
    ang0 = rnd.uniform(0, 6.28) if rnd else 0.0
    for k in range(tries):
        ang = ang0 + k * 6.2832 / tries
        for d in (dist, dist + 3, dist - 3):
            x, y = round(near[0] + d * math.cos(ang), 2), round(near[1] + d * math.sin(ang), 2)
            if not gm.beacon_ok(x, y):
                continue
            h = max(near[2] + lift - 400, gm.top_near(x, y, 2) + lift)
            h = int(math.ceil(h / 64.0) * 64)
            ax = routes.ring_axis(None, (x, y, h), toward)
            if routes.disc_clear(gm.a, x, y, h, 1.6, ax, 192) is None and routes.seg_clear(gm.a, (x, y, h), (toward[0], toward[1], toward[2] + 500), 192) is None:
                best = (x, y, h, 1.6, ax)
                break
        if best:
            break
    return best


def course(gm, tag, k, legs=3, leg=(15, 26), spacing=7.0, hrange=(1500, 4200)):
    """A ring course of `legs` legs from a random free spot. -> (start ring, rings) or None."""
    rnd = gm.rng('%s%d' % (tag, k))
    a, g = gm.a, gm.g
    for attempt in range(400):
        x, y = rnd.uniform(14, 114), rnd.uniform(14, 114)
        if not gm.beacon_ok(x, y):
            continue
        top = gm.top_near(x, y, 2)
        h0 = max(hrange[0], top + 1300)
        h0 = int(math.ceil(h0 / 256.0) * 256)
        if h0 > hrange[1]:
            continue
        anchors = [(x, y, h0)]
        ang = rnd.uniform(0, 6.28)
        ok = True
        for _ in range(legs):
            ang += rnd.uniform(-1.3, 1.3)
            d = rnd.uniform(*leg)
            nx, ny = anchors[-1][0] + d * math.cos(ang), anchors[-1][1] + d * math.sin(ang)
            if not (10 <= nx <= 118 and 10 <= ny <= 118):
                ok = False
                break
            nh = anchors[-1][2] + rnd.choice((-512, -256, 0, 0, 256, 512))
            nh = max(hrange[0], min(hrange[1], nh, ))
            nh = max(nh, gm.top_near(nx, ny, 2) + 900)
            if nh > hrange[1] + 800:
                ok = False
                break
            anchors.append((nx, ny, int(math.ceil(nh / 256.0) * 256)))
        if not ok:
            continue
        rings, bad = routes.ring_course(a, g, anchors, spacing, 1.1, 0.7, True)
        if bad or not 7 <= len(rings) <= 15:
            continue
        s = rings[0]
        if s[2] - gm.top_near(s[0], s[1], 0) < 1000:
            continue
        body = rings[1:]
        if len(body) < 6:
            continue
        return s, body
    gm.problems.append('no ring course for %s%d' % (tag, k))
    return None


def put_course(gm, name, s, body):
    """The places of a ring course: NAME.s the start ring, NAME.1.. the rings."""
    gm.place(name + '.s', s[0], s[1], s[2], s[3], RING_NAME[s[4]], 'air')
    gm.claim(s[0], s[1])
    for i, (x, y, h, r, ax) in enumerate(body, 1):
        gm.place('%s.%d' % (name, i), x, y, h, r, RING_NAME[ax], 'air')
    return '%s.1..%s.%d' % (name, name, len(body)), len(body)


def pads(gm, min_area=20):
    """The flat tops a landing may use, each (x, y, h, area, Roof): roofs and decks, then towers."""
    out = []
    for rf in list(gm.a.roofs) + list(gm.a.decks):
        if rf.pad and rf.area >= min_area and gm.land_ok(rf):
            out.append(rf)
    return out


def chain(gm, tag, k, hops=5, hop=(5.0, 12.0), used=()):
    """A rooftop chain: `hops` roofs each a short hop from the one before (area 20 and up). -> (start ring, [Roof]) or None."""
    rnd = gm.rng('%s%d' % (tag, k))
    roofs = pads(gm)
    if len(roofs) < hops + 2:
        return ground_chain(gm, tag, k, hops, rnd)
    pos = lambda r: (r.pad[0] + .5, r.pad[1] + .5)
    near_used = lambda r: any(math.hypot(pos(r)[0] - ux, pos(r)[1] - uy) < 3.0 for ux, uy in list(gm.lands) + list(used))
    cand = [r for r in roofs if not near_used(r)]
    if len(cand) < hops:
        cand = roofs
    best = None
    for attempt in range(200):
        first = rnd.choice(cand)
        seq = [first]
        while len(seq) < hops:
            px, py = pos(seq[-1])
            nb = [r for r in cand if r not in seq and hop[0] <= math.hypot(pos(r)[0] - px, pos(r)[1] - py) <= hop[1]
                  and all(math.hypot(pos(r)[0] - pos(q)[0], pos(r)[1] - pos(q)[1]) >= 4.0 for q in seq)]
            if not nb:
                break
            seq.append(rnd.choice(nb))
        if len(seq) < hops:
            if best is None or len(seq) > len(best[0]):
                sr = start_ring(gm, '', (pos(seq[0])[0], pos(seq[0])[1], seq[0].h), (pos(seq[0])[0], pos(seq[0])[1], seq[0].h), rnd=rnd)
                if sr and len(seq) >= 3:
                    best = (seq, sr)
            continue
        p0 = pos(seq[0])
        sr = start_ring(gm, '', (p0[0], p0[1], seq[0].h), (p0[0], p0[1], seq[0].h), rnd=rnd)
        if sr:
            return sr, seq
    if best:
        return best[1], best[0]
    return ground_chain(gm, tag, k, hops, rnd)


def put_chain(gm, name, sr, seq):
    gm.place(name + '.s', sr[0], sr[1], sr[2], sr[3], RING_NAME[sr[4]], 'air')
    gm.claim(sr[0], sr[1])
    for i, rf in enumerate(seq, 1):
        gm.place('%s.%d' % (name, i), rf.pad[0] + .5, rf.pad[1] + .5, rf.h, 1.8, 'pad', 'roof')
    return len(seq)


class GroundPad:
    """A landing pad on open ground, shaped like a Roof for put_chain."""
    def __init__(self, cx, cz):
        self.pad, self.h, self.area = (cx, cz), 0, 9


def ground_chain(gm, tag, k, hops, rnd):
    """Where the map has no roofs: pads on open ground a short hop apart. -> (start ring, [GroundPad]) or None."""
    for attempt in range(120):
        x, y = rnd.uniform(14, 114), rnd.uniform(14, 114)
        p = gm.spot(x, y, 'car', 2, 10)
        if not p:
            continue
        seq = [p]
        ang = rnd.uniform(0, 6.28)
        while len(seq) < hops:
            got = None
            for t in range(10):
                a2 = ang + rnd.uniform(-1.0, 1.0)
                d = rnd.uniform(7.0, 12.0)
                q = gm.spot(seq[-1][0] + d * math.cos(a2), seq[-1][1] + d * math.sin(a2), 'car', 2, 3)
                if q and all(math.hypot(q[0] - s[0], q[1] - s[1]) >= 5 for s in seq) and 7.0 <= math.hypot(q[0] - seq[-1][0], q[1] - seq[-1][1]) <= 12.5:
                    got = q
                    ang = a2
                    break
            if not got:
                break
            seq.append(got)
        if len(seq) < hops:
            continue
        sr = start_ring(gm, '', (seq[0][0], seq[0][1], 0), (seq[0][0], seq[0][1], 0), rnd=rnd)
        if sr:
            return sr, [GroundPad(int(q[0]), int(q[1])) for q in seq]
    gm.problems.append('no ground chain for %s%d' % (tag, k))
    return None
