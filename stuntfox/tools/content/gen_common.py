"""What the generators share: a map under construction (its .places lines, its .sfm text, the beacons already taken),
the floor and spot finders over the atlas, and the seeded random source. Everything here is a pure function of the atlas,
the hand content and the seeds: running a generator twice gives the same text (tests/content checks it)."""
import collections
import math
import random

import atlas as A
import routes
import validate as V

TITLE_CHARS = V.TITLE_CHARS


class GMap:
    def __init__(self, level, a, hand=None):
        self.level, self.a = level, a
        self._g = None
        self.pl = ['map %d' % level]
        self.sf = []
        self.problems = []
        self.count = collections.Counter()
        hand = hand or {}
        self.taken = list(hand.get('beacons', []))          # (x, y) of every start beacon so far, the hand acts' first
        self.lands = list(hand.get('lands', []))            # (x, y) of the hand acts' landings
        self.far = V.start_far(a)
        self.names = set(hand.get('names', ()))
        self.titles = set()
        self.made = set()

    @property
    def g(self):
        if self._g is None:
            self._g = routes.AirGrid(self.a)
        return self._g

    def rng(self, tag):
        return random.Random('sf:%d:%s' % (self.level, tag))

    def note(self, text):
        self.pl.append('# ' + text)

    def place(self, name, x, y, h, r, *flags):
        assert name not in self.names, 'place %s twice' % name
        self.names.add(name)
        hs = h if isinstance(h, str) else '%d' % h
        self.pl.append('place %s x=%g y=%g h=%s r=%g %s' % (name, round(x, 3), round(y, 3), hs, r, ' '.join(flags)))

    def zone(self, name, x0, y0, x1, y1):
        x0, y0, x1, y1 = (max(3, min(123, v)) for v in (x0, y0, x1, y1))              # (V14: the box inside the playable 2..126)
        self.pl.append('zone %s x=%g..%g y=%g..%g' % (name, x0, x1, y0, y1))

    def mission(self, kind, name, title, ops, **kw):
        """kw: pay score par fail start mode giver tier; ops: the indented lines."""
        assert all(ch in TITLE_CHARS for ch in title) and len(title) <= 19, title
        head = '%s %s "%s" map=%d' % (kind, name, title, self.level)
        for k in ('giver', 'tier', 'par', 'pay', 'score', 'fail', 'start', 'mode'):
            if k in kw and kw[k] is not None:
                head += ' %s=%s' % (k, kw[k])
        self.sf.append(head + '\n' + '\n'.join('  ' + o for o in ops) + '\n')
        self.count[kind] += 1
        self.made.add(name)

    # ---- the ground ----
    def floors(self, cx, cz, mode):
        if not (0 <= cx < A.N and 0 <= cz < A.N):
            return None
        src = self.a.main_foot if mode == 'foot' else self.a.main_car
        return src.get(A.idx(cx, cz))

    def ground(self, x, y, mode='car', h=None, rad=6):
        """The nearest cell centre a mode stands on, (x, y, floor height), or None."""
        best = None
        for dx in range(-rad, rad + 1):
            for dy in range(-rad, rad + 1):
                cx, cz = int(x) + dx, int(y) + dy
                fl = [f for f in (self.floors(cx, cz, mode) or ()) if f >= 0]          # (a place's height is unsigned)
                if fl:
                    hh = min(fl, key=lambda f: abs(f - (h or 0)))
                    d = (cx + .5 - x) ** 2 + (cz + .5 - y) ** 2 + ((hh - (h or 0)) / 1024.0) ** 2
                    if best is None or d < best[0]:
                        best = (d, cx + .5, cz + .5, hh)
        return best[1:] if best else None

    def street_ok(self, cx, cz, mode, rad=1):
        """Level street ground all round (rad cells): a spot to stand a pad or a pick on."""
        src = self.a.main_foot if mode == 'foot' else self.a.main_car
        for ex in range(-rad, rad + 1):
            for ey in range(-rad, rad + 1):
                i = A.idx(cx + ex, cz + ey)
                if not (0 <= cx + ex < A.N and 0 <= cz + ey < A.N) or src.get(i) != [0] or self.a.water[i]:
                    return False
        return True

    def beacon_ok(self, x, y, gap=7.0, far=None):
        """A start beacon at (x, y) keeps clear of the beacons, the phones and Payback's start points."""
        a = self.a
        if not (6 <= x <= 122 and 6 <= y <= 122):
            return False
        if any(math.hypot(x - bx, y - by) < gap for bx, by in self.taken):
            return False
        if any(math.hypot(x - px - .5, y - py - .5) < 4.0 for px, py in a.phones):
            return False
        far = self.far if far is None else far
        return all(math.hypot(x - sx - .5, y - sy - .5) >= far + .5 for sx, sy, _k in a.starts)

    def claim(self, x, y):
        self.taken.append((x, y))

    def spot(self, x, y, mode='car', rad=1, maxd=14, pred=None):
        """The nearest cell centre with open street ground all round that `pred` accepts: (x, y) or None."""
        best = None
        for dx in range(-maxd, maxd + 1):
            for dy in range(-maxd, maxd + 1):
                cx, cz = int(x) + dx, int(y) + dy
                if not (4 <= cx < 124 and 4 <= cz < 124) or not self.street_ok(cx, cz, mode, rad):
                    continue
                if self.a.kind[A.idx(cx, cz)] not in ('ground', 'road', 'kerb'):
                    continue
                if pred and not pred(cx + .5, cz + .5):
                    continue
                d = dx * dx + dy * dy
                if best is None or d < best[0]:
                    best = (d, cx + .5, cz + .5)
        return best[1:] if best else None

    def beacon_spot(self, x, y, mode='car', rad=1, maxd=14, gap=7.0):
        return self.spot(x, y, mode, rad, maxd, lambda px, py: self.beacon_ok(px, py, gap))

    def top_near(self, x, y, r=1):
        t = 0
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                cx, cz = int(x) + dx, int(y) + dy
                if 0 <= cx < A.N and 0 <= cz < A.N:
                    t = max(t, self.a.column_top(cx, cz))
        return t

    def land_ok(self, rf):
        """A roof pad a landing may use: its 3 x 3 flat, no water within a cell, the surface where the pad says."""
        px, pz = rf.pad
        a = self.a
        for dx in (-2, -1, 0, 1, 2):
            for dz in (-2, -1, 0, 1, 2):
                cx, cz = px + dx, pz + dz
                if 0 <= cx < A.N and 0 <= cz < A.N and a.water[A.idx(cx, cz)]:
                    return False
        return 5 <= px <= 122 and 5 <= pz <= 122

    # ---- the files ----
    def places_text(self):
        return '\n'.join(self.pl) + '\n'

    def sfm_text(self):
        return '\n'.join(self.sf)


def lane_runs(a, minlen=10):
    """Straight runs of lane cells a car follows: (axis, line, lo, hi), a pair of lanes counted once. The line is the
    cell index; the run's centre line is line + .5. 'y' runs go along x (y fixed), 'x' runs along y."""
    runs = []
    for axis in ('x', 'y'):
        found = []
        for c in range(A.N):
            cur = None
            for t in range(A.N):
                i = A.idx(c, t) if axis == 'x' else A.idx(t, c)
                ok = (a.lane[i] & 15) != 0 and i in a.main_car and max(a.main_car[i]) >= 0
                if ok and cur is None:
                    cur = t
                if (not ok or t == A.N - 1) and cur is not None:
                    end = t - 1 if not ok else t
                    if end - cur >= minlen:
                        found.append((axis, c, cur, end))
                    cur = None
        keep = []
        for r in found:
            if any(q[1] == r[1] - 1 and q[2] <= r[3] and r[2] <= q[3] for q in found):
                continue                                        # (the second lane of a pair)
            keep.append(r)
        runs += keep
    return runs


def lane_pt(run, t):
    """The cell-centre point on a run at position t along it."""
    axis, c = run[0], run[1] + .5
    return (c, t) if axis == 'x' else (t, c)
