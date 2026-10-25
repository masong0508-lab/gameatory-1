"""The mission language (.sfm) and the campaign file (campaign.sfc).

    act kz.trench "TRENCH RUN" map=3 act=2 giver=rook par=70 pay=400 score=50 fail=time,death,ceil start=canyon.gate mode=fly
      brief "STAY UNDER THE SKYBRIDGES"
      ceil 3500 zone=canyon.trench
      rings canyon.r1..canyon.r8 strict "FLY THE TRENCH"
      land fox_field.pad "SET DOWN ON PAD"
      finish

A header is `act | contract | chal | medal NAME "TITLE" key=value ...`; each indented line after it is one objective
(one 12-byte record). Places are names (a range name1..name2 takes the numbered names between), or literals (x,y,h,r).
Quoted text: the first is the HUD line (18 letters), on `brief` a banner (19) and then the card (2 x 38, \\n between
the lines), on `talk` and `card` the card. Nothing here prints on Payback's ticker.

campaign.sfc: the crew (giver ids), the chapters (map, flags, split, station hover cell, title, brief) in order, the
unlock and story-flag numbers the ops use.
"""
import os
import re

import misfmt as F
import places as P

MODES = {'any': 0, 'foot': 1, 'drive': 2, 'car': 2, 'fly': 3}
FAIL = {'time': F.FF_TIME, 'death': F.FF_DEATH, 'vehlost': F.FF_VEHLOST, 'zone': F.FF_ZONE, 'ceil': F.FF_CEIL,
        'ceiling': F.FF_CEIL, 'escort': F.FF_ESCORT}
START = {'foot': F.MS_FOOT, 'drive': F.MS_DRIVE, 'car': F.MS_DRIVE, 'fly': F.MS_FLY, 'space': F.MS_SPACE,
         'after': F.MS_AFTER, 'repeat': F.MS_REPEAT}
KINDS = {'act': F.MK_ACT, 'contract': F.MK_CONTRACT, 'chal': F.MK_CHAL, 'medal': F.MK_MEDAL}
FOES = {'raider': 1, 'carrier': 2, 'turret': 3, 'ace': 4, 'courier': 5}        # K's F_* (sgint.h)
CREW = {'none': 0, 'rook': 1, 'pip': 2, 'nova': 3, 'dusty': 4, 'quill': 5, 'juno': 6, 'kestrel': 7}


class SfmError(Exception):
    pass


class Obj:
    def __init__(self, op, src):
        self.op, self.src = op, src
        self.mode = 0
        self.places = []            # refs: a name (str) or a PlaceDef (a literal)
        self.n = None               # explicit count (None: the places)
        self.a = 0
        self.b = 0
        self.flags = 0
        self.text = ''              # the HUD line, or a card
        self.banner = ''            # brief: the banner
        self.zone = None            # ref of a zone (stunt, ceil, zone, blast)
        self.drop = None            # crates: the drop place ref

    def __repr__(self):
        return 'Obj(%s %s n=%s a=%s b=%s %r)' % (F.OPS[self.op], self.places, self.n, self.a, self.b, self.text)


class Mission:
    def __init__(self, kind, name, title, src):
        self.kind, self.name, self.title, self.src = kind, name, title, src
        self.map = None
        self.act = 0
        self.tier = 0
        self.giver = 0
        self.par = 0                # 0 / 'auto': the compiler's (calibration, else the distance formula)
        self.pay = 0
        self.score = 0
        self.flags = 0
        self.start = None           # ref
        self.start_kind = None
        self.brief = ''
        self.objs = []
        self.gen = False            # from a generator (content/missions/gen)

    def key(self):
        return 'm%d.%s' % (self.map, self.name)


def unquote(tok):
    s = tok[1:-1].replace('\\n', '\n')
    return s


def _kv(tokens_):
    pos, kv, flags = [], {}, []
    for t in tokens_:
        if t.startswith('"'):
            pos.append(t)
        elif '=' in t and not t.startswith('('):
            k, v = t.split('=', 1)
            kv[k] = v
        else:
            pos.append(t)
    return pos, kv


