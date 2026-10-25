#!/usr/bin/env python3
"""Fail the build when our memory lands on Payback's.

Reads memmap.txt (ranges of Payback's memory, in EWRAM and IWRAM), the linked ELF's allocated sections
and the RAM regions of merge.ld, and exits non-zero if any of them breaks a rule. A line is
"[KIND] start-end what"; KIND (FORBID when left out) says what the range is:

    FORBID   Payback's: nothing of ours may overlap it. One that ends in "[may share: REGION ...]" may lie
             under those merge.ld regions and the sections inside them (memmap.txt says why), and under
             nothing else; one that starts with "stay " lets the IWRAM regions that are put back (SAVED) lie
             under it
    RESERVE  kept free for stage 3 (big map streaming): as FORBID
    SCRATCH  free in play but unwatched in the long run: per-frame data only (.scratch, .scratch2, the pool),
             nothing that has to live from one frame to the next
    KEEP     our persistent region, by its merge.ld name, "reserve=N margin=N": the sections .canary .data
             .bss .noinit (and .radio, in its own region) must fit in it and leave N + N bytes free

It also prints the space left in keep.

    python3 tools/memguard.py build/merge/stuntfox-merge.elf src/merge.ld memmap.txt
"""
import re
import subprocess
import sys


# IWRAM regions lent to us for the frame and put back from a copy saved as we take them (merge.c
# hot_install): Payback's own words under them come back as they were. The other regions are put
# back from Payback's ROM image, or stay ours between frames, so a range marked 'stay' in
# memmap.txt is checked against those.
SAVED = ('hot6b',)
PER_FRAME = ('scr', 'scr2', 'poola')           # regions, and the sections that go in them, that nothing outlives a frame in
KINDS = ('FORBID', 'RESERVE', 'SCRATCH', 'KEEP')


def ranges(path):
    """(start, end, what, stay, share, kind) of every line but KEEP's; and KEEP's (region, reserve, margin)."""
    out, keep = [], None
    for line in open(path):
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        kind = 'FORBID'
        if line.split()[0] in KINDS:
            kind, _, line = line.partition(' ')
            line = line.strip()
        if kind == 'KEEP':
            f = line.split()
            keep = (f[0], int(dict(x.split('=') for x in f[1:])['reserve']), int(dict(x.split('=') for x in f[1:])['margin']))
            continue
        span, _, what = line.partition(' ')
        a, b = span.split('-')
        what = what.strip()
        stay = what.startswith('stay ')
        if stay:
            what = what[5:]
        m = re.search(r'\[may share: ([\w ]+)\]$', what)
        share = set(m.group(1).split()) if m else set()
        out.append((int(a, 16), int(b, 16), what[:m.start()].strip() if m else what, stay, share, kind))
    return out, keep


def ram(addr):
    return 0x02000000 <= addr < 0x02040000 or 0x03000000 <= addr < 0x03008000


def sections(elf):
    text = subprocess.run(['llvm-readelf', '-S', '-W', elf], capture_output=True, text=True,
                          check=True).stdout
    out = []
    for m in re.finditer(r'\]\s+(\S+)\s+\S+\s+([0-9a-f]{8})\s+[0-9a-f]+\s+([0-9a-f]+)\s+\S+\s+(\S*)', text):
        name, addr, size, flags = m.group(1), int(m.group(2), 16), int(m.group(3), 16), m.group(4)
        if 'A' in flags and size and ram(addr):
            out.append((addr, addr + size, 'section ' + name))
    return out


def regions(ld):
    out = []
    for m in re.finditer(r'(\w+)\s*\(\w+\)\s*:\s*ORIGIN\s*=\s*(0x[0-9a-fA-F]+)\s*,\s*LENGTH\s*=\s*(0x[0-9a-fA-F]+)',
                         open(ld).read()):
        a = int(m.group(2), 16)
        if ram(a):
            out.append((a, a + int(m.group(3), 16), 'region ' + m.group(1)))
    return out, {m[2][7:]: m for m in out}


def per_frame(what):
    return what in ['region ' + r for r in PER_FRAME] or what in ('section .scratch', 'section .scratch2')


def check(elf, ld, memmap):
    """The report (a string) when the map is clear; SystemExit with what is wrong when it is not."""
    bad, keep = ranges(memmap)
    regs, byname = regions(ld)
    ours = sections(elf) + regs
    out, fail = [], []
    for a, b, what in ours:
        for fa, fb, fwhat, stay, share, kind in bad:
            if a >= fb or fa >= b:
                continue
            if kind == 'SCRATCH':
                if not per_frame(what):
                    fail.append('memguard: %s 0x%08x-0x%08x is in the per-frame scratch %s (0x%08x-0x%08x): nothing '
                                'that lives from one frame to the next may be' % (what, a, b, fwhat, fa, fb))
                continue
            if stay and what in [k + r for r in SAVED for k in ('region ', 'section .')]:
                continue
            if any(byname[r][0] <= a and b <= byname[r][1] for r in share if r in byname):
                continue                       # (under a region it may share)
            fail.append('memguard: %s 0x%08x-0x%08x overlaps %s %s (0x%08x-0x%08x)'
                        % (what, a, b, 'the stage 3 reserve' if kind == 'RESERVE' else "Payback's", fwhat, fa, fb))
    if keep:
        name, reserve, margin = keep
        lo, hi = byname[name][0], byname[name][1]
        top = max((b for a, b, w in ours if w.startswith('section ') and lo <= a < hi), default=lo)
        free = hi - top
        out.append('memguard: keep has %d bytes free' % free)
        out.append('memguard: keep headroom %d bytes after the stage 3 reserve (%d) and the margin (%d)'
                   % (free - reserve - margin, reserve, margin))
        if free < reserve + margin:
            fail.append('memguard: keep has %d bytes free, short of the stage 3 reserve (%d) and margin (%d) by %d'
                        % (free, reserve, margin, reserve + margin - free))
        for a, b, w in ours:
            if w.startswith('section ') and w[9:] in ('canary', 'data', 'bss', 'noinit') and not (lo <= a and b <= hi):
                fail.append('memguard: %s 0x%08x-0x%08x is outside %s (0x%08x-0x%08x)' % (w, a, b, name, lo, hi))
    for r in ('scr', 'scr2'):
        used = max((b for a, b, w in ours if w == 'section .scratch' + ('2' if r == 'scr2' else '')), default=0)
        if r in byname and used:
            out.append('memguard: %s uses %d of %d bytes' % (r, used - byname[r][0], byname[r][1] - byname[r][0]))
    if fail:
        sys.exit('\n'.join(fail) + '\nmemguard: memory map breaks memmap.txt')
    out.append('memguard: OK, %d of our ranges clear of %d Payback ranges' % (len(ours), len(bad)))
    return '\n'.join(out)


def main(elf, ld, memmap):
    print(check(elf, ld, memmap))


if __name__ == '__main__':
    main(*sys.argv[1:4])
