"""The content validators. Every one is a function of a Ctx (the resolved missions, the atlases, the blob) that yields
Issues; an error stops the build, a warning is printed. V1-V14 are stage2.md 3.6; the rest are the checks the engine's
own limits and the first-minute rule ask for. Each has a failing fixture in tests/content/fixtures.py.

  V1  places in open air or on a top, never inside a solid; ring discs clear          V9  per-map counts, chapter split
  V2  reachable in the mode the step needs (flood fill over Payback's walkability)    V10 op arguments and caps
  V3  ring/checkpoint spacing (rings 3 s, others 6 s, 32 cells) and turn limit                        V11 beacons 6 cells apart, 3 from phones
  V4  ceilings leave 400 units over the route                                          V12 start beacons on a floor / in open air
  V5  races follow lanes (90% of samples)                                              V13 the mode flow of a mission
  V6  par: bots, else the number written, else the formula; a limit that can be met   V14 blob size, text size, duplicates
  V7  text limits (titles 18) and glyphs                                                                            V15 beacons 12 cells off Payback's starts
  V8  ids.lock stable                                                                  V16 blast zones hold boxes; maps have what an act needs
"""
import collections
import math

import misfmt as F
import par as PAR

Issue = collections.namedtuple('Issue', 'code sev where msg')
ERR, WARN = 'error', 'warn'

QUOTA = dict(acts=6, contracts=6, chal=(8, 12), medals=6)
CAPS = dict(objs=32, rings=16, checks=16, foes=8, tags=6, group=16)
LIMITS = dict(title=19, hud=18, card=38, card_lines=2, status=7)
BLOB_MAX, TEXT_MAX = 128 * 1024, 32 * 1024
RING_KINDS = (F.PK_RING_X, F.PK_RING_Y, F.PK_RING_H)
AXIS = {F.PK_RING_X: 'x', F.PK_RING_Y: 'y', F.PK_RING_H: 'h'}
MODE_NAME = PAR.MODE_NAME
GROUP_OK = (F.OP_GOTO, F.OP_LAND, F.OP_ENTER, F.OP_STUNT, F.OP_DOCK, F.OP_SPACE, F.OP_PHONE, F.OP_SCORE, F.OP_COLLECT)
PLACE_OPS = {F.OP_GOTO: 1, F.OP_LAND: 1, F.OP_CHASE: 1, F.OP_FOES: 1, F.OP_BOSS: 1, F.OP_DEFEND: 1, F.OP_ESCORT: 2,
             F.OP_SPAWNVEH: 1}                                   # ops with exactly this many places
RUN_OPS = (F.OP_CHECK, F.OP_RINGS, F.OP_RACE, F.OP_DELIVER, F.OP_DESTROY, F.OP_COLLECT, F.OP_CRATES)
NEED_PLACE = set(PLACE_OPS) | set(RUN_OPS)
VEH_TANK = (11, 23)
# P12 (K's probe; not in this base): what pb_spawn_tagged may be asked for on each map. cars everywhere, tanks where
# Payback's own level has them, the helicopter nowhere.
SPAWN_OK = {m: set(range(0, 11)) | {12, 13, 14, 15, 16} for m in range(11)}
for _m in (6, 7):
    SPAWN_OK[_m] |= {11, 23}
BOSS_N = 9
FOE_KINDS = (1, 2, 3, 4, 5)
CREW_N = 7
PROBES = {'wanted': True, 'score': True, 'phone': True}          # P10 / P13 / P2 results; False refuses the op
OP_PROBE = {F.OP_WANTED: 'wanted', F.OP_SCORE: 'score', F.OP_PHONE: 'phone'}
TITLE_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")      # (Payback's banner font: letters, digits and the space are the glyphs seen on screen; no punctuation)
START_FAR = 12                  # cells a challenge or medal beacon keeps from Payback's start points (the first minute): past the roam radius
ACT_FAR = 8                     # (an act's first beacon; also what a map gets whose starts leave too little ground at START_FAR)


def start_far(a):
    """The distance a challenge or medal beacon keeps from the map's Payback start points: START_FAR, or ACT_FAR where the
    starts are so many that less than 400 cells lie that far from all of them (Real Park has 68)."""
    f = getattr(a, '_start_far', None)
    if f is None:
        ok = sum(1 for x in range(4, 124) for y in range(4, 124)
                 if all(math.hypot(x - sx, y - sy) >= START_FAR for sx, sy, _k in a.starts) and idx(x, y) in a.main_car)
        f = a._start_far = START_FAR if ok >= 400 else ACT_FAR
    return f


class Ctx:
    """What the validators look at."""
    def __init__(self, rm, chapters, at, cal, order=None, ids=None, lock=None, blob=None, parsed=None, quota=None, errors=()):
        self.rm, self.chapters, self.at, self.cal = rm, chapters, at, cal
        self.order = order or []
        self.ids, self.lock, self.blob, self.parsed = ids or {}, lock, blob, parsed
        self.quota = dict(QUOTA, **(quota or {}))
        self.errors = list(errors)
        self.speed = cal['speed']

    def atlas(self, m):
        return self.at.get(m.map)


def cells(x):
    return int(x)


def idx(cx, cz):
    return cx * 128 + cz


