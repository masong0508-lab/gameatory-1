"""Places: named points of a map, in cells (decimals) with heights in world units, read from content/maps/m<NN>.places
(hand) and content/maps/gen/m<NN>.places (generated), and resolved against the atlas.

    map 3
    place fox_field.pad  x=108.5 y=13.5 h=ground r=2 pad
    place canyon.r1      x=105.5 y=90   h=1500   r=1.5 ring
    zone  canyon.trench  x=104..107 y=56..91
    alias fox.pad = fox_field.pad

Keys: x, y (cells); h a number (units), or ground / top / deck with an optional +N or -N (the atlas resolves them: the floor
a man or car stands on in that cell, the highest solid there, a deck's top); r in cells (default 1.5); the kind word
(point pad ring ring_x ring_y ring_h pick spawn; "ring" takes its axis from the way the course runs); the mode the place
is checked for (foot car air roof any). A zone is an inclusive cell range, made into two corner places NAME.0 and NAME.1.

Names the atlas gives without a line here: roof.N tower.N deck.N (a pad of the Nth largest roof, tallest tower, largest
deck), start.N (Payback's Nth start point) and phone.N. A literal in an objective is (x,y[,h[,r]]) with the same h forms.
"""
import os
import re

import misfmt as F

KINDS = {'point': F.PK_POINT, 'pad': F.PK_PAD, 'ring_x': F.PK_RING_X, 'ring_y': F.PK_RING_Y, 'ring_h': F.PK_RING_H,
         'pick': F.PK_PICK, 'spawn': F.PK_SPAWN, 'box0': F.PK_BOX0, 'box1': F.PK_BOX1}
AUTO_RING = 'ring'                             # the kind word whose axis the course decides
MODES = ('foot', 'car', 'air', 'roof', 'any')
HEXPR = re.compile(r'^(ground|top|deck)?([+-]\d+)?$')
DEFAULT_R = 1.5


class PlaceError(Exception):
    pass


class PlaceDef:
    """A place as written: x, y in cells, h an expression (base, offset) or an absolute number, r cells, kind a PK_* or
    AUTO_RING, tag a mode word or None."""
    def __init__(self, name, x, y, h=('ground', 0), r=DEFAULT_R, kind=F.PK_POINT, tag=None, src=''):
        self.name, self.x, self.y, self.h, self.r, self.kind, self.tag, self.src = name, x, y, h, r, kind, tag, src

    def copy(self, **kw):
        c = PlaceDef(self.name, self.x, self.y, self.h, self.r, self.kind, self.tag, self.src)
        c.__dict__.update(kw)
        return c

    def cell(self):
        return int(self.x), int(self.y)

    def __repr__(self):
        return 'Place(%s %.2f,%.2f h=%s r=%s kind=%s tag=%s)' % (self.name, self.x, self.y, self.h, self.r, self.kind, self.tag)


def parse_h(s):
    """'1500' -> ('abs', 1500); 'ground+300' -> ('ground', 300); 'top' -> ('top', 0)."""
    m = HEXPR.match(s)
    if m and (m.group(1) or m.group(2)):
        if not m.group(1):                      # a bare +N or -N is a number
            return ('abs', int(m.group(2)))
        return (m.group(1), int(m.group(2) or 0))
    try:
        return ('abs', int(float(s)))
    except ValueError:
        raise PlaceError('bad height %r' % s)


def parse_literal(tok, src=''):
    """'(x,y,h,r)' -> a PlaceDef (name '').  h and r are optional; an h that is not a number is a ground / top / deck form."""
    body = tok.strip()[1:-1]
    parts = [p.strip() for p in body.split(',')]
    kw = {}
    pos = []
    for p in parts:
        if '=' in p:
            k, v = p.split('=', 1)
            kw[k] = v
        else:
            pos.append(p)
    if len(pos) < 2:
        raise PlaceError('%s: a literal needs x,y: %r' % (src, tok))
    p = PlaceDef('', float(pos[0]), float(pos[1]), src=src)
    if len(pos) > 2:
        p.h = parse_h(pos[2])
    if len(pos) > 3:
        p.r = float(pos[3])
    for k, v in kw.items():
        if k == 'r':
            p.r = float(v)
        elif k == 'h':
            p.h = parse_h(v)
        elif k == 'kind':
            p.kind = AUTO_RING if v == 'ring' else KINDS[v]
        elif k == 'tag':
            p.tag = v
    return p