def expand_range(tok, src):
    """canyon.r1..canyon.r8 -> the names from canyon.r1 to canyon.r8 (a trailing number counts up)."""
    a, b = tok.split('..', 1)
    ma, mb = re.match(r'^(.*?)(\d+)$', a), re.match(r'^(.*?)(\d+)$', b)
    if not ma or not mb or ma.group(1) != mb.group(1):
        raise SfmError('%s: bad range %s' % (src, tok))
    lo, hi = int(ma.group(2)), int(mb.group(2))
    w = len(ma.group(2))
    step = 1 if hi >= lo else -1
    return ['%s%0*d' % (ma.group(1), w if ma.group(2).startswith('0') else 0, i) for i in range(lo, hi + step, step)]


def place_refs(toks, src):
    out = []
    for t in toks:
        if t.startswith('('):
            out.append(P.parse_literal(t, src))
        elif '..' in t and not t.startswith('"') and not re.match(r'^[\d.]+$', t):
            out += expand_range(t, src)
        else:
            out.append(t)
    return out


CONSTS = {}                 # campaign.sfc's const NAME = N (loaded before the missions): a number in an op may be a name


def num(v, src, what):
    if v in CONSTS:
        return CONSTS[v]
    try:
        return int(float(v))
    except ValueError:
        raise SfmError('%s: %s is not a number: %r' % (src, what, v))


