#!/usr/bin/env python3
"""Milestone B stage B2 (PS1): pin Stunt Fox's variables to their GBA addresses (README.md: "B2 data").

usage: pin.py IN.ll OUT.ll FILE.c GBA_SYMS.txt [REPORT]
  GBA_SYMS.txt  natbuild.py's table of the GBA build's RAM objects: "file name address size bind" per line (file is '-' for a global)
Stunt Fox's assembly hooks stay interpreted from the ROM and name its variables by their GBA addresses (literal pools), Payback's RAM keeps
pointers into them, and the lockstep check compares them by address with mGBA: so every variable of the native module sits at the host image
of its GBA address.  Each variable that the GBA build has (same file and name: gcc and clang name and split function statics and scalarised
aggregates alike, "f.v", "v.0") gets the section .data.sfv.ADDR or .bss.sfv.ADDR (place.py puts it there) and goes into @llvm.used, so
that the whole-module optimiser neither drops nor reshapes it (the assembly may read or write it).  A variable the GBA build split
(v.0, v.1, ... next to each other) and clang did not lands on v.0.  Constants stay native (read-only data: the ROM keeps its own copy).
Variables with no GBA twin are listed (REPORT) and stay where the native linker puts them."""
import re
import sys


def main():
    src, dst, cfile, syms = sys.argv[1:5]
    rep = sys.argv[5] if len(sys.argv) > 5 else None
    loc, glo = {}, {}
    for line in open(syms):
        f, n, a, sz, b = line.split()
        (glo if f == '-' else loc.setdefault(f, {}))[n] = (int(a, 16), int(sz), b)
    mine = loc.get(cfile, {})
    text = open(src).read()
    out, used, miss, pinned = [], [], [], 0
    gre = re.compile(r'^@([\w.$]+) = ((?:[\w]+ )*?)(global|constant) (.*?)(, align (\d+))?$')
    for line in text.split('\n'):
        m = gre.match(line)
        if m and m.group(3) == 'global' and 'external' not in m.group(2):
            n = m.group(1)
            hit = mine.get(n) or (glo.get(n) if 'internal' not in m.group(2) and 'private' not in m.group(2) else None)
            if hit:
                a, sz, b = hit
                kind = b                # the GBA section: .data's variables keep their place in the initial image, the rest are zero
                if kind == 'bss' and not ('zeroinitializer' in m.group(4) or re.match(r'\S+ (null|0|false)$', m.group(4).split(', section')[0])):
                    raise SystemExit('pin.py: %s %s: initialised natively, zero on the GBA' % (cfile, n))
                sec = '.%s.sfv.%08x' % (kind, a)
                al = a & -a if a else 4096          # never more aligned than the GBA address (lld would move it)
                line, k = re.subn(r', section "[^"]*"', ', section "%s"' % sec, line)
                if not k:
                    am = re.search(r', align \d+', line)
                    line = line[:am.start()] + ', section "%s"' % sec + line[am.start():] if am else line + ', section "%s"' % sec
                line = re.sub(r', align (\d+)', lambda q: ', align %d' % min(int(q.group(1)), al), line)
                line = line.replace(' unnamed_addr ', ' ').replace(' local_unnamed_addr ', ' ')
                used.append(n)
                pinned += 1
            else:
                miss.append(n)
        out.append(line)
    text = '\n'.join(out)
    if used:
        arr = ', '.join('ptr @%s' % n for n in used)
        um = re.search(r'^@llvm\.used = appending global \[(\d+) x ptr\] \[(.*)\], section "llvm.metadata"$', text, re.M)
        if um:
            k = int(um.group(1)) + len(used)
            text = text[:um.start()] + '@llvm.used = appending global [%d x ptr] [%s, %s], section "llvm.metadata"' % (k, um.group(2), arr) + text[um.end():]
        else:
            text += '\n@llvm.used = appending global [%d x ptr] [%s], section "llvm.metadata"\n' % (len(used), arr)
    open(dst, 'w').write(text)
    if rep:
        with open(rep, 'a') as f:
            f.write('%s pinned %d unpinned %s\n' % (cfile, pinned, ' '.join(miss) or '-'))


if __name__ == '__main__':
    main()
