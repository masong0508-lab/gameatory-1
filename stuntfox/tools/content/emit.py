"""From parsed content to the blob: places resolved against the atlas, rings oriented along their course, every
objective that names places given a run of its own in the place table (so a run is always consecutive, as the engine reads
it), text deduplicated, ids from ids.lock, chapters in campaign order with their missions after them (acts first).
"""
import math

import misfmt as F
import places as P
import sfm

PK = F


class RPlace:
    """A place resolved: cells (floats), height in units, radius in cells, a PK_* kind and the mode it is checked for."""
    def __init__(self, name, x, y, h, r, kind, tag, src=''):
        self.name, self.x, self.y, self.h, self.r, self.kind, self.tag, self.src = name, x, y, h, r, kind, tag, src

    @property
    def cell(self):
        return int(self.x), int(self.y)

    @property
    def units(self):
        return (self.x * 1024.0, self.h, self.y * 1024.0)          # world x, y (height), z

    def xyz(self):
        return (self.x * 1024.0, self.y * 1024.0, float(self.h))   # x, z, y: the map's plane first

    def __repr__(self):
        return 'R(%s %.2f,%.2f h%d r%.1f k%d)' % (self.name, self.x, self.y, self.h, self.r, self.kind)


class RObj:
    def __init__(self, o):
        self.src, self.op, self.mode, self.flags = o.src, o.op, o.mode, o.flags
        self.n, self.a, self.b, self.text, self.banner = o.n, o.a, o.b, o.text, o.banner
        self.places = []              # [RPlace]
        self.zone = None              # (RPlace, RPlace)
        self.drop = None
        self.raw = o


class RMis:
    def __init__(self, m):
        self.m = m
        self.name, self.kind, self.title, self.map, self.act = m.name, m.kind, m.title, m.map, m.act
        self.tier, self.giver, self.pay, self.score, self.flags = m.tier, m.giver, m.pay, m.score, m.flags
        self.par_src = m.par
        self.par = m.par
        self.par_from = ''
        self.start = None
        self.objs = []
        self.id = None
        self.src = m.src
        self.gen = m.gen

    @property
    def key(self):
        return 'm%d.%s' % (self.map, self.name)


class Resolver:
    """Resolves the places of every mission against the map places and the atlas."""
    def __init__(self, mapplaces, atlases):
        self.mp, self.at = mapplaces, atlases
        self.auto = {}                 # (level, name) -> PlaceDef: the atlas's own names that were used

    def lookup(self, level, ref, src=''):
        """A name or a literal -> PlaceDef (unresolved height)."""
        if isinstance(ref, P.PlaceDef):
            return ref
        mp = self.mp.get(level)
        pd = mp.lookup(ref) if mp else None
        if pd is None:
            pd = P.auto_place(self.at[level], ref)
            if pd is not None:
                self.auto[(level, ref)] = pd
        if pd is None:
            raise P.PlaceError('%s: no place %s on map %d' % (src, ref, level))
        return pd

    def lookup_zone(self, level, ref, src=''):
        if isinstance(ref, str):
            mp = self.mp.get(level)
            name = mp.alias.get(ref, ref) if mp else ref
            if mp and name in mp.zones:
                return mp.zones[name]
            if mp and name + '.0' in mp.p and name + '.1' in mp.p:
                return mp.p[name + '.0'], mp.p[name + '.1']
        raise P.PlaceError('%s: no zone %s on map %d' % (src, ref, level))

    def one(self, level, ref, src):
        pd = self.lookup(level, ref, src)
        a = self.at[level]
        h = P.resolve_h(a, pd)
        kind = pd.kind
        name = pd.name or 'literal(%.2f,%.2f)' % (pd.x, pd.y)
        return RPlace(name, pd.x, pd.y, h, pd.r, kind, pd.tag, pd.src or src)

    def zone(self, level, ref, src):
        a, b = self.lookup_zone(level, ref, src)
        return (RPlace(a.name, a.x, a.y, 0, 0.0, F.PK_BOX0, None, a.src), RPlace(b.name, b.x, b.y, 0, 0.0, F.PK_BOX1, None, b.src))

    def mission(self, m):
        r = RMis(m)
        lv = m.map
        if m.start is not None:
            r.start = self.one(lv, m.start, m.src)
        for o in m.objs:
            ro = RObj(o)
            if o.op == F.OP_BLAST:                       # its place is a zone name
                if not o.places:
                    raise P.PlaceError('%s: blast ZONE n=N' % o.src)
                ro.zone = self.zone(lv, o.places[0], o.src)
            else:
                ro.places = [self.one(lv, p, o.src) for p in o.places]
                if o.zone is not None:
                    ro.zone = self.zone(lv, o.zone, o.src)
            if o.drop is not None:
                ro.drop = self.one(lv, o.drop, o.src)
            r.objs.append(ro)
        orient(r)
        return r