def places_of(m):
    """(obj or None, role, RPlace): the start and every place an objective uses (not zone corners)."""
    if m.start is not None:
        yield None, 'start', m.start
    for o in m.objs:
        for p in o.places:
            yield o, 'place', p
        if o.drop is not None:
            yield o, 'drop', o.drop


def flow(m):
    """(obj, the mode it runs in: foot / drive / fly or None) for each objective, the mode following ENTER."""
    cur = PAR.start_mode(m)
    for o in m.objs:
        if o.op == F.OP_ENTER and o.mode:
            cur = MODE_NAME[o.mode]
        yield o, (MODE_NAME.get(o.mode) or cur)


def where(m, o=None):
    return (o.src if o is not None else m.src) + ' (' + m.key + ')'


def surface_heights(a, cx, cz):
    """Every height something to stand or rest on has in the cell: its ground, a deck's top."""
    i = idx(cx, cz)
    out = []
    if a.kind[i] != 'building' or a.hi[i]:
        out.append(a.hi[i])
    for d in (a.deck.get(i), a.deck2.get(i)):
        if d:
            out.append(d[1])
    return out


def nearest(a, mode, x, y, h, rad=14):
    """The nearest cell a mode can stand in, as 'x,y h' for a message."""
    src = a.main_foot if mode == 'foot' else a.main_car
    best = None
    for dx in range(-rad, rad + 1):
        for dy in range(-rad, rad + 1):
            cx, cz = int(x) + dx, int(y) + dy
            if 0 <= cx < 128 and 0 <= cz < 128:
                fl = src.get(idx(cx, cz))
                if fl:
                    hh = min(fl, key=lambda f: abs(f - h))
                    d = dx * dx + dy * dy + ((hh - h) / 1024.0) ** 2
                    if best is None or d < best[0]:
                        best = (d, cx + 0.5, cz + 0.5, hh)
    return 'nearest %s: %.1f,%.1f h%d' % (mode, best[1], best[2], best[3]) if best else 'no %s cell within %d' % (mode, rad)


# ---- V1 ----
def on_floor(a, p, tol=400):
    """The place stands on a floor the player can reach (a ramp or an upper road lies inside the deck's own box)."""
    cx, cz = p.cell
    return any(abs(f - p.h) <= tol for md in ('foot', 'car') for f in a.floors(cx, cz, md))


def v1(c):
    for m in c.rm:
        a = c.atlas(m)
        if not a:
            continue
        for o, role, p in places_of(m):
            w = where(m, o)
            x, z, y = p.xyz()
            if not (2 <= p.x < 126 and 2 <= p.y < 126):
                yield Issue('V1', ERR, w, 'place %s (%.1f, %.1f) is off the playable box (2..126)' % (p.name, p.x, p.y))
                continue
            ground_gate = role == 'start' and PAR.start_mode(m) in ('foot', 'drive')      # (a gate on the road: half sunk by design, only its centre is checked)
            if p.kind in RING_KINDS and (o is None or o.op == F.OP_RINGS or role == 'start') and not ground_gate:
                r = (p.r * 1024) if p.r else 1536
                bad = a.clear_disc(x, z, y, r, AXIS[p.kind], 128)
                if bad:
                    yield Issue('V1', ERR, w, 'ring %s at (%.1f, %.1f, h%d): solid at (%.1f, %.1f, h%d) inside its disc'
                                % (p.name, p.x, p.y, p.h, bad[0] / 1024, bad[1] / 1024, bad[2]))
            elif a.blocked(x, z, y + 160, 0) and not on_floor(a, p):
                yield Issue('V1', ERR, w, 'place %s at (%.1f, %.1f, h%d) is inside a solid (a building, a deck)' % (p.name, p.x, p.y, p.h))


# ---- V2 ----
def ground_ok(a, mode, p, tol=400):
    cx, cz = p.cell
    return any(abs(f - p.h) <= tol for f in a.floors(cx, cz, mode))


