#!/usr/bin/env python3
"""sfc: the content compiler. content/ (places, missions, campaign, ids.lock, calibration.json) in, the mission data
blob (src/misdata.h) out, every validator (validate.py) run on the way. tools/s2build.py calls build(rom, orig, gen);
a content error raises, so the build stops.

    python3 tools/content/sfc.py check   [--rom ROM | --cache DIR]       compile and validate; messages say file:line
    python3 tools/content/sfc.py ids     [--rom ROM | --cache DIR]       add new missions and pinned auto places to ids.lock
    python3 tools/content/sfc.py gen     [MAP ...] [--check]             rewrite content/*/gen (the generators; --check: only compare)
    python3 tools/content/sfc.py report  [--rom ROM | --cache DIR]       counts per map and chapter, the biggest times
    python3 tools/content/sfc.py preview KEY [--rom ROM | --cache DIR]   a PNG of a mission's route over its map
    python3 tools/content/sfc.py build   [--rom ROM] -o blob.bin         the blob
"""
import argparse
import collections
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import misfmt as F  # noqa: E402
import par as PAR  # noqa: E402
import places as P  # noqa: E402
import sfm  # noqa: E402
import emit  # noqa: E402
import validate as V  # noqa: E402

CONTENT = os.path.join(ROOT, 'content')
CACHE = os.path.join(ROOT, 'build', 'atlas')


class ContentError(Exception):
    pass


class Content:
    """The sources, parsed."""
    def __init__(self, root=CONTENT):
        self.root = root
        self.maps = {}
        self.missions = []
        self.campaign = dict(chapters=[], consts={})
        self.lock = None
        self.cal = PAR.load(os.path.join(root, 'calibration.json'))
        self.errors = []

    @classmethod
    def load(cls, root=CONTENT):
        c = cls(root)
        try:
            c.maps = P.load_dir(os.path.join(root, 'maps'))
            cp = os.path.join(root, 'campaign.sfc')
            if os.path.exists(cp):
                c.campaign = sfm.parse_campaign(cp)
            sfm.CONSTS.clear()
            sfm.CONSTS.update(c.campaign['consts'])
            c.missions = sfm.load_dir(os.path.join(root, 'missions'))
        except (P.PlaceError, sfm.SfmError) as e:
            raise ContentError(str(e))
        lp = os.path.join(root, 'ids.lock')
        if os.path.exists(lp):
            with open(lp) as f:
                c.lock = json.load(f)
        return c

    @classmethod
    def from_texts(cls, files, lock=None, cal=None):
        """Content from {relative path: text} (the fixtures): written to a folder and loaded."""
        with tempfile.TemporaryDirectory(prefix='sfc') as d:
            for rel, text in files.items():
                p = os.path.join(d, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, 'w') as f:
                    f.write(text)
            c = cls.load(d)
        if lock is not None:
            c.lock = lock
        if cal is not None:
            c.cal = cal
        return c


def load_atlases(rom, cache=CACHE, levels=range(11)):
    import atlas
    return {m: atlas.Atlas(rom, m, cache) for m in levels}


def cached_atlases(cache=CACHE, levels=range(11)):
    import atlas
    out = {}
    for m in levels:
        a = atlas.Atlas.cached(cache, m)
        if a is not None:
            out[m] = a
    return out


def open_rom(path):
    """Payback as the merge build has it just before the content is built (phones added, the arena regridded)."""
    sys.path[:0] = [os.path.join(ROOT, 'tools'), os.path.join(ROOT, '..', 'payback-mod')]
    from paybackmod.rom import PaybackRom
    import mksolo
    import s2build
    with open(path, 'rb') as f:
        orig = f.read()
    rom = PaybackRom(orig)
    mksolo.offer_every_map(rom.d)
    mksolo.add_phones(rom)
    s2build.pre_world(rom, orig)
    return rom, orig


class Result:
    def __init__(self):
        self.blob = None
        self.ship = None                                        # (the blob without the keys: what goes into the ROM)
        self.names = []                                         # (the mission keys in blob order)
        self.rm = []
        self.order = []
        self.issues = []
        self.ctx = None

    @property
    def errors(self):
        return V.errors(self.issues)


