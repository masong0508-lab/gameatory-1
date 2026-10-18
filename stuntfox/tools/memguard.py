#!/usr/bin/env python3
"""Fail the build when our memory lands on Payback's.

Reads memmap.txt (forbidden ranges, in EWRAM and IWRAM), the linked ELF's allocated sections and
the RAM regions of merge.ld, and exits non-zero if any of them overlap a forbidden range. A range
that ends in "[may share: REGION ...]" may lie under those merge.ld regions and the sections inside
them (memmap.txt says why), and under nothing else. Also prints the space left in keep.

    python3 tools/memguard.py build/merge/stuntfox-merge.elf src/merge.ld memmap.txt
"""
import re
import subprocess
import sys


# IWRAM regions lent to us for the frame and put back from a copy saved as we take them (merge.c
# hot_install): Payback's own words under them come back as they were. The other regions are put
# back from Payback's ROM image, or stay ours between frames, so a range marked 'stay' in
# memmap.txt is checked against those.
SAVED = ('hot3', 'hot6b')


def ranges(path):
    out = []
    for line in open(path):
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        span, _, what = line.partition(' ')
        a, b = span.split('-')
        what = what.strip()
        stay = what.startswith('stay ')
        if stay:
            what = what[5:]
        m = re.search(r'\[may share: ([\w ]+)\]$', what)
        share = set(m.group(1).split()) if m else set()
        out.append((int(a, 16), int(b, 16), what[:m.start()].strip() if m else what, stay, share))
    return out


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


def main(elf, ld, memmap):
    bad = ranges(memmap)
    regs, byname = regions(ld)
    ours = sections(elf) + regs
    fail = 0
    for a, b, what in ours:
        for fa, fb, fwhat, stay, share in bad:
            if stay and what in [k + r for r in SAVED for k in ('region ', 'section .')]:
                continue
            if any(byname[r][0] <= a and b <= byname[r][1] for r in share if r in byname):
                continue                       # (under a region it may share)
            if a < fb and fa < b:
                print('memguard: %s 0x%08x-0x%08x overlaps Payback\'s %s (0x%08x-0x%08x)'
                      % (what, a, b, fwhat, fa, fb))
                fail = 1
    if 'keep' in byname:
        top = max((b for a, b, w in ours if w.startswith('section ') and byname['keep'][0] <= a < byname['keep'][1]),
                  default=byname['keep'][0])
        print('memguard: keep has %d bytes free' % (byname['keep'][1] - top))
    if fail:
        sys.exit('memguard: memory map overlaps Payback (see memmap.txt)')
    print('memguard: OK, %d of our ranges clear of %d Payback ranges' % (len(ours), len(bad)))


if __name__ == '__main__':
    main(*sys.argv[1:4])