def parse_obj(toks, src):
    op = toks[0]
    if op not in F.ENUMS['OP'] and op.upper() not in F.ENUMS['OP']:
        raise SfmError('%s: unknown objective %r' % (src, op))
    opn = op.upper()
    o = Obj(F.ENUMS['OP'][opn], src)
    rest = toks[1:]
    strs = [unquote(t) for t in rest if t.startswith('"')]
    rest = [t for t in rest if not t.startswith('"')]
    pos, kv = _kv(rest)
    flags = [p for p in pos if p in ('strict', 'ckpt', 'hidden', 'ordered')]
    pos = [p for p in pos if p not in flags]
    if 'strict' in flags:
        o.flags |= F.MO_STRICT
    if 'ckpt' in flags:
        o.flags |= F.MO_CKPT
    if 'hidden' in flags:
        o.flags |= F.MO_HIDDEN
    if 'ordered' in flags:
        o.flags |= F.MO_ORDER
    if 'mode' in kv:
        if kv['mode'] not in MODES:
            raise SfmError('%s: mode %s' % (src, kv['mode']))
        o.mode = MODES[kv.pop('mode')]
    used = set()

    def take(k, default=0):
        if k in kv:
            used.add(k)
            return kv[k]
        return default
    P_OPS = ('goto', 'check', 'rings', 'land', 'deliver', 'race', 'chase', 'destroy', 'blast', 'foes', 'boss', 'escort', 'defend',
             'collect', 'crates', 'spawnveh')
    if op in P_OPS:
        o.places = place_refs(pos, src)
        pos = []
    if opn in ('BRIEF',):
        if len(strs) == 2:
            o.banner, o.text = strs
        elif len(strs) == 1:
            o.text = strs[0]
        strs = []
    elif opn in ('TALK',):
        if len(pos) != 2:
            raise SfmError('%s: talk CREW NODE "card"' % src)
        o.a = CREW[pos[0]] if pos[0] in CREW else num(pos[0], src, 'crew')
        o.b = num(pos[1], src, 'node')
        o.text = strs[0] if strs else ''
        strs = []
        pos = []
    elif opn == 'CARD':
        o.text = strs[0] if strs else ''
        strs = []
    if strs:
        o.text = strs[0]
    if opn == 'GOTO' or opn == 'LAND':
        o.a = num(take('tol', 0), src, 'tol')
    elif opn == 'CHECK':
        o.b = num(take('limit', 0), src, 'limit')
    elif opn == 'RINGS':
        pass
    elif opn == 'ENTER':
        if pos:
            o.mode = MODES[pos[0]]
            pos = pos[1:]
        o.a = num(take('veh', 0), src, 'veh')
    elif opn == 'RACE':
        o.b = num(take('laps', 1), src, 'laps')
    elif opn == 'CHASE':
        o.a = num(take('type', 0), src, 'type')
        o.b = num(take('ticks', 0), src, 'ticks')
    elif opn == 'DESTROY':
        o.a = num(take('type', 0), src, 'type')
    elif opn == 'BLAST':
        o.zone = o.places[0] if o.places else None
        o.n = num(take('n', 0), src, 'n')
    elif opn == 'FOES':
        o.n = num(take('n', 1), src, 'n')
        k = take('kind', 'raider')
        o.a = FOES[k] if k in FOES else num(k, src, 'kind')
        o.b = num(take('hp', 0), src, 'hp')
    elif opn == 'BOSS':
        o.a = num(take('boss', 0), src, 'boss')
    elif opn == 'ESCORT':
        o.a = num(take('type', 0), src, 'type')
    elif opn == 'DEFEND':
        o.a = num(take('hp', 0), src, 'hp')
        o.b = num(take('secs', 0), src, 'secs')
    elif opn == 'CRATES':
        d = take('drop', None)
        if d is None:
            raise SfmError('%s: crates needs drop=PLACE' % src)
        o.drop = place_refs([d], src)[0]
    elif opn == 'STUNT':
        o.a = num(take('points', 0), src, 'points')
        z = take('zone', None)
        o.zone = place_refs([z], src)[0] if z else None
    elif opn == 'JUMP':
        o.a = num(float(take('cells', 0)) * 8, src, 'cells')
    elif opn == 'SCORE':
        o.a = num(pos[0] if pos else take('x100', 0), src, 'score')
        pos = []
    elif opn == 'WANTED':
        o.a = num(take('stars', 0), src, 'stars')
        o.b = num(take('secs', 0), src, 'secs')
    elif opn == 'PHONE':
        o.n = num(take('n', 1), src, 'n')
    elif opn == 'SURVIVE':
        o.b = num(take('secs', 0), src, 'secs')
    elif opn == 'TIMER':
        o.b = num(take('secs', 0), src, 'secs')
    elif opn == 'WAIT':
        o.b = num(take('ticks', 0) or float(take('secs', 0)) * 30, src, 'wait')
    elif opn == 'SPAWNVEH':
        o.a = num(take('type', 0), src, 'type')
    elif opn == 'CEIL':
        if not pos:
            raise SfmError('%s: ceil HEIGHT zone=ZONE' % src)
        o.a = num(pos[0], src, 'height')
        pos = pos[1:]
        z = take('zone', None)
        o.zone = place_refs([z], src)[0] if z else None
    elif opn == 'ZONE':
        z = take('zone', None) or (pos[0] if pos else None)
        o.zone = place_refs([z], src)[0] if z else None
        pos = []
    elif opn in ('GIVE', 'UNLOCK', 'GATEWAY'):
        o.a = num(pos[0] if pos else take('n', 0), src, 'arg')
        pos = []
    elif opn == 'SET':
        o.a = num(take('flag', 0), src, 'flag')
        o.b = num(take('value', 1), src, 'value')
    for k in kv:
        if k not in used and k not in ('hud',):
            raise SfmError('%s: %s does not take %s=' % (src, op, k))
    if pos and opn not in ('ENTER',):
        raise SfmError('%s: %s: what is %r?' % (src, op, ' '.join(pos)))
    return o