def order_chapters(chapters, rm):
    """[(chapter index, [RMis])]: a chapter's missions are its acts by number, then contracts, challenges, medals."""
    by = collections.defaultdict(list)
    for m in rm:
        by[m.map].append(m)
    out = []
    for i, ch in enumerate(chapters):
        ms = by.get(ch.map, []) if not (ch.flags & F.CH_RESERVED) else []
        ms = sorted(ms, key=lambda m: (m.kind, m.act if m.kind == F.MK_ACT else 0))       # (stable: file order within a kind)
        out.append((i, ms))
    return out


def compile(content, atlases, lock=None, quota=None, new_ids=False, only=None):
    """Resolve, id, par, pack and validate. -> Result (the blob is None when the content did not resolve)."""
    res = Result()
    errs = []
    chapters = content.campaign['chapters']
    cal = content.cal
    lock = lock if lock is not None else content.lock
    rs = emit.Resolver(content.maps, atlases)
    rm = []
    for m in content.missions:
        if m.map not in atlases:
            errs.append(V.Issue('V2', V.ERR, m.src, '%s: no atlas for map %d' % (m.name, m.map)))
            continue
        try:
            rm.append(rs.mission(m))
        except (P.PlaceError, sfm.SfmError, KeyError, ValueError, AssertionError) as e:
            errs.append(V.Issue('V2', V.ERR, m.src, '%s: %s' % (m.name, e)))
    res.rm = rm
    for m in rm:
        m.par, m.par_from = PAR.final_par(m, cal)
    # ids from the lock; with new_ids the new missions get the next numbers
    ids = dict((lock or {}).get('ids', {}))
    nxt = (lock or {}).get('next', 0)
    order = order_chapters(chapters, rm)
    seq = [m for _, ms in order for m in ms] + [m for m in rm if not any(m is q for _, ms in order for q in ms)]
    for m in seq:
        if m.key in ids:
            m.id = ids[m.key]
        elif new_ids:
            m.id = ids[m.key] = nxt
            nxt += 1
        else:
            m.id = 0xffff                                              # (V8 says it)
    newlock = dict(lock or {}, ids=ids, next=nxt)
    newlock.setdefault('retired', [])
    auto = {}
    for (lv, name), pd in rs.auto.items():
        try:
            h = P.resolve_h(atlases[lv], pd)
        except P.PlaceError:
            continue
        auto['%d:%s' % (lv, name)] = [int(round(pd.x * 8)), int(round(pd.y * 8)), h]
    if new_ids:
        newlock['auto'] = dict(newlock.get('auto', {}), **auto)
    res.newlock = newlock
    res.order = order
    blob = parsed = None
    ctx = V.Ctx(rm, chapters, atlases, cal, order, ids=ids, lock=newlock if new_ids else lock, quota=quota, errors=errs)
    ctx.auto_cells = auto
    if not errs or True:
        try:
            b = emit.build_blob([(i, ms) for i, ms in order], chapters, content.campaign['consts'])
            blob = emit.pack(b)
            parsed = F.parse(blob)
            res.ship = emit.pack(b, names=False)
            res.names = list(b.names)
        except (ValueError, AssertionError, KeyError, P.PlaceError) as e:
            errs.append(V.Issue('V14', V.ERR, 'blob', str(e)))
    ctx.blob, ctx.parsed = blob, parsed
    ctx.errors = list(errs)                                    # (the blob step's too: it ran after the Ctx was made)
    res.ctx = ctx
    res.issues = V.run(ctx, only)
    res.blob = blob
    return res


def report_text(res):
    lines = []
    cnt = collections.defaultdict(collections.Counter)
    for m in res.rm:
        cnt[m.map][m.kind] += 1
    nm = ('acts', 'contracts', 'challenges', 'medals')
    for lv in sorted(cnt):
        lines.append('map %2d: %s' % (lv, '  '.join('%d %s' % (cnt[lv][k], nm[k]) for k in range(4))))
    if res.blob:
        lines.append('blob %d bytes, %d missions, %d objectives, %d places, %d texts' % (
            len(res.blob), len(res.rm), len(res.ctx.parsed['objs']), len(res.ctx.parsed['places']), len(res.ctx.parsed['texts'])))
    src = collections.Counter(m.par_from for m in res.rm)
    lines.append('par from: ' + ', '.join('%s %d' % kv for kv in sorted(src.items())))
    return '\n'.join(lines)