def v2(c):
    for m in c.rm:
        a = c.atlas(m)
        if not a:
            continue
        for o, eff in flow(m):
            w = where(m, o)
            ps = list(o.places)
            if o.op == F.OP_CRATES and o.drop is not None:
                ps.append(o.drop)
            for p in ps:
                cx, cz = p.cell
                if not (0 <= cx < 128 and 0 <= cz < 128):
                    yield Issue('V2', ERR, w, 'place %s is off the map' % p.name)
                    continue
                if o.op in (F.OP_DESTROY, F.OP_CHASE, F.OP_ESCORT, F.OP_SPAWNVEH):
                    if not (a.main_car.get(idx(cx, cz)) or a.main_foot.get(idx(cx, cz))):
                        yield Issue('V2', ERR, w, 'spawn %s at (%.1f, %.1f) is not on a drivable cell; %s' % (p.name, p.x, p.y, nearest(a, 'drive', p.x, p.y, p.h)))
                    continue
                if o.op in (F.OP_GOTO, F.OP_CHECK, F.OP_RACE, F.OP_DELIVER, F.OP_COLLECT, F.OP_CRATES):
                    if eff in ('foot', 'drive'):
                        md = 'foot' if eff == 'foot' else 'car'
                        if not ground_ok(a, md, p):
                            yield Issue('V2', ERR, w, '%s at (%.1f, %.1f, h%d) is not reachable %s; %s'
                                        % (p.name or 'place', p.x, p.y, p.h, 'on foot' if eff == 'foot' else 'by car', nearest(a, md, p.x, p.y, p.h)))
                    elif eff is None:                                   # any mode: a floor for either, or open air
                        if not (ground_ok(a, 'foot', p) or ground_ok(a, 'car', p) or not a.blocked(*p.xyz()[:2], p.h + 160)):
                            yield Issue('V2', ERR, w, '%s at (%.1f, %.1f, h%d) is not reachable' % (p.name or 'place', p.x, p.y, p.h))
                elif o.op == F.OP_LAND:
                    sh = surface_heights(a, cx, cz)
                    if a.water[idx(cx, cz)]:
                        yield Issue('V2', ERR, w, 'land %s is on water' % p.name)
                    elif not any(abs(p.h - s) <= 160 for s in sh):
                        yield Issue('V2', ERR, w, 'land %s at h%d: the surface there is %s' % (p.name, p.h, sh))
                    else:
                        for dx in (-1, 0, 1):
                            for dz in (-1, 0, 1):
                                s2 = surface_heights(a, cx + dx, cz + dz) if 0 <= cx + dx < 128 and 0 <= cz + dz < 128 else []
                                if a.water[idx(cx + dx, cz + dz)] if s2 else False:
                                    yield Issue('V2', ERR, w, 'land %s: water within a cell' % p.name)
                                    break
                                if not any(abs(p.h - s) <= 80 for s in s2):
                                    yield Issue('V2', ERR, w, 'land %s at h%d: not a flat pad (cell %d,%d has %s)' % (p.name, p.h, cx + dx, cz + dz, s2))
                                    break
                            else:
                                continue
                            break
        # a vehicle drive requires cars; checked per op above


# ---- V3 ----
SPACING_S = 6.0                                              # (seconds at the mode's top speed between checkpoints: a street checkpoint is read off the arrow)
RING_S = 3.0                                                 # (a ring is small: the next must be on screen soon)
DRAW_CAP = 32                                                # (cells: the beacons draw to 40, and a checkpoint should be well inside that)
def seg(a, b):
    dx, dz, dy = (b.x - a.x) * 1024, (b.y - a.y) * 1024, b.h - a.h
    return dx, dy, dz


def v3(c):
    for m in c.rm:
        last = m.start
        for o, eff in flow(m):
            w = where(m, o)
            if o.op in (F.OP_RINGS, F.OP_CHECK, F.OP_RACE) and o.places:
                mode = eff or 'drive'
                sp = c.speed.get(mode, 9.0) * 1024.0
                lim = RING_S if o.op == F.OP_RINGS else SPACING_S
                cap = min(lim * sp, DRAW_CAP * 1024.0)
                pts = ([last] if last is not None and o.op != F.OP_RACE else []) + list(o.places)
                prev_d = None
                for i in range(1, len(pts)):
                    dx, dy, dz = seg(pts[i - 1], pts[i])
                    d = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if d > cap + 1e-6 and not (o.op == F.OP_RINGS and i == 1 and pts[0] is last):
                        yield Issue('V3', ERR, w, '%s %d is %.1f s from the one before at top speed (%g s or %d cells at most): %.1f cells'
                                    % (F.OPS[o.op].lower(), i, d / sp, lim, DRAW_CAP, d / 1024))
                    if o.op == F.OP_RINGS and d < 1000:
                        yield Issue('V3', ERR, w, 'rings %d and %d are %d units apart (1000 at least)' % (i - 1, i, d))
                    if o.op == F.OP_RINGS and prev_d is not None and d > 0 and prev_d[3] > 0:
                        dot = (prev_d[0] * dx + prev_d[1] * dy + prev_d[2] * dz) / (prev_d[3] * d)
                        ang = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
                        if ang > 100.0:
                            yield Issue('V3', ERR, w, 'ring %d turns %d degrees (100 at most)' % (i, ang))
                    prev_d = (dx, dy, dz, d)
            if o.places:
                last = o.places[-1]


# ---- V4 ----
def in_zone(z, p):
    x0, x1 = sorted((z[0].x, z[1].x))
    y0, y1 = sorted((z[0].y, z[1].y))
    return x0 <= p.x <= x1 and y0 <= p.y <= y1


def v4(c):
    for m in c.rm:
        ceil = None
        for o in m.objs:
            w = where(m, o)
            if o.op == F.OP_CEIL:
                if o.zone is None:
                    yield Issue('V4', ERR, w, 'ceil has no zone')
                    continue
                ceil = (o.a, o.zone)
                if not (m.flags & F.FF_CEIL):
                    yield Issue('V4', WARN, w, 'ceil without fail=ceil')
                if not any(in_zone(o.zone, p) for q in m.objs for p in q.places):
                    yield Issue('V4', ERR, w, 'no place of the route lies in the ceiling zone')
            elif ceil is not None:
                for p in o.places:
                    if in_zone(ceil[1], p) and p.h > ceil[0] - 400 and o.op != F.OP_LAND:
                        yield Issue('V4', ERR, w, '%s at h%d is not 400 under the ceiling %d' % (p.name or 'place', p.h, ceil[0]))
        if m.flags & F.FF_CEIL and not any(o.op == F.OP_CEIL for o in m.objs):
            yield Issue('V4', ERR, where(m), 'fail=ceil without a ceil step')