def tokens(line):
    """Split a line on spaces, keeping "quoted" strings and (parenthesised) literals whole; # starts a comment."""
    out, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c in ' \t':
            i += 1
        elif c == '#':
            break
        elif c == '"':
            j = line.index('"', i + 1) if '"' in line[i + 1:] else -1
            if j < 0:
                raise PlaceError('unterminated string: %s' % line)
            out.append(line[i:j + 1])
            i = j + 1
        else:
            j = i
            depth = 0
            while j < n and (depth or line[j] not in ' \t'):
                if line[j] == '(':
                    depth += 1
                elif line[j] == ')':
                    depth -= 1
                elif line[j] == '"':                # key="a b"
                    k = line.index('"', j + 1)
                    j = k
                j += 1
            out.append(line[i:j])
            i = j
    return out


class MapPlaces:
    """The named places of one map."""
    def __init__(self, level):
        self.level = level
        self.p = {}                            # name -> PlaceDef
        self.zones = {}                        # name -> (PlaceDef corner 0, corner 1)
        self.alias = {}

    def add(self, pd, src=''):
        if pd.name in self.p or pd.name in self.zones:
            raise PlaceError('%s: place %s is defined twice' % (src, pd.name))
        self.p[pd.name] = pd

    def lookup(self, name):
        name = self.alias.get(name, name)
        return self.p.get(name)