# ---- rings face the way the course runs ----
def _axis(prev, cur, nxt):
    """RING_X, RING_Y or RING_H for a ring at cur between prev and nxt (RPlaces or None)."""
    a = prev or cur
    b = nxt or cur
    dx, dz, dy = (b.x - a.x) * 1024, (b.y - a.y) * 1024, b.h - a.h
    if prev is None and nxt is None:
        return F.PK_RING_X
    if abs(dy) > 1.2 * max(abs(dx), abs(dz)):
        return F.PK_RING_H
    return F.PK_RING_X if abs(dx) >= abs(dz) else F.PK_RING_Y


def orient(m):
    """Give every ring place of the mission its axis (a ring named with a kind keeps it)."""
    last = m.start
    seq = []
    for o in m.objs:
        if o.op == F.OP_RINGS:
            seq.append(o)
    for o in m.objs:
        if o.op != F.OP_RINGS:
            if o.places:
                last = o.places[-1]
            continue
        ps = o.places
        for i, p in enumerate(ps):
            if p.kind in (F.PK_RING_X, F.PK_RING_Y, F.PK_RING_H):
                continue
            prev = ps[i - 1] if i else last
            nxt = ps[i + 1] if i + 1 < len(ps) else None
            p.kind = _axis(prev, p, nxt)
        last = ps[-1] if ps else last
    if m.start is not None and m.start.kind in (P.AUTO_RING,):
        tgt = next((o.places[0] for o in m.objs if o.places), None)
        m.start.kind = _axis(None, m.start, tgt) if tgt else F.PK_RING_X


def kind_for(op, i, n):
    """The PK_ kind a place gets from the objective that uses it (rings keep their axis)."""
    if op == F.OP_LAND:
        return F.PK_PAD
    if op == F.OP_COLLECT or op == F.OP_CRATES:
        return F.PK_PICK
    if op in (F.OP_CHASE, F.OP_DESTROY, F.OP_ESCORT, F.OP_SPAWNVEH):
        return F.PK_SPAWN
    if op == F.OP_DELIVER and i == 0:
        return F.PK_PICK
    return F.PK_POINT


# ---- the blob ----
class Blob:
    def __init__(self):
        self.texts = ['']
        self.tx = {'': 0}
        self.places = []
        self.px = {}
        self.objs = []
        self.mis = []
        self.chapters = []
        self.names = []

    def text(self, s):
        if s not in self.tx:
            self.tx[s] = len(self.texts)
            self.texts.append(s)
        return self.tx[s]

    def place(self, p, kind=None, share=True):
        try:
            hh = F.h_to(p.h)
        except AssertionError as ex:
            raise ValueError('place %s (%s): %s' % (getattr(p, 'name', '?'), getattr(p, 'src', ''), ex))
        d = dict(x8=int(round(p.x * 8)), y8=int(round(p.y * 8)), h=hh, r8=min(255, int(round(p.r * 8))),
                 kind=p.kind if kind is None else kind)
        if not (0 <= d['x8'] < 65536 and 0 <= d['y8'] < 65536):
            raise ValueError('place %s is off the 16 bit grid' % p)
        key = tuple(sorted(d.items()))
        if share and key in self.px:
            return self.px[key]
        self.places.append(d)
        if share:
            self.px[key] = len(self.places) - 1
        return len(self.places) - 1

    def run(self, ps, kinds):
        """A fresh run of consecutive places."""
        at = len(self.places)
        for p, k in zip(ps, kinds):
            self.place(p, k, share=False)
        return at