# ---- V5 ----
def lane_fraction(a, pts, blocked=None):
    """The share of 0.5 cell samples along the polyline that lie on lane cells (or other paving a car reaches). blocked, a
    list, gets the first samples that no car reaches (a wall, water, a drop)."""
    n = ok = 0
    for i in range(1, len(pts)):
        x0, y0, x1, y1 = pts[i - 1].x, pts[i - 1].y, pts[i].x, pts[i].y
        k = max(1, int(math.hypot(x1 - x0, y1 - y0) * 2))
        for j in range(k):
            t = j / k
            cx, cz = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
            if not (0 <= cx < 128 and 0 <= cz < 128):
                n += 1
                continue
            i2 = idx(cx, cz)
            n += 1
            ok += (a.lane[i2] & 15) != 0 or (i2 in a.main_car and a.kind[i2] != 'ground')     # (a lane, a road, a kerb, a ramp, a bridge deck: not a field)
            if blocked is not None and i2 not in a.main_car:
                blocked.append((cx, cz))
    return ok / n if n else 1.0


def v5(c):
    for m in c.rm:
        a = c.atlas(m)
        if not a:
            continue
        for o in m.objs:
            if o.op == F.OP_RACE and len(o.places) > 1 and not (m.flags & F.MS_FLY):
                pts = list(o.places) + ([o.places[0]] if o.b > 1 or o.b == 0 and False else [])
                bl = []
                fr = lane_fraction(a, pts, bl)
                if fr < 0.9:
                    yield Issue('V5', ERR, where(m, o), 'the race leaves the lanes: %d%% of the course is on a lane cell (90%% needed)' % round(fr * 100))
                if len(bl) > 2:
                    yield Issue('V5', ERR, where(m, o), 'the course crosses cells no car reaches, first at %d,%d (%d samples)' % (bl[0][0], bl[0][1], len(bl)))


# ---- V6 ----
def v6(c):
    for m in c.rm:
        if m.par is None:
            yield Issue('V6', ERR, where(m), 'no par')
            continue
        if m.flags & F.FF_TIME:
            if not m.par:
                yield Issue('V6', ERR, where(m), 'fail=time needs a par (the limit)')
                continue
            top = PAR.top_time(m, c.speed)
            if m.par < PAR.limit_floor(top):                                  # (the bots' too: they carry the vehicle, a person has to steer)
                yield Issue('V6', ERR, where(m), 'the limit %d s is too tight (%s): flying the route at top speed takes %.0f s, so %d at least'
                            % (m.par, m.par_from, top, PAR.limit_floor(top)))
            if PAR.start_mode(m) == 'foot' and any(o.op == F.OP_COLLECT for o in m.objs) and m.par > PAR.FOOT_PAR_MAX:
                yield Issue('V6', ERR, where(m), 'a hunt on foot with a limit of %d s (%d at most): gather the pickups closer' % (m.par, PAR.FOOT_PAR_MAX))
            est = PAR.estimate(m, c.speed)
            if m.par > 4 * est + 60:
                yield Issue('V6', WARN, where(m), 'the limit %d s is far over the estimate %.0f s' % (m.par, est))
        if not 0 <= m.par <= 65535:
            yield Issue('V6', ERR, where(m), 'par %s does not fit' % m.par)


# ---- V7 ----
def text_issues(s, limit, what, w, glyphs=None):
    lines = s.split('\n')
    if limit == LIMITS['card']:
        if len(lines) > LIMITS['card_lines']:
            yield Issue('V7', ERR, w, '%s has %d lines (2 at most)' % (what, len(lines)))
    elif len(lines) > 1:
        yield Issue('V7', ERR, w, '%s has a line break' % what)
    for ln in lines:
        if len(ln) > limit:
            yield Issue('V7', ERR, w, '%s "%s" is %d letters (%d at most)' % (what, ln, len(ln), limit))
    odd = sorted({ch for ch in s if ch != '\n' and not (32 <= ord(ch.upper()) <= 95 if glyphs is None else ch in glyphs)})
    if odd:
        yield Issue('V7', ERR, w, '%s has letters the font lacks: %s' % (what, ' '.join(repr(ch) for ch in odd)))


def v7(c):
    for m in c.rm:
        yield from text_issues(m.title, LIMITS['hud'], 'title', where(m), TITLE_CHARS)       # (the banner takes 19; the armed HUD line, which shows the title, 18)
        if m.title != m.title.upper():
            yield Issue('V7', ERR, where(m), 'title "%s" is not capitals' % m.title)
        for o in m.objs:
            w = where(m, o)
            if o.op in (F.OP_BRIEF, F.OP_TALK, F.OP_CARD):
                yield from text_issues(o.text, LIMITS['card'], 'card', w)
                if o.op == F.OP_BRIEF and o.banner:
                    yield from text_issues(o.banner, LIMITS['title'], 'banner', w, TITLE_CHARS)
            elif o.text:
                yield from text_issues(o.text, LIMITS['hud'], 'line', w)
    for ch in c.chapters:
        yield from text_issues(ch.title, LIMITS['title'], 'chapter title', ch.src, TITLE_CHARS)
        yield from text_issues(ch.brief, LIMITS['card'], 'chapter brief', ch.src)
    # the longest status the engine builds: "NE 999" / "HP 99" / "16/16" / "10:00" (hudline.c): at most 7 letters
    for s in ('NE 999', 'SW 999', 'HP 999', '16/16', '99:59', '32/32'):
        if len(s) > LIMITS['status']:
            yield Issue('V7', ERR, 'hudline', 'status %s is longer than 7' % s)


