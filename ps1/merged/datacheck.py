#!/usr/bin/env python3
"""Milestone B stage B2 (PS1): build check of native Stunt Fox's .data initial image (README.md: "Data").

usage: datacheck.py PAYBACK.elf PAYBACK.bin NATDIR [GUEST.map]
  PAYBACK.elf/.bin  the linked PS1 program and its flat image (llvm-objcopy -O binary, first byte at 0x80010000)
  NATDIR            natbuild.py's output (gba_data.bin / gba_data.txt: the GBA build's .data image; gba_ram.txt: its variables)
merge.c start() copies __data_start..__data_end from __data_lma at every level start, as on the GBA.  The PS1 image at sfn___data_lma must hold
the GBA's initial value of every .data variable: the native files' (pin.py) and the interpreted files' (place.py fills those from the GBA build).
Any byte that differs fails the build, named by the GBA variable that holds it.  Also prints the free bytes of R1 (up to the native stack).
GUEST.map (the translation's guest -> host map): merge.c sf_pick_rand tells its two callers in Payback's chooser apart by
__builtin_return_address, which is the guest lr of the entry (sfglue.h).  Translated code would hand it a host return address there, so the
two call sites (PICK_X - 4, PICK_Y - 4) must lie in code that the interpreter runs: cold groups from SF_NAT_LO up.  The build fails otherwise."""
import os
import re
import subprocess
import sys

BASE = 0x80010000
STACK_LO = 0x80119000


def main():
    elf, binp, nat = sys.argv[1:4]
    syms = {}
    for line in subprocess.run(['llvm-nm', elf], capture_output=True, text=True, check=True).stdout.splitlines():
        p = line.split()
        if len(p) == 3:
            syms[p[2]] = int(p[0], 16)
    d0, size = (int(x, 16) for x in open(nat + '/gba_data.txt').read().split())
    want = open(nat + '/gba_data.bin', 'rb').read()
    assert len(want) == size
    lma = syms['sfn___data_lma']
    img = open(binp, 'rb').read()[lma - BASE:lma - BASE + size]
    names = []
    for line in open(nat + '/gba_ram.txt'):
        f, n, ad, sz, k = line.split()
        if k == 'data':
            names.append((int(ad, 16), int(sz), n if f == '-' else '%s:%s' % (f, n)))
    def who(a):
        return ','.join(n for ad, sz, n in names if ad <= a < ad + sz) or '(padding)'
    bad = [i for i in range(size) if i >= len(img) or img[i] != want[i]]
    free = STACK_LO - (lma + size)
    print('datacheck: .data image at 0x%08x (%d B) vs the GBA build: %d bytes differ; R1 free below the native stack: %d B'
          % (lma, size, len(bad), free))
    if bad:
        for i in bad[:64]:
            print('  0x%08x %s: PS1 %s GBA %02x' % (d0 + i, who(d0 + i), '%02x' % img[i] if i < len(img) else '--', want[i]))
        raise SystemExit('datacheck: the native .data image differs from the GBA build')
    if len(sys.argv) > 4:
        hmap = {}
        for line in open(sys.argv[4]):
            p = line.split()
            if len(p) == 2:
                hmap[int(p[0], 16)] = int(p[1], 16)
        nat_lo = int(re.search(r'SF_NAT_LO 0x([0-9a-f]+)', open(os.path.join(nat, 'sfnat_place.h')).read()).group(1), 16)
        src = open(os.path.join(nat, 'b', 'src', 'merge.c')).read()
        for k in ('PICK_X', 'PICK_Y'):
            site = (int(re.search(r'#define %s (0x[0-9a-f]+)' % k, src).group(1), 16) | 0x08000000) - 4
            h = hmap.get(site)
            if h is not None and h < nat_lo:
                raise SystemExit('datacheck: the chooser call %s at 0x%08x is translated (host 0x%08x below SF_NAT_LO 0x%08x): '
                                 'sf_pick_rand would see a host return address' % (k, site, h, nat_lo))
            print('datacheck: chooser call %s at 0x%08x: %s' % (k, site, 'interpreted (host 0x%08x, cold group from SF_NAT_LO 0x%08x)'
                                                                % (h, nat_lo) if h is not None else 'not translated (interpreted)'))


if __name__ == '__main__':
    main()
