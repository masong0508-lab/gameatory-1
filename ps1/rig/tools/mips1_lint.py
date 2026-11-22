#!/usr/bin/env python3
"""mips1_lint.py: list instruction words that are not valid on the PlayStation's R3000A (MIPS I + COP0 + GTE).

    mips1_lint.py payback.elf                 every executable section of the ELF, with the enclosing symbol
    mips1_lint.py --raw FILE --base 0x80010000 [--start OFF --size N]     a raw code image (for example a cold overlay group)

clang emits `teq $divisor,$zero,7` after every div/divu unless -mno-check-zero-division is given; teq is MIPS II.
A dynarec that ignores unknown opcodes (pcsx_rearmed's lightrec, PCSXR) runs such code, a real R3000A (and an emulator that
models it) raises a Reserved Instruction exception.  Data inside code sections can give false hits: check the listing.
"""
import struct
import sys

SPECIAL_OK = {0x00, 0x02, 0x03, 0x04, 0x06, 0x07, 0x08, 0x09, 0x0c, 0x0d, 0x10, 0x11, 0x12, 0x13, 0x18, 0x19, 0x1a, 0x1b,
              0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x2a, 0x2b}
REGIMM_OK = {0x00, 0x01, 0x10, 0x11}
OP_OK = {0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
         0x28, 0x29, 0x2a, 0x2b, 0x2e, 0x32, 0x3a}
SPECIAL_NAMES = {0x0a: 'movz', 0x0b: 'movn', 0x0f: 'sync', 0x30: 'tge', 0x31: 'tgeu', 0x32: 'tlt', 0x33: 'tltu', 0x34: 'teq', 0x36: 'tne',
                 0x01: 'movf/movt', 0x14: 'dsllv', 0x1c: 'dmult'}
OP_NAMES = {0x14: 'beql', 0x15: 'bnel', 0x16: 'blezl', 0x17: 'bgtzl', 0x1c: 'special2 (mul/clz/madd)', 0x1f: 'special3', 0x2f: 'cache',
            0x30: 'll', 0x38: 'sc', 0x11: 'cop1 (no FPU)', 0x13: 'cop3', 0x31: 'lwc1', 0x39: 'swc1', 0x33: 'pref/lwc3', 0x1a: 'ldl', 0x1b: 'ldr'}


def bad(w):
    """None when the word is a valid R3000A instruction, else a short reason."""
    op = w >> 26
    if op == 0:
        f = w & 0x3f
        return None if f in SPECIAL_OK else 'SPECIAL funct 0x%02x %s' % (f, SPECIAL_NAMES.get(f, ''))
    if op == 1:
        rt = (w >> 16) & 0x1f
        return None if rt in REGIMM_OK else 'REGIMM rt 0x%02x (branch-likely / trap-immediate)' % rt
    if op == 0x10:      # COP0: mfc0 mtc0 rfe (tlb ops are harmless decodes on the PS1? no TLB: list them)
        rs = (w >> 21) & 0x1f
        if rs in (0, 4):
            return None
        if rs == 0x10 and (w & 0x3f) == 0x10:
            return None
        return 'COP0 rs 0x%02x funct 0x%02x' % (rs, w & 0x3f)
    if op == 0x12:      # COP2 = GTE: mfc2 cfc2 mtc2 ctc2 + commands
        rs = (w >> 21) & 0x1f
        return None if rs in (0, 2, 4, 6) or (rs & 0x10) else 'COP2 rs 0x%02x' % rs
    if op in OP_OK:
        return None
    return 'opcode 0x%02x %s' % (op, OP_NAMES.get(op, ''))


def scan(data, base, syms=None):
    out = []
    names = sorted((a, n) for n, a in (syms or {}).items())
    for o in range(0, len(data) - 3, 4):
        w, = struct.unpack_from('<I', data, o)
        r = bad(w)
        if r:
            a = base + o
            fn = ''
            lo, hi = 0, len(names)
            while lo < hi:
                m = (lo + hi) // 2
                if names[m][0] <= a:
                    lo = m + 1
                else:
                    hi = m
            if lo:
                fn = '%s+0x%x' % (names[lo - 1][1], a - names[lo - 1][0])
            out.append((a, w, r, fn))
    return out


def elf_parse(path):
    """(sections [(name, addr, bytes, exec)], functions [(addr, size, name)]) of a 32-bit little-endian ELF."""
    d = open(path, 'rb').read()
    shoff, = struct.unpack_from('<I', d, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x2e)
    secs = [struct.unpack_from('<10I', d, shoff + i * shentsize) for i in range(shnum)]
    stro = secs[shstrndx][4]
    out, funcs = [], []
    for s in secs:
        name = d[stro + s[0]:d.index(b'\0', stro + s[0])].decode()
        if s[1] == 1 and s[5]:
            out.append((name, s[3], d[s[4]:s[4] + s[5]], bool(s[2] & 4)))
        if s[1] == 2:
            so = secs[s[6]][4]
            for o in range(s[4], s[4] + s[5], 16):
                nm, val, size, info, other, shndx = struct.unpack_from('<IIIBBH', d, o)
                if (info & 15) == 2 and size:
                    funcs.append((val, size, d[so + nm:d.index(b'\0', so + nm)].decode('latin1')))
    return out, sorted(funcs)


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('file')
    ap.add_argument('--raw', action='store_true', help='FILE is a raw code image')
    ap.add_argument('--base', default='0x80010000')
    ap.add_argument('--start', default='0')
    ap.add_argument('--size', default=None)
    ap.add_argument('--section', action='append', default=[], help='ELF: also scan this whole section as code (for example .blob)')
    ap.add_argument('--max', type=int, default=40)
    a = ap.parse_args()
    total = 0
    if a.raw:
        d = open(a.file, 'rb').read()
        s = int(a.start, 0)
        d = d[s:s + int(a.size, 0)] if a.size else d[s:]
        hits = scan(d, int(a.base, 0))
        print('%s: %d words, %d not valid on the R3000A (raw scan: data in the image gives false hits)' % (a.file, len(d) // 4, len(hits)))
        kinds = {}
        for h in hits:
            kinds[h[2]] = kinds.get(h[2], 0) + 1
        for k, n in sorted(kinds.items(), key=lambda x: -x[1])[:12]:
            print('   %6d x %s' % (n, k))
        for adr, w, r, fn in hits[:a.max]:
            print('   %08x: %08x  %s' % (adr, w, r))
        return 1 if hits else 0
    secs, funcs = elf_parse(a.file)
    nwords = 0
    for name, base, data, ex in secs:
        if not ex and name not in a.section:
            continue
        if name in a.section:
            hits = scan(data, base)
            nwords += len(data) // 4
            for adr, w, r, fn in hits:
                print('   %08x: %08x  %-34s %s (whole section)' % (adr, w, r, name))
            total += len(hits)
            continue
        for fa, fs, fn in funcs:
            if base <= fa < base + len(data):
                code = data[fa - base:fa - base + fs]
                nwords += len(code) // 4
                for adr, w, r, _ in scan(code, fa):
                    print('   %08x: %08x  %-34s %s+0x%x' % (adr, w, r, fn, adr - fa))
                    total += 1
    print('%s: %d instruction words inside function symbols checked, %d not valid on the R3000A' % (a.file, nwords, total))
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