# ---- V8 ----
def v8(c):
    lock = c.lock
    if lock is None:
        return
    seen = {}
    for k, i in lock.get('ids', {}).items():
        if i in seen:
            yield Issue('V8', ERR, 'ids.lock', 'id %d is used by %s and %s' % (i, seen[i], k))
        seen[i] = k
        if i >= lock.get('next', 0):
            yield Issue('V8', ERR, 'ids.lock', 'id %d of %s is not below next (%d)' % (i, k, lock.get('next', 0)))
    for i in lock.get('retired', []):
        if i in seen:
            yield Issue('V8', ERR, 'ids.lock', 'retired id %d is in use by %s' % (i, seen[i]))
    keys = set()
    for m in c.rm:
        if m.key in keys:
            yield Issue('V8', ERR, where(m), 'two missions are called %s' % m.key)
        keys.add(m.key)
        if m.key not in lock.get('ids', {}):
            yield Issue('V8', ERR, where(m), '%s has no id in ids.lock (run: sfc ids)' % m.key)
        elif m.id != lock['ids'][m.key]:
            yield Issue('V8', ERR, where(m), '%s has id %s, the lock says %d' % (m.key, m.id, lock['ids'][m.key]))
    for k in lock.get('ids', {}):
        if k not in keys:
            yield Issue('V8', WARN, 'ids.lock', '%s is in the lock but not in the content (retired: its id stays taken)' % k)
    pinned = lock.get('auto', {})
    for key, want in pinned.items():
        lv, name = key.split(':', 1)
        a = c.at.get(int(lv))
        if not a:
            continue
        got = c.auto_cells.get(key) if hasattr(c, 'auto_cells') else None
        if got is not None and list(got) != list(want):
            yield Issue('V8', ERR, 'ids.lock', 'auto place %s moved: pinned %s, the atlas now says %s' % (key, want, got))
    if c.parsed:
        ids = [d['id'] for d in c.parsed['missions']]
        if len(set(ids)) != len(ids):
            yield Issue('V8', ERR, 'blob', 'duplicate mission ids in the blob')


# ---- V9 ----
def v9(c):
    q = c.quota
    by = collections.defaultdict(lambda: collections.Counter())
    for m in c.rm:
        by[m.map][m.kind] += 1
    chmaps = {ch.map: ch for ch in c.chapters}
    for lv, cnt in sorted(by.items()):
        if lv not in chmaps:
            yield Issue('V9', ERR, 'map %d' % lv, 'missions on a map with no chapter in campaign.sfc')
            continue
        w = 'map %d' % lv
        if cnt[F.MK_ACT] != q['acts']:
            yield Issue('V9', ERR, w, '%d acts (%d wanted)' % (cnt[F.MK_ACT], q['acts']))
        if cnt[F.MK_CONTRACT] != q['contracts']:
            yield Issue('V9', ERR, w, '%d contracts (%d wanted)' % (cnt[F.MK_CONTRACT], q['contracts']))
        lo, hi = q['chal']
        if not lo <= cnt[F.MK_CHAL] <= hi:
            yield Issue('V9', ERR, w, '%d challenges (%d to %d wanted)' % (cnt[F.MK_CHAL], lo, hi))
        if cnt[F.MK_MEDAL] != q['medals']:
            yield Issue('V9', ERR, w, '%d medals (%d wanted)' % (cnt[F.MK_MEDAL], q['medals']))
        acts = sorted(m.act for m in c.rm if m.map == lv and m.kind == F.MK_ACT)
        if acts != list(range(1, len(acts) + 1)):
            yield Issue('V9', ERR, w, 'acts are numbered %s (1..n wanted)' % acts)
    for ch in c.chapters:
        story = bool(ch.flags & F.CH_STORY)
        want = 3 if story else 6
        if ch.flags & F.CH_RESERVED:
            continue
        if ch.split != want:
            yield Issue('V9', ERR, ch.src, 'chapter split %d, but a %s chapter has %d acts in its first level' % (ch.split, 'story' if story else 'rampage', want))
    for ch in c.chapters:                                      # (the station hangs over the cell the drop starts from)
        if ch.flags & F.CH_DROP:
            a1 = next((m for m in c.rm if m.map == ch.map and m.kind == F.MK_ACT and m.act == 1 and m.start is not None), None)
            if a1 is not None and (int(round(a1.start.x * 2)), int(round(a1.start.y * 2))) != tuple(ch.hover):
                yield Issue('V9', ERR, ch.src, 'chapter map %d: hover cell %s but the drop starts at %.1f,%.1f' % (ch.map, tuple(v / 2 for v in ch.hover), a1.start.x, a1.start.y))
    if c.parsed:                                               # (the engine's roam scan looks at the map's chapter range only)
        chs = c.parsed['chapters']
        for i, mi in enumerate(c.parsed['missions']):
            home = [k for k, ch in enumerate(chs) if ch['mis0'] <= i < ch['mis0'] + ch['nmis']]
            if len(home) != 1 or chs[home[0]]['map'] != mi['map']:
                yield Issue('V9', ERR, 'blob', 'mission %d (map %d) is not in its map\'s chapter range' % (i, mi['map']))
                break
    cs = [ch.map for ch in c.chapters]
    if len(set(cs)) != len(cs):
        yield Issue('V9', ERR, 'campaign.sfc', 'a map has two chapters')
    if c.chapters and sum(1 for ch in c.chapters if ch.flags & F.CH_FINAL) != 1:
        yield Issue('V9', ERR, 'campaign.sfc', 'exactly one chapter is the final one')