def parse_file(path, out, gen=False):
    """Missions of one .sfm file appended to out (a list)."""
    cur = None
    base = os.path.basename(path)
    with open(path) as f:
        lines = f.read().split('\n')
    for ln, raw in enumerate(lines, 1):
        src = '%s:%d' % (base, ln)
        try:
            t = P.tokens(raw)
        except P.PlaceError as e:
            raise SfmError('%s: %s' % (src, e))
        if not t:
            continue
        w = t[0]
        if w in KINDS and not raw[0].isspace():
            if len(t) < 3 or not t[2].startswith('"'):
                raise SfmError('%s: %s NAME "TITLE" key=value ...' % (src, w))
            m = Mission(KINDS[w], t[1], unquote(t[2]), src)
            m.gen = gen
            pos, kv = _kv(t[3:])
            for k, v in kv.items():
                if k == 'map':
                    m.map = int(v)
                elif k == 'act':
                    m.act = int(v)
                elif k == 'tier':
                    m.tier = int(v)
                elif k == 'giver':
                    m.giver = CREW[v] if v in CREW else int(v)
                elif k == 'par':
                    m.par = 0 if v == 'auto' else int(v)
                elif k == 'pay':
                    m.pay = int(v)
                elif k == 'score':
                    m.score = int(v)
                elif k == 'fail':
                    for f_ in v.split(','):
                        if f_ not in FAIL:
                            raise SfmError('%s: fail=%s' % (src, f_))
                        m.flags |= FAIL[f_]
                elif k == 'mode':
                    for f_ in re.split(r'[,+]', v):
                        if f_ not in START:
                            raise SfmError('%s: mode=%s' % (src, f_))
                        m.flags |= START[f_]
                elif k == 'start':
                    m.start = place_refs([v], src)[0]
                else:
                    raise SfmError('%s: header key %s' % (src, k))
            for p in pos:
                if p == 'repeat':
                    m.flags |= F.MS_REPEAT
                elif p == 'phone':
                    m.flags |= F.MF_PHONE
                elif p == 'after':
                    m.flags |= F.MS_AFTER
                else:
                    raise SfmError('%s: header word %r' % (src, p))
            if m.map is None:
                raise SfmError('%s: %s %s has no map=' % (src, w, t[1]))
            out.append(m)
            cur = m
            continue
        if cur is None:
            raise SfmError('%s: an objective before any act' % src)
        if w == 'brief' and False:
            pass
        try:
            cur.objs.append(parse_obj(t, src))
        except (KeyError, ValueError) as e:
            raise SfmError('%s: %s %r' % (src, type(e).__name__, e))
    return out


def load_dir(root):
    """All missions under root (hand ones, then gen/), in file order."""
    out = []
    for sub, gen in (('', False), ('gen', True)):
        d = os.path.join(root, sub) if sub else root
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith('.sfm'):
                parse_file(os.path.join(d, f), out, gen)
    return out


# ---- the campaign file ----
class Chapter:
    def __init__(self):
        self.map = 0
        self.flags = 0
        self.split = 0
        self.hover = (0, 0)
        self.title = ''
        self.brief = ''
        self.index = 0
        self.src = ''


def parse_campaign(path):
    """-> dict(chapters=[Chapter], consts={name: int}). Lines:
         chapter map=0 flags=story,drop split=3 hover=62,30 title="FREEDOM CITY" brief="..."
         const NAME = N"""
    chapters, consts = [], {}
    base = os.path.basename(path)
    with open(path) as fh:
        lines = fh.read().split('\n')
    for ln, raw in enumerate(lines, 1):
        src = '%s:%d' % (base, ln)
        t = P.tokens(raw)
        if not t:
            continue
        if t[0] == 'const':
            consts[t[1]] = int(t[3], 0)
        elif t[0] == 'chapter':
            c = Chapter()
            c.src = src
            for tk in t[1:]:
                k, v = tk.split('=', 1)
                if k == 'map':
                    c.map = int(v)
                elif k == 'flags':
                    for f_ in v.split(','):
                        c.flags |= F.ENUMS['CH'][f_.upper()]
                elif k == 'split':
                    c.split = int(v)
                elif k == 'hover':
                    x, y = (float(q) for q in v.split(','))
                    c.hover = (int(round(x * 2)), int(round(y * 2)))
                elif k == 'title':
                    c.title = unquote(v)
                elif k == 'brief':
                    c.brief = unquote(v)
                else:
                    raise SfmError('%s: chapter key %s' % (src, k))
            c.index = len(chapters)
            chapters.append(c)
        elif t[0] == 'crew':
            pass
        else:
            raise SfmError('%s: unknown line %r' % (src, t[0]))
    return dict(chapters=chapters, consts=consts)
