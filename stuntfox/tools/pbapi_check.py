#!/usr/bin/env python3
"""Stage 2 reaches Payback only through src/pbapi.h: this checks that header against Payback's ROM, and the
stage-2 sources for any Payback address of their own.

Every `#define PBA_x 0x... /*kind*/` in pbapi.h is checked against the ROM image:
    fn    a function: where it starts (an odd value is the Thumb entry; the name ending _FN is the bl target),
          that its first instruction is a push (or one of the few leaf functions named in LEAF), and that
          Payback calls it, a bl in its code or a pointer in a table or literal pool
    ram   a word of EWRAM or IWRAM that Payback's code addresses: the value, or a structure it is in, is in a
          literal pool
    rom   an address in Payback's ROM that its code addresses the same way
    site  a bl in Payback's code, to the function named in SITES

The stage-2 .c files, and stage2.h, may not contain an address in EWRAM, IWRAM or Payback's ROM (comments
apart): they say pb_goal_add() or PB_CLOCK, and pbapi.h has the numbers. The build runs this after linking.

    python3 tools/pbapi_check.py "Payback (Europe) (En,Fr,De,Es,It).gba"
"""
import os
import re
import struct
import sys

GBA = 0x08000000
CODE_END = 0x00120000            # (Payback's code and its pools: the ROM image past this is data)
LEAF = {'PBA_GET_SCORE'}         # functions that open with something other than a push (checked by hand)
# functions nothing in the image calls (no bl, no pointer in any table or pool): the halfwords they must hold,
# by offset from their start, instead. pb_kill: push {r4, r5, lr}; r5 = the tag; r4 = 0; ... movs r2, #0xa6;
# lsls r1, r2, #1 (the tag is at +0x14c of each entity it walks)
UNCALLED = {'PBA_KILL': {0: 0xb530, 2: 0x1c05, 4: 0x2400, 0x14: 0x22a6, 0x16: 0x0051}}
SITES = {'PBA_EEP_IDENT_SITE': 'PBA_EEP_IDENT'}
KINDS = ('fn', 'ram', 'rom', 'site')


def parse(header):
    out = []
    for m in re.finditer(r'#define\s+(PBA_\w+)\s+(0x[0-9a-fA-F]+)\s*/\*(\w+)\*/', open(header).read()):
        out.append((m.group(1), int(m.group(2), 16), m.group(3)))
    return out


def bl_target(d, site):
    h1, h2 = struct.unpack_from('<HH', d, site - GBA)
    if (h1 & 0xf800) != 0xf000 or (h2 & 0xf800) != 0xf800:
        return None
    off = (h1 & 0x7ff) << 12 | (h2 & 0x7ff) << 1
    off -= (1 << 23) if off & (1 << 22) else 0
    return site + 4 + off


class Rom:
    def __init__(self, d):
        self.d = d
        n = min(len(d), CODE_END) // 4
        self.words = struct.unpack_from('<%dI' % n, d, 0)
        self.pool = {}
        for i, w in enumerate(self.words):
            self.pool.setdefault(w, []).append(i * 4)
        self.calls = None

    def callers(self, fn):
        if self.calls is None:
            self.calls = {}
            for a in range(GBA, GBA + min(len(self.d), CODE_END), 2):
                t = bl_target(self.d, a)
                if t is not None:
                    self.calls.setdefault(t, []).append(a)
        return self.calls.get(fn, [])

    def pooled(self, value, below=0):
        """Pool words equal to value, or (below > 0) in value - below .. value (a structure it is in)."""
        if below == 0:
            return self.pool.get(value, [])
        return [o for v in range(value - below, value + 1) for o in self.pool.get(v, [])]

    def half(self, addr):
        return struct.unpack_from('<H', self.d, addr - GBA)[0]