# ---- V10 ----
def v10(c):
    for m in c.rm:
        if len(m.objs) > CAPS['objs']:
            yield Issue('V10', ERR, where(m), '%d objectives (%d at most)' % (len(m.objs), CAPS['objs']))
        if not m.objs:
            yield Issue('V10', ERR, where(m), 'no objectives')
            continue
        if m.objs[-1].op != F.OP_FINISH and m.kind == F.MK_ACT:
            yield Issue('V10', WARN, where(m), 'an act should end with finish')
        gdepth, gn, live = 0, 0, 0
        timer = False
        bosses = 0
        for k, o in enumerate(m.objs):
            w = where(m, o)
            n = len(o.places)
            if o.op in PLACE_OPS and n != PLACE_OPS[o.op]:
                yield Issue('V10', ERR, w, '%s takes %d place(s), not %d' % (F.OPS[o.op].lower(), PLACE_OPS[o.op], n))
            if o.op in RUN_OPS and n == 0:
                yield Issue('V10', ERR, w, '%s needs places' % F.OPS[o.op].lower())
            if o.op in (F.OP_RINGS, F.OP_CHECK, F.OP_RACE) and n > CAPS['rings']:
                yield Issue('V10', ERR, w, '%d places (%d at most)' % (n, CAPS['rings']))
            if o.op == F.OP_RACE and n < 2:
                yield Issue('V10', ERR, w, 'a race needs 2 checkpoints at least')
            if o.op in OP_PROBE and not PROBES.get(OP_PROBE[o.op], True):
                yield Issue('V10', ERR, w, '%s is refused: its probe failed' % F.OPS[o.op].lower())
            if o.op == F.OP_DESTROY:
                if n > CAPS['tags']:
                    yield Issue('V10', ERR, w, 'destroy %d: %d tagged spawns alive at most' % (n, CAPS['tags']))
                if o.a not in SPAWN_OK.get(m.map, set()) and o.a != 0:
                    yield Issue('V10', ERR, w, 'type %d cannot be spawned on map %d' % (o.a, m.map))
            if o.op in (F.OP_CHASE, F.OP_ESCORT, F.OP_SPAWNVEH):
                if o.a != 0 and o.a not in SPAWN_OK.get(m.map, set()):
                    yield Issue('V10', ERR, w, 'type %d cannot be spawned on map %d' % (o.a, m.map))
            if o.op == F.OP_SPAWNVEH:
                later = [q for q in m.objs[k + 1:] if q.op == F.OP_DESTROY and len(q.places) >= 2]
                if later:
                    yield Issue('V10', ERR, w, 'spawnveh uses tag slot 1, a later destroy with 2 or more takes it')
            if o.op == F.OP_FOES:
                if not 1 <= o.n <= CAPS['foes']:
                    yield Issue('V10', ERR, w, 'foes %s (1..%d)' % (o.n, CAPS['foes']))
                if o.a not in FOE_KINDS:
                    yield Issue('V10', ERR, w, 'foe kind %d' % o.a)
                if o.b < 0:
                    yield Issue('V10', ERR, w, 'foe hp %d' % o.b)
            if o.op == F.OP_BOSS:
                bosses += 1
                if not 0 <= o.a < BOSS_N:
                    yield Issue('V10', ERR, w, 'boss %d (0..%d)' % (o.a, BOSS_N - 1))
            if o.op == F.OP_DEFEND and (o.a <= 0 or o.b <= 0):
                yield Issue('V10', ERR, w, 'defend needs hp and seconds')
            if o.op == F.OP_STUNT and o.a <= 0:
                yield Issue('V10', ERR, w, 'stunt needs points')
            if o.op == F.OP_JUMP and o.a <= 0:
                yield Issue('V10', ERR, w, 'jump needs a distance')
            if o.op == F.OP_TALK and not 1 <= o.a <= CREW_N:
                yield Issue('V10', ERR, w, 'talk: crew %d' % o.a)
            if o.op == F.OP_TIMER:
                if timer:
                    yield Issue('V10', ERR, w, 'timers do not nest')
                timer = True
                if o.b <= 0:
                    yield Issue('V10', ERR, w, 'timer needs seconds')
            if o.op == F.OP_ENDTIMER:
                if not timer:
                    yield Issue('V10', ERR, w, 'endtimer without a timer')
                timer = False
            if o.op == F.OP_GROUP:
                if gdepth:
                    yield Issue('V10', ERR, w, 'groups do not nest')
                gdepth, gn = 1, 0
            elif o.op == F.OP_ENDGROUP:
                if not gdepth:
                    yield Issue('V10', ERR, w, 'endgroup without a group')
                gdepth = 0
            elif gdepth:
                gn += 1
                if o.op not in GROUP_OK:
                    yield Issue('V10', ERR, w, '%s cannot be in a group (only ops that finish at once: %s)'
                                % (F.OPS[o.op].lower(), ' '.join(F.OPS[g].lower() for g in GROUP_OK)))
                if o.op == F.OP_COLLECT and len(o.places) != 1:
                    yield Issue('V10', ERR, w, 'a collect in a group takes one pickup')
                if gn > CAPS['group']:
                    yield Issue('V10', ERR, w, 'more than %d in a group' % CAPS['group'])
            if o.op == F.OP_RINGS and o.mode not in (0, F.MODE_FLY):
                yield Issue('V10', ERR, w, 'rings are flown')
            if not -32768 <= o.a <= 32767 or not -32768 <= o.b <= 32767:
                yield Issue('V10', ERR, w, 'argument out of 16 bits')
            if o.n is not None and not 0 <= o.n <= 255:
                yield Issue('V10', ERR, w, 'count %s' % o.n)
        if gdepth:
            yield Issue('V10', ERR, where(m), 'a group is not closed')
        if timer:
            yield Issue('V10', WARN, where(m), 'a timer is not closed (it runs to the end)')
        if bosses > 1:
            yield Issue('V10', ERR, where(m), '%d bosses (1 at a time)' % bosses)
        if m.flags & F.FF_ESCORT and not any(o.op == F.OP_ESCORT for o in m.objs):
            yield Issue('V10', ERR, where(m), 'fail=escort without an escort step')
        if m.flags & F.FF_ZONE and not any(o.op == F.OP_ZONE for o in m.objs):
            yield Issue('V10', ERR, where(m), 'fail=zone without a zone step')
        if m.flags & F.FF_VEHLOST and not any(o.op == F.OP_DELIVER and o.mode for o in m.objs):
            yield Issue('V10', WARN, where(m), 'fail=vehlost only counts in a deliver with a mode')
        if m.kind == F.MK_ACT and not 1 <= m.act <= 6:
            yield Issue('V10', ERR, where(m), 'act %d (1..6)' % m.act)
        if not 0 <= m.tier <= 3:
            yield Issue('V10', ERR, where(m), 'tier %d' % m.tier)
        if m.pay > 65535 or m.score > 65535:
            yield Issue('V10', ERR, where(m), 'pay or score over 16 bits')