def add_route(cur, t, src):
    """route NAME step=N [h=..] [r=..] [flags] X,Y X,Y ...: the polyline's vertices and a place every step cells along it, as
    NAME.1 ... NAME.n (the first and the last vertex included; at most 16 make a race or a check)."""
    name = t[1]
    kv, flags, pts = {}, [], []
    for tk in t[2:]:
        if '=' in tk:
            k, v = tk.split('=', 1)
            kv[k] = v
        elif ',' in tk:
            x, y = tk.split(',')
            pts.append((float(x), float(y)))
        else:
            flags.append(tk)
    step = float(kv.pop('step', 12))
    h = parse_h(kv.pop('h', 'ground'))
    r = float(kv.pop('r', DEFAULT_R))
    if kv or len(pts) < 2:
        raise PlaceError('%s: route NAME step=N X,Y X,Y ...' % src)
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        d = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        k = max(1, int(-(-d // step)))
        for i in range(1, k + 1):
            out.append((x0 + (x1 - x0) * i / k, y0 + (y1 - y0) * i / k))
    kind, tag = F.PK_POINT, None
    for fl in flags:
        if fl in KINDS:
            kind = KINDS[fl]
        elif fl in MODES:
            tag = fl
        else:
            raise PlaceError('%s: unknown flag %r' % (src, fl))
    for i, (x, y) in enumerate(out, 1):
        cur.add(PlaceDef('%s.%d' % (name, i), round(x, 3), round(y, 3), h, r, kind, tag, src), src)


def parse_file(path, maps):
    """Read a .places file into maps ({level: MapPlaces}); a file may switch the map with a 'map N' line."""
    cur = None
    base = os.path.basename(path)
    with open(path) as f:
        for ln, raw in enumerate(f, 1):
            src = '%s:%d' % (base, ln)
            t = tokens(raw.rstrip('\n'))
            if not t:
                continue
            w = t[0]
            if w == 'map':
                cur = maps.setdefault(int(t[1]), MapPlaces(int(t[1])))
                continue
            if cur is None:
                raise PlaceError('%s: no "map N" line before the first place' % src)
            if w == 'alias':
                if len(t) != 4 or t[2] != '=':
                    raise PlaceError('%s: alias NAME = OTHER' % src)
                cur.alias[t[1]] = t[3]
                continue
            if w == 'route':
                add_route(cur, t, src)
                continue
            if w not in ('place', 'zone'):
                raise PlaceError('%s: unknown line %r' % (src, w))
            name = t[1]
            kv, flags = {}, []
            for tk in t[2:]:
                if '=' in tk:
                    k, v = tk.split('=', 1)
                    kv[k] = v
                else:
                    flags.append(tk)
            if w == 'zone':
                xs, ys = kv['x'], kv['y']
                x0, x1 = (float(v) for v in xs.split('..')) if '..' in xs else (float(xs), float(xs))
                y0, y1 = (float(v) for v in ys.split('..')) if '..' in ys else (float(ys), float(ys))
                a = PlaceDef(name + '.0', x0, y0, ('abs', 0), 0.0, F.PK_BOX0, None, src)
                b = PlaceDef(name + '.1', x1 + 1, y1 + 1, ('abs', 0), 0.0, F.PK_BOX1, None, src)
                if name in cur.p or name in cur.zones:
                    raise PlaceError('%s: place %s is defined twice' % (src, name))
                cur.zones[name] = (a, b)
                continue
            pd = PlaceDef(name, float(kv['x']), float(kv['y']), src=src)
            if 'h' in kv:
                pd.h = parse_h(kv['h'])
            if 'r' in kv:
                pd.r = float(kv['r'])
            for fl in flags:
                if fl == AUTO_RING:
                    pd.kind = AUTO_RING
                elif fl in KINDS:
                    pd.kind = KINDS[fl]
                elif fl in MODES:
                    pd.tag = fl
                else:
                    raise PlaceError('%s: unknown flag %r' % (src, fl))
            unknown = set(kv) - {'x', 'y', 'h', 'r'}
            if unknown:
                raise PlaceError('%s: unknown key %s' % (src, sorted(unknown)))
            cur.add(pd, src)
    return maps


def load_dir(root):
    """All the place files under root (hand ones, then maps/gen/)."""
    maps = {}
    for sub in ('', 'gen'):
        d = os.path.join(root, sub) if sub else root
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith('.places'):
                parse_file(os.path.join(d, f), maps)
    return maps


# ---- resolving against the atlas ----
def auto_place(atlas, name):
    """roof.N, tower.N, deck.N, start.N, phone.N from the atlas, or None."""
    m = re.match(r'^(roof|tower|deck|start|phone)\.(\d+)$', name)
    if not m:
        return None
    kind, n = m.group(1), int(m.group(2))
    lst = {'roof': [r for r in atlas.roofs if r.pad], 'tower': atlas.towers, 'deck': [r for r in atlas.decks if r.pad]}.get(kind)
    if lst is not None:
        if not 1 <= n <= len(lst):
            raise PlaceError('%s: the atlas has %d' % (name, len(lst)))
        r = lst[n - 1]
        return PlaceDef(name, r.pad[0] + 0.5, r.pad[1] + 0.5, ('abs', r.h), DEFAULT_R, F.PK_PAD, 'roof', 'atlas')
    pts = atlas.starts if kind == 'start' else atlas.phones
    if not 1 <= n <= len(pts):
        raise PlaceError('%s: the atlas has %d' % (name, len(pts)))
    q = pts[n - 1]
    return PlaceDef(name, q[0] + 0.5, q[1] + 0.5, ('ground', 0), DEFAULT_R, F.PK_POINT, 'foot' if kind == 'start' else 'foot', 'atlas')


def resolve_h(atlas, pd):
    """The place's height in units."""
    base, off = pd.h
    if base == 'abs':
        h = off
    else:
        cx, cz = pd.cell()
        if not (0 <= cx < 128 and 0 <= cz < 128):
            raise PlaceError('%s: (%.2f, %.2f) is off the map' % (pd.src, pd.x, pd.y))
        if base == 'ground':
            fl = atlas.floors(cx, cz, 'foot') or atlas.floors(cx, cz, 'car')
            if not fl:
                fl = [atlas.lowest_floor(cx, cz)]
            h = fl[0] + off
        elif base == 'top':
            h = atlas.column_top(cx, cz) + off
        else:                                    # deck
            d = atlas.deck.get(cx * 128 + cz)
            if not d:
                raise PlaceError('%s: no deck at (%d, %d)' % (pd.src, cx, cz))
            h = d[1] + off
    return int(h)