def build(rom, orig, gen):
    """tools/s2build.py's hook: the blob for the link. Any error stops the build."""
    content = Content.load()
    at = load_atlases(rom)
    res = compile(content, at)
    for i in res.issues:
        print('sfc: ' + V.fmt(i))
    bad = res.errors
    if bad:
        raise ContentError('%d content errors (first: %s)' % (len(bad), V.fmt(bad[0])))
    print('sfc: ' + report_text(res).replace('\n', '\nsfc: '))
    sidecar = os.path.join(ROOT, 'build', 'content', 'names.json')           # (the keys stay out of the ROM; the harness reads them here)
    os.makedirs(os.path.dirname(sidecar), exist_ok=True)
    with open(sidecar, 'w') as f:
        json.dump(res.names, f)
    return res.ship


# ---- the command line ----
def _atlases(args):
    if args.rom:
        rom, orig = open_rom(args.rom)
        return load_atlases(rom, args.cache or CACHE)
    return cached_atlases(args.cache or CACHE)


def cmd_check(args):
    content = Content.load()
    res = compile(content, _atlases(args))
    for i in res.issues:
        print(V.fmt(i))
    print(report_text(res))
    return 1 if res.errors else 0


def cmd_ids(args):
    content = Content.load()
    res = compile(content, _atlases(args), new_ids=True)
    path = os.path.join(CONTENT, 'ids.lock')
    nl = res.newlock
    with open(path, 'w') as f:
        json.dump(nl, f, indent=1, sort_keys=True)
        f.write('\n')
    print('ids.lock: %d ids, next %d' % (len(nl['ids']), nl['next']))
    return 0


def cmd_gen(args):
    import gen
    return gen.main(args.maps, args.check, _atlases(args))


def cmd_report(args):
    content = Content.load()
    res = compile(content, _atlases(args))
    print(report_text(res))
    for ch_i, ms in res.order:
        ch = content.campaign['chapters'][ch_i]
        print('chapter %d map %d %s: %d missions' % (ch_i + 1, ch.map, ch.title, len(ms)))
        for m in ms:
            if m.kind == F.MK_ACT:
                print('   act %d %-19s par %3d (%s) %d objs' % (m.act, m.title, m.par, m.par_from, len(m.objs)))
    return 0


def cmd_preview(args):
    import preview
    content = Content.load()
    at = _atlases(args)
    res = compile(content, at)
    for m in res.rm:
        if m.key == args.key or m.name == args.key:
            pts = [(p.name, p.x, p.y, p.kind) for _, _, p in V.places_of(m)]
            route = [[(p.x, p.y) for p in ([m.start] if m.start else []) + o.places] for o in m.objs if o.places]
            out = args.out or os.path.join(ROOT, 'build', 'content', m.key + '.png')
            os.makedirs(os.path.dirname(out), exist_ok=True)
            preview.render(at[m.map], pts, route, out)
            print(out)
            return 0
    print('no mission %s' % args.key)
    return 1


def cmd_build(args):
    rom, orig = open_rom(args.rom)
    blob = build(rom, orig, None)
    with open(args.out, 'wb') as f:
        f.write(blob)
    print('%s: %d bytes' % (args.out, len(blob)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='sfc')
    ap.add_argument('cmd', choices=['check', 'ids', 'gen', 'report', 'preview', 'build'])
    ap.add_argument('rest', nargs='*')
    ap.add_argument('--rom', default=os.environ.get('PAYBACK_ROM'))
    ap.add_argument('--cache')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('-o', '--out')
    args = ap.parse_args(argv)
    args.maps = [int(x) for x in args.rest] if args.cmd == 'gen' else []
    args.key = args.rest[0] if args.cmd == 'preview' and args.rest else None
    try:
        return {'check': cmd_check, 'ids': cmd_ids, 'gen': cmd_gen, 'report': cmd_report, 'preview': cmd_preview,
                'build': cmd_build}[args.cmd](args)
    except ContentError as e:
        print('sfc: ' + str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())