# ---- V11 ----
def beacon_list(c):
    out = []
    for m in c.rm:
        if m.start is not None:
            out.append((m, m.start))
    return out


def v11(c):
    bl = beacon_list(c)
    for i in range(len(bl)):
        for j in range(i + 1, len(bl)):
            (m1, p1), (m2, p2) = bl[i], bl[j]
            if m1.map == m2.map and math.hypot(p1.x - p2.x, p1.y - p2.y) < 6.0:
                # the same course's own beacon for itself is not a pair
                yield Issue('V11', ERR, where(m1), 'beacon %s is %.1f cells from %s (6 at least)' % (m1.key, math.hypot(p1.x - p2.x, p1.y - p2.y), m2.key))
    for m, p in bl:
        a = c.atlas(m)
        if not a:
            continue
        for (px, py) in a.phones:
            if math.hypot(p.x - (px + 0.5), p.y - (py + 0.5)) < 3.0:
                yield Issue('V11', ERR, where(m), 'beacon is %.1f cells from the phone at %d,%d (3 at least)' % (math.hypot(p.x - px - 0.5, p.y - py - 0.5), px, py))


# ---- V12 ----
def v12(c):
    for m in c.rm:
        a = c.atlas(m)
        if not a or m.start is None:
            continue
        p = m.start
        w = where(m)
        mode = PAR.start_mode(m)
        if m.flags & F.MS_SPACE:
            if p.h < 12000:
                yield Issue('V12', ERR, w, 'a space start is at h%d (12000 and up)' % p.h)
            continue
        if mode == 'foot' and not ground_ok(a, 'foot', p, 768):
            yield Issue('V12', ERR, w, 'the beacon (%.1f, %.1f, h%d) is not on a floor a man reaches; %s' % (p.x, p.y, p.h, nearest(a, 'foot', p.x, p.y, p.h)))
        elif mode == 'drive' and not ground_ok(a, 'car', p, 768):
            yield Issue('V12', ERR, w, 'the beacon (%.1f, %.1f, h%d) is not on a floor a car reaches; %s' % (p.x, p.y, p.h, nearest(a, 'car', p.x, p.y, p.h)))
        elif mode == 'fly':
            cx, cz = p.cell
            top = a.column_top(cx, cz)
            if p.h - top < 1000:
                yield Issue('V12', ERR, w, 'a fly start (%.1f, %.1f, h%d) is %d over the top below it (1000 at least)' % (p.x, p.y, p.h, p.h - top))
            if p.kind not in RING_KINDS:
                yield Issue('V12', WARN, w, 'a fly start should be a ring (flying through it starts the mission)')
        elif mode is None and not (ground_ok(a, 'foot', p, 768) or ground_ok(a, 'car', p, 768)):
            yield Issue('V12', ERR, w, 'the beacon (%.1f, %.1f, h%d) is on no floor; %s' % (p.x, p.y, p.h, nearest(a, 'foot', p.x, p.y, p.h)))
        if p.kind in RING_KINDS:                                    # (a ring starts by crossing its plane: it faces the way the route runs)
            first = next((o for o in m.objs if o.places), None)
            if first is not None and first.op in (F.OP_RINGS, F.OP_RACE, F.OP_CHECK):
                import emit
                want = emit._axis(None, p, first.places[0])
                if want != p.kind:
                    yield Issue('V12', ERR, w, 'the start ring faces %s but the route runs the %s way (use %s)'
                                % (AXIS[p.kind], AXIS[want], {F.PK_RING_X: 'ring_x', F.PK_RING_Y: 'ring_y', F.PK_RING_H: 'ring_h'}[want]))


