#!/usr/bin/env python3
"""gpuwait_scan.py ELF [--json OUT]: find busy-waits on GPUSTAT bit 26 (0x04000000, "ready to receive a command word").

The documentation (psx-spx, GPUSTAT bit 26): the bit is CLEAR while the GPU "wants to either receive additional
parameters/data or is busy".  A helper that waits for it before every GP0 word therefore never returns once a command
word has been sent and its parameters are due.  PCSX-family GPUs report the bit as always set.

A site is `lui rM,0x0400` whose every later use (until rM is overwritten) is `and rX,rY,rM` feeding a beq/bne
against $zero.  For each site the tool gives the address of the lui; TEST PATCH = the same lui with 0x1000 (bit 28,
"ready to receive a DMA block": there is room for another word).  Sites with other uses of the constant are listed
as 'mixed' and never patched.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mips1_lint import elf_parse   # noqa: E402


def dest(w):
    op = w >> 26
    if op == 0:
        f = w & 0x3f
        if f in (8, 0x0c, 0x0d, 0x11, 0x13, 0x18, 0x19, 0x1a, 0x1b):
            return 0
        return (w >> 11) & 31
    if op == 3:
        return 31
    if 8 <= op <= 0x0f or 0x20 <= op <= 0x26:
        return (w >> 16) & 31
    if op in (0x10, 0x12) and ((w >> 21) & 31) in (0, 2):
        return (w >> 16) & 31
    return 0


def uses(w, r):
    op = w >> 26
    rs, rt = (w >> 21) & 31, (w >> 16) & 31
    if op == 0:
        f = w & 0x3f
        if f in (0, 2, 3):
            return rt == r
        return rs == r or rt == r
    if op in (2, 3, 0x0f):
        return False
    if op in (4, 5) or 0x28 <= op <= 0x2e:
        return rs == r or rt == r
    if op in (0x10, 0x12):
        return rt == r and rs in (4, 6)
    return rs == r


def scan(path):
    secs, funcs = elf_parse(path)
    sites = []
    for name, base, data, ex in secs:
        if not ex:
            continue
        for fa, fs, fn in funcs:
            if not (base <= fa < base + len(data)):
                continue
            ws = struct.unpack_from('<%dI' % (fs // 4), data, fa - base)
            for i, w in enumerate(ws):
                if (w >> 26) != 0x0f or (w & 0xffff) != 0x0400:
                    continue
                rm = (w >> 16) & 31
                waits, other = [], []
                for j in range(i + 1, len(ws)):
                    x = ws[j]
                    if uses(x, rm):
                        ok = False
                        if (x >> 26) == 0 and (x & 0x3f) == 0x24:
                            rd = (x >> 11) & 31
                            for k in range(j + 1, min(j + 3, len(ws))):
                                y = ws[k]
                                if (y >> 26) in (4, 5) and {(y >> 21) & 31, (y >> 16) & 31} == {rd, 0}:
                                    ok = True
                        (waits if ok else other).append(fa + 4 * j)
                    if dest(x) == rm:
                        break
                sites.append({'addr': fa + 4 * i, 'func': fn, 'off': 4 * i, 'reg': rm, 'word': w, 'waits': waits, 'other': other,
                              'kind': 'wait' if waits and not other else ('mixed' if waits else 'other')})
    return sites


def main():
    path = sys.argv[1]
    sites = scan(path)
    by = {}
    for s in sites:
        by.setdefault(s['kind'], []).append(s)
    for kind in ('wait', 'mixed', 'other'):
        L = by.get(kind, [])
        fns = {}
        for s in L:
            fns[s['func']] = fns.get(s['func'], 0) + 1
        print('%-5s %3d sites: %s' % (kind, len(L), ' '.join('%s:%d' % kv for kv in sorted(fns.items()))))
    for s in by.get('mixed', []):
        print('  mixed %08x %s+0x%x  waits %s other %s' % (s['addr'], s['func'], s['off'], ['%08x' % a for a in s['waits']], ['%08x' % a for a in s['other']]))
    if '--json' in sys.argv:
        out = sys.argv[sys.argv.index('--json') + 1]
        patches = [{'addr': s['addr'], 'old': s['word'], 'new': (s['word'] & 0xffff0000) | 0x1000, 'func': s['func']} for s in by.get('wait', [])]
        # a mixed site keeps its constant; the branch of each of its wait loops is replaced by nop instead (the word after the `and`)
        secs, _ = elf_parse(path)
        def word(a):
            for name, base, data, ex in secs:
                if base <= a < base + len(data):
                    return struct.unpack_from('<I', data, a - base)[0]
        for s in by.get('mixed', []):
            for a in s['waits']:
                for k in (4, 8):
                    w = word(a + k)
                    if (w >> 26) in (4, 5):
                        patches.append({'addr': a + k, 'old': w, 'new': 0, 'func': s['func'] + ' (wait branch -> nop)'})
                        break
        json.dump({'elf': os.path.abspath(path), 'what': 'GPUSTAT wait mask bit 26 -> bit 28 (TEST PATCH)', 'patches': patches}, open(out, 'w'), indent=1)
        print('%d patches -> %s' % (len(patches), out))


if __name__ == '__main__':
    main()