def check_api(rom, header):
    api, bad, notes = parse(header), [], []
    by = {n: v for n, v, k in api}
    for name, v, kind in api:
        if kind not in KINDS:
            bad.append('%s: unknown kind /*%s*/' % (name, kind))
        elif kind == 'fn':
            fn = v & ~1
            if (v & 1) == name.endswith('_FN'):
                bad.append('%s: 0x%08x is %s' % (name, v, 'a bl target with the Thumb bit' if name.endswith('_FN')
                                                 else 'a function pointer without the Thumb bit'))
            elif not GBA <= fn < GBA + len(rom.d):
                bad.append('%s: 0x%08x is not in the ROM' % (name, v))
            elif name not in LEAF and rom.half(fn) >> 8 not in (0xb4, 0xb5):
                bad.append('%s: no push at 0x%08x (0x%04x): not a function start' % (name, fn, rom.half(fn)))
            elif name in UNCALLED:
                if any(rom.half(fn + o) != h for o, h in UNCALLED[name].items()):
                    bad.append('%s: 0x%08x is not the function it was taken for' % (name, fn))
                else:
                    notes.append('%s: nothing calls it; its code is as expected' % name)
            elif not (rom.callers(fn) or rom.pooled(fn | 1) or rom.pooled(fn)):
                bad.append('%s: nothing in Payback calls 0x%08x' % (name, fn))
        elif kind == 'ram':
            if not (0x02000000 <= v < 0x02040000 or 0x03000000 <= v < 0x03008000):
                bad.append('%s: 0x%08x is not in EWRAM or IWRAM' % (name, v))
            elif not rom.pooled(v):
                if rom.pooled(v, 0x100):
                    notes.append('%s: addressed through a base below it' % name)
                else:
                    bad.append('%s: no code of Payback addresses 0x%08x' % (name, v))
        elif kind == 'rom':
            if not GBA <= v < GBA + len(rom.d):
                bad.append('%s: 0x%08x is not in the ROM' % (name, v))
            elif not (rom.pooled(v) or rom.pooled(v, 0x400)):
                bad.append('%s: no code of Payback addresses 0x%08x' % (name, v))
        elif kind == 'site':
            target = by.get(SITES.get(name, ''), None)
            if target is None:
                bad.append('%s: no function named for it in SITES' % name)
            elif bl_target(rom.d, v) != target & ~1:
                bad.append('%s: the bl at 0x%08x goes to %s, not 0x%08x' % (name, v, hex(bl_target(rom.d, v) or 0), target & ~1))
    return api, bad, notes


ADDR = re.compile(r'\b0[xX]0([2-3][0-9a-fA-F]{6}|[89a-dA-D][0-9a-fA-F]{6})\b')


def strip_comments(s):
    return re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: '\n' * m.group(0).count('\n'), s, flags=re.S)


def scan_files(files):
    bad = []
    for f in files:
        text = strip_comments(open(f).read())
        for n, line in enumerate(text.split('\n'), 1):
            for m in ADDR.finditer(line):
                a = int(m.group(0), 16)
                if 0x02000000 <= a < 0x02040000 or 0x03000000 <= a < 0x03008000 or GBA <= a < 0x0e000000:
                    bad.append('%s:%d: a raw address %s (name it in pbapi.h)' % (os.path.basename(f), n, m.group(0)))
    return bad


def check(orig, srcdir, files):
    """The report; SystemExit with what is wrong. orig: the Payback ROM (bytes); files: stage-2 sources built."""
    rom = Rom(bytes(orig))
    api, bad, notes = check_api(rom, os.path.join(srcdir, 'pbapi.h'))
    scan = [f for f in files if os.path.dirname(os.path.abspath(f)) == os.path.abspath(srcdir)]
    if os.path.exists(os.path.join(srcdir, 'stage2.h')):
        scan.append(os.path.join(srcdir, 'stage2.h'))
    bad += scan_files(sorted(set(scan)))
    if bad:
        sys.exit('\n'.join('pbapi_check: ' + b for b in bad) + '\npbapi_check: failed')
    return 'pbapi_check: OK, %d Payback addresses in pbapi.h match its ROM, %d stage-2 files hold none of their own' \
        % (len(api), len(scan))


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(os.path.dirname(here), 'src')
    names = [os.path.join(src, n) for n in ('s2core.c',)]
    print(check(open(sys.argv[1], 'rb').read(), src, [n for n in names if os.path.exists(n)]))