# ---- V13 ----
def v13(c):
    for m in c.rm:
        cur = PAR.start_mode(m)
        for o in m.objs:
            w = where(m, o)
            want = MODE_NAME.get(o.mode)
            if o.op == F.OP_ENTER:
                if not o.mode:
                    yield Issue('V13', ERR, w, 'enter needs a mode')
                else:
                    if cur == 'foot' and want == 'fly' and False:
                        pass
                    cur = want
                continue
            if want and cur and want != cur and o.op in (F.OP_GOTO, F.OP_CHECK, F.OP_RACE, F.OP_DELIVER, F.OP_COLLECT, F.OP_CRATES, F.OP_LAND, F.OP_RINGS):
                if not (o.op == F.OP_LAND and want == 'foot' and cur == 'fly'):
                    yield Issue('V13', ERR, w, '%s runs as %s but the mission is %s here (an enter is missing)' % (F.OPS[o.op].lower(), want, cur))
            if want and cur is None:
                cur = want
            if o.op == F.OP_RINGS and cur not in ('fly', None):
                yield Issue('V13', ERR, w, 'rings are flown, but the mission is %s here' % cur)
            if o.op == F.OP_RINGS and cur is None:
                cur = 'fly'
            if o.op == F.OP_LAND and cur == 'foot':
                pass
            if o.op == F.OP_LAND and want == 'foot':
                cur = 'foot'
            if o.op in (F.OP_FOES, F.OP_BOSS, F.OP_DEFEND) and cur not in ('fly', None):
                yield Issue('V13', WARN, w, '%s while %s (a fight is flown)' % (F.OPS[o.op].lower(), cur))
        if (m.flags & F.MS_SPACE) and PAR.start_mode(m) != 'fly':
            yield Issue('V13', ERR, where(m), 'a space start flies (mode=space,fly)')


# ---- V14 ----
def v14(c):
    if c.blob is not None:
        if len(c.blob) > BLOB_MAX:
            yield Issue('V14', ERR, 'blob', 'the blob is %d bytes (%d at most)' % (len(c.blob), BLOB_MAX))
    if c.parsed:
        tx = c.parsed['texts']
        size = sum(len(t) + 3 for t in tx)
        if size > TEXT_MAX:
            yield Issue('V14', ERR, 'blob', 'the text is %d bytes (%d at most)' % (size, TEXT_MAX))
        seen = collections.Counter(tx)
        for t, n in seen.items():
            if n > 1 and len(t) > 8:
                yield Issue('V14', ERR, 'blob', 'the string "%s" is stored %d times' % (t[:30], n))
        h = c.parsed['head']
        if h['nplace'] > 32767:
            yield Issue('V14', ERR, 'blob', 'more than 32767 places (a crates drop is a signed index)')
        for d in c.parsed['places']:
            if not (2 * 8 <= d['x8'] <= 126 * 8 and 2 * 8 <= d['y8'] <= 126 * 8):
                yield Issue('V14', ERR, 'blob', 'a place outside the map: %s' % d)


# ---- V15 ----
def v15(c):
    for m in c.rm:
        a = c.atlas(m)
        if not a or m.start is None:
            continue
        far = ACT_FAR if m.kind == F.MK_ACT else start_far(a)
        if m.kind == F.MK_ACT and m.act != 1:
            continue
        for (sx, sy, k) in a.starts:
            d = math.hypot(m.start.x - sx - 0.5, m.start.y - sy - 0.5)
            if d < far:
                yield Issue('V15', ERR, where(m), 'beacon %.1f cells from Payback start (%d,%d): the first minute of the map would change (%d at least)'
                            % (d, sx, sy, far))


# ---- V16 ----
def v16(c):
    for m in c.rm:
        a = c.atlas(m)
        if not a:
            continue
        for o in m.objs:
            if o.op == F.OP_BLAST and o.zone:
                z = o.zone
                have = sum(1 for (cx, cz) in a.crates if in_zone(z, type('P', (), dict(x=cx + .5, y=cz + .5))))
                if have < (o.n or 0):
                    yield Issue('V16', ERR, where(m, o), 'blast %d boxes, but the zone holds %d' % (o.n or 0, have))
            if o.op in (F.OP_CRATES,) and False:
                pass
            if o.op == F.OP_PHONE and not a.phones:
                yield Issue('V16', ERR, where(m, o), 'the map has no phones')
        if m.flags & F.MF_PHONE and not a.phones:
            yield Issue('V16', ERR, where(m), 'a phone mission on a map without phones')


ALL = [v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, v11, v12, v13, v14, v15, v16]


def run(c, only=None):
    out = list(c.errors)
    for fn in ALL:
        if only and fn.__name__.upper() not in only:
            continue
        out.extend(fn(c))
    return out


def errors(issues):
    return [i for i in issues if i.sev == ERR]


def fmt(i):
    return '%s %s: %s: %s' % (i.code, 'error' if i.sev == ERR else 'warning', i.where, i.msg)