def build_blob(order, chapters, consts):
    """order: [(chapter index, [RMis])] with each mission's id set, par final; chapters: sfm.Chapter list."""
    b = Blob()
    for ch, mlist in order:
        c = chapters[ch]
        mis0 = len(b.mis)
        for m in mlist:
            first = len(b.objs)
            for o in m.objs:
                b.objs.append(emit_obj(b, m, o))
            start = b.place(m.start) if m.start is not None else F.NOPLACE
            brief = next((o.text for o in m.objs if o.op == F.OP_BRIEF and o.text), '')
            b.mis.append(dict(id=m.id, map=m.map, kind=m.kind, act=m.act, tier=m.tier, flags=m.flags & 0xffff,
                              title=b.text(m.title), brief=b.text(brief), obj0=first, nobj=len(m.objs), giver=m.giver,
                              start=start, par=m.par, pay=m.pay, score=m.score))
            b.names.append(m.key)
        nact = sum(1 for m in mlist if m.kind == F.MK_ACT)
        b.chapters.append(dict(map=c.map, flags=c.flags, nact=nact, split=c.split, mis0=mis0, nmis=len(mlist),
                               title=b.text(c.title), brief=b.text(c.brief), hx2=c.hover[0], hy2=c.hover[1],
                               next=0xffff))
    for i, c in enumerate(b.chapters):
        if i + 1 < len(b.chapters) and not (chapters[i].flags & F.CH_FINAL) and not (chapters[i + 1].flags & F.CH_RESERVED):
            c['next'] = i + 1
    return b


def emit_obj(b, m, o):
    d = dict(op=o.op, flags=o.flags, mode=o.mode, n=0, place=0, a=0, b=0, text=0)
    op = o.op
    if o.zone is not None and op in (F.OP_BLAST, F.OP_CEIL, F.OP_ZONE, F.OP_STUNT):
        z0 = b.run(list(o.zone), [F.PK_BOX0, F.PK_BOX1])
        if op == F.OP_STUNT:
            d['b'] = z0
        else:
            d['place'] = z0
    elif op == F.OP_STUNT:
        d['b'] = -1
    if o.places:
        kinds = []
        for i, p in enumerate(o.places):
            kinds.append(p.kind if p.kind in (F.PK_RING_X, F.PK_RING_Y, F.PK_RING_H) and op == F.OP_RINGS else kind_for(op, i, len(o.places)))
        d['place'] = b.run(o.places, kinds)
        d['n'] = len(o.places)
    if o.n is not None:
        d['n'] = o.n
    if op in (F.OP_GOTO, F.OP_LAND, F.OP_CHASE, F.OP_FOES, F.OP_BOSS, F.OP_DEFEND, F.OP_SPAWNVEH):
        d['n'] = o.n if o.n is not None else 0
    if op == F.OP_ESCORT:
        d['n'] = 2
    if op == F.OP_CRATES:
        d['b'] = b.place(o.drop, F.PK_POINT, share=False)
    elif op in (F.OP_DESTROY,):
        pass
    d['a'] = o.a
    if op not in (F.OP_CRATES, F.OP_STUNT):
        d['b'] = o.b if op != F.OP_STUNT else d['b']
    if op == F.OP_STUNT:
        d['a'] = o.a
    if op == F.OP_BRIEF:
        d['a'] = b.text(o.banner) if o.banner else 0
        d['text'] = b.text(o.text)
    elif op in (F.OP_TALK, F.OP_CARD):
        d['text'] = b.text(o.text)
    elif o.text:
        d['text'] = b.text(o.text)
    for k in ('a', 'b'):
        if not -32768 <= d[k] <= 32767:
            raise ValueError('%s: %s=%d does not fit 16 bits' % (o.src, k, d[k]))
    return d


def pack(b, names=True):
    """The blob. The mission keys (names) are for the host tools: the ROM's copy leaves them out (names=False; sfc.build writes
    them to a sidecar file the harness reads)."""
    return F.pack(b.chapters, b.mis, b.objs, b.places, b.texts, b.names if names else ())
