#!/usr/bin/env python3
"""gpuwait_classify.py ELF [--json OUT] [-v]: classify every busy-wait on GPUSTAT bit 26 by the GP0 word that follows it.

  C  the word is a command (or the wait is a plain idle wait before a DMA / the flip): waiting for bit 26 is correct.
  P  the word is a parameter or VRAM data of the command before it: the documentation says bit 26 stays CLEAR
     while the GPU waits for parameters/data, so this wait never ends on hardware and on GPUs that model the bit.

Class S: a tiny out-of-line write function whose one wait serves command and parameter words alike.
TEST PATCH (--json): the loop branch of every P and S wait is replaced by nop (the word is written without waiting; a
command and its parameters fit the GPU's FIFO once the command wait has seen the GPU idle).  C waits are untouched.
Classification = value analysis of the stored word (constants built by lui/ori/or/addu) plus the command stream state
(how many parameters the last recognised command still expects), in address order inside each function.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mips1_lint import elf_parse      # noqa: E402
from gpuwait_scan import scan, dest   # noqa: E402

NPAR = {0x01: 0, 0x02: 2, 0x03: 0, 0x80: 3, 0xa0: 2, 0xc0: 2}


def is_cmd_const(k, composite):
    t = k >> 24
    if k in (0x01000000, 0x03000000) and not composite:
        return True
    return t == 0x02 or 0x20 <= t <= 0x7f or t in (0x80, 0xa0, 0xc0) or 0xe1 <= t <= 0xe6


def npar(k):
    t = k >> 24
    if t in NPAR:
        return NPAR[t]
    if 0x60 <= t <= 0x7f:
        return 1 + (1 if (t & 0x18) == 0 else 0) + (1 if t & 0x04 else 0)     # rectangle: xy [+uv] [+wh]
    if 0x20 <= t <= 0x3f:
        n = 4 if t & 0x08 else 3
        return n * (1 + (1 if t & 0x04 else 0)) + ((n - 1) if t & 0x10 else 0)
    return 0


def lui_const(ws, upto, r):
    """constant held by register r just before index upto when it was built by lui [+ ori], else None"""
    for c in range(upto - 1, max(upto - 14, -1), -1):
        x = ws[c]
        if r and dest(x) == r:
            op = x >> 26
            if op == 0x0f:
                return (x & 0xffff) << 16
            if op == 0x0d and ((x >> 21) & 31) == r:
                k = lui_const(ws, c, r)
                return None if k is None else k | (x & 0xffff)
            return None
    return None


def value(ws, k):
    """kind of the word stored by the sw at index k: ('const', K) | ('comp', K) | ('zero',) | ('data',) | ('unk',)"""
    rv = (ws[k] >> 16) & 31
    if rv == 0:
        return ('zero',)
    c = lui_const(ws, k, rv)
    if c is not None:
        return ('const', c)
    for b in range(k - 1, max(k - 16, -1), -1):
        x = ws[b]
        if dest(x) == rv:
            op = x >> 26
            if op == 0 and (x & 0x3f) in (0x25, 0x21):          # or / addu: a command when one side is a command constant
                for r in ((x >> 21) & 31, (x >> 16) & 31):
                    c = lui_const(ws, b, r)
                    if c is not None and is_cmd_const(c, True):
                        return ('comp', c)
                return ('expr',)
            if op == 0 and (x & 0x3f) == 0:
                return ('expr',)
            if 0x20 <= op <= 0x26:
                return ('unk',) if ((x >> 21) & 31) in (29, 30) else ('data',)
            return ('unk',)
    return ('unk',)


def classify(path):
    secs, funcs = elf_parse(path)
    code = {}
    for name, base, data, ex in secs:
        for fa, fs, fn in funcs:
            if ex and base <= fa < base + len(data):
                code[fn] = (fa, struct.unpack_from('<%dI' % (fs // 4), data, fa - base))
    per = {}
    for s in scan(path):
        for a in s['waits']:
            per.setdefault(s['func'], []).append(a)
    out = []
    for fn, ands in per.items():
        fa, ws = code[fn]
        expect, data = 0, False
        for a in sorted(ands):
            i = (a - fa) // 4
            br = i + 1
            while (ws[br] >> 26) not in (4, 5):
                br += 1
            k, kind = br + 2, None
            while k < min(len(ws), br + 16):
                w = ws[k]
                if (w >> 26) == 0x2b and ((w >> 21) & 31) not in (29, 30):
                    kind = value(ws, k)
                    break
                if (w >> 26) in (2, 3, 4, 5) or (w >> 26) == 1:      # control flow before any store: an idle wait
                    break
                k += 1
            shared = (kind is not None and len(ands) == 1 and len(ws) <= 16 and k < len(ws) and ((ws[k] >> 16) & 31) == 4 and
                      any(x == 0x03e00008 for x in ws[k:k + 3]) and not any((x >> 26) == 0x0f and ((x >> 16) & 31) == 4 for x in ws[:k]) and
                      not any((x >> 26) in (8, 9, 13) and ((x >> 16) & 31) == 4 for x in ws[:k]))
            if shared:
                # a tiny out-of-line "write one GP0 word" function: its argument (a0, untouched) goes to GP0 after the wait.
                # It serves command words and parameter words alike, so the wait is wrong for some of its calls.
                cls, why = 'S', 'shared write function: GP0 = its argument, used for command and parameter words alike'
            elif kind is None:
                cls, why, data = 'C', 'idle wait (no GP0 word follows)', False
            elif kind[0] in ('const', 'comp') and is_cmd_const(kind[1], kind[0] == 'comp') and not expect:
                cls, why, expect = 'C', 'command %08x' % kind[1], npar(kind[1])
                data = (kind[1] >> 24) == 0xa0                          # CPU -> VRAM: two parameters, then data words
            elif kind[0] == 'unk' and not expect:
                cls, why, expect, data = 'C', 'unknown word where a command is due', 1 << 30, False
            elif not expect and not data and kind[0] in ('const', 'zero'):
                cls, why = 'P', 'constant outside a known command (taken as a parameter)'
            else:
                cls, why = 'P', {'const': 'constant %08x' % kind[1] if kind[0] == 'const' else '', 'zero': 'zero', 'data': 'word loaded from memory',
                                 'expr': 'computed word', 'unk': 'register/stack word inside a command', 'comp': 'computed'}.get(kind[0], kind[0])
                expect = max(0, expect - 1)
            out.append({'func': fn, 'and': a, 'branch': fa + 4 * br, 'branch_word': ws[br], 'class': cls, 'why': why})
    return sorted(out, key=lambda r: r['and'])


def main():
    path = sys.argv[1]
    rows = classify(path)
    nc = sum(1 for r in rows if r['class'] == 'C')
    ns = sum(1 for r in rows if r['class'] == 'S')
    fns = {}
    for r in rows:
        if r['class'] == 'P':
            fns[r['func']] = fns.get(r['func'], 0) + 1
    print('%s: %d waits on GPUSTAT bit 26: %d before a command / idle (correct), %d before parameter or data words (never end on an accurate GPU)%s' % (
        path, len(rows), nc, len(rows) - nc - ns, ', %d in a shared write function (wrong whenever it is called for a parameter or data word): %s' % (
            ns, ' '.join('%s@%08x' % (r['func'], r['and']) for r in rows if r['class'] == 'S')) if ns else ''))
    print('  parameter/data waits by function: ' + ' '.join('%s:%d' % kv for kv in sorted(fns.items())))
    if '-v' in sys.argv:
        for r in rows:
            print('  %s %08x %-13s %s' % (r['class'], r['and'], r['func'], r['why']))
    if '--json' in sys.argv:
        out = sys.argv[sys.argv.index('--json') + 1]
        patches = [{'addr': r['branch'], 'old': r['branch_word'], 'new': 0, 'func': r['func'], 'why': r['why']} for r in rows if r['class'] in ('P', 'S')]
        json.dump({'elf': os.path.abspath(path), 'what': 'TEST PATCH: loop branch of every GPUSTAT bit-26 wait that precedes a parameter/data word -> nop; '
                   'in a shared write function the wait is removed for all its words (commands are then not held back while the GPU is busy)', 'patches': patches},
                  open(out, 'w'), indent=1)
        print('  %d patches -> %s' % (len(patches), out))


if __name__ == '__main__':
    main()
