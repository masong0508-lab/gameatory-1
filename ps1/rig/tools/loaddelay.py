#!/usr/bin/env python3
"""loaddelay.py: find R3000A load-delay hazards: a register loaded by lb/lh/lw/lbu/lhu/lwl/lwr or mfc0/mfc2/cfc2 and
read by the very next instruction (which still sees the OLD value on the real CPU and on emulators that model it;
PCSX-family HLE setups do not model it, so such code only fails on accurate emulators and hardware).

    loaddelay.py ELF [--section NAME ...]      executable sections (function symbols), plus whole named sections
    loaddelay.py --raw FILE --base ADDR        raw code image (data in it gives false hits)

A load in a branch delay slot followed by a use at the branch target cannot be seen by this linear scan.
"""
import struct
import sys

def loaded_reg(w):
    op = w >> 26
    if 0x20 <= op <= 0x26:
        return (w >> 16) & 31
    if op in (0x10, 0x12) and ((w >> 21) & 31) in (0, 2):       # mfc0 / mfc2 / cfc2
        return (w >> 16) & 31
    return 0

def sources(w):
    op = w >> 26
    rs, rt = (w >> 21) & 31, (w >> 16) & 31
    if op == 0:
        f = w & 0x3f
        if f in (0, 2, 3):
            return {rt}
        if f in (8, 9, 0x11, 0x13):
            return {rs}
        if f in (0x10, 0x12, 0x0c, 0x0d):
            return set()
        return {rs, rt}
    if op == 1 or op in (6, 7):
        return {rs}
    if op in (4, 5):
        return {rs, rt}
    if op in (2, 3, 0x0f):
        return set()
    if 8 <= op <= 0x0e:
        return {rs}
    if 0x20 <= op <= 0x26:
        return {rs, rt} if op in (0x22, 0x26) else {rs}
    if 0x28 <= op <= 0x2e:
        return {rs, rt}
    if op in (0x10, 0x11, 0x12, 0x13):
        return {rt} if rs in (4, 6) else set()
    if op in (0x32, 0x3a):                                      # lwc2 / swc2
        return {rs}
    return set()

def scan(data, base):
    out = []
    prev = 0
    for o in range(0, len(data) - 3, 4):
        w, = struct.unpack_from('<I', data, o)
        if prev:
            r = loaded_reg(prev)
            if r and r in sources(w):
                pop, op = prev >> 26, w >> 26
                if not (pop in (0x22, 0x26) and op in (0x22, 0x26) and ((w >> 16) & 31) == r and r not in {(w >> 21) & 31}):
                    out.append((base + o - 4, prev, w, r))
        prev = w
    return out

def main():
    a = sys.argv[1:]
    if a and a[0] == '--raw':
        d = open(a[1], 'rb').read()
        base = int(a[a.index('--base') + 1], 0) if '--base' in a else 0
        hits = scan(d, base)
        print('%s: %d words, %d load-delay hazards (raw scan)' % (a[1], len(d) // 4, len(hits)))
        for adr, p, w, r in hits[:30]:
            print('   %08x: %08x then %08x  uses $%d' % (adr, p, w, r))
        return
    sys.path.insert(0, __file__.rsplit('/', 1)[0])
    from mips1_lint import elf_parse
    extra = [a[i + 1] for i in range(len(a)) if a[i] == '--section']
    secs, funcs = elf_parse(a[0])
    total = words = 0
    for name, base, data, ex in secs:
        if name in extra or (ex and not funcs):
            hits = scan(data, base); words += len(data) // 4
            for adr, p, w, r in hits:
                print('   %08x: %08x then %08x  uses $%d   %s (whole section)' % (adr, p, w, r, name))
            total += len(hits)
        elif ex:
            done = 0
            for fa, fs, fn in funcs:
                if base <= fa < base + len(data):
                    code = data[fa - base:fa - base + fs]; words += len(code) // 4; done += 1
                    for adr, p, w, r in scan(code, fa):
                        print('   %08x: %08x then %08x  uses $%d   %s+0x%x' % (adr, p, w, r, fn, adr - fa)); total += 1
            if not done:
                hits = scan(data, base); words += len(data) // 4
                for adr, p, w, r in hits:
                    print('   %08x: %08x then %08x  uses $%d   %s (no symbols: whole section)' % (adr, p, w, r, name))
                total += len(hits)
    print('%s: %d words checked, %d load-delay hazards' % (a[0], words, total))

main()
