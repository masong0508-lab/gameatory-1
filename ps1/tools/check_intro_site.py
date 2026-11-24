#!/usr/bin/env python3
"""Build-time check of the words the intro fix patches or relies on (ps1rt/interp_glue.h, intro_fix_init).

The ZOO-logo join point 0x080234be is a prune.py stub in the current translation.  At boot the runtime rewrites the one
translated call site of that stub ("ori $25,$0,ID; j RT_STUB; nop" in the hot blob) into a jump to RT_MISS, and points the
hash slots of IWRAM overlay-area keys at a miss thunk while the film player is resident.  This script makes the same checks on
the linked ELF, so a translation that no longer has exactly that shape fails the disc build instead of booting into a loop:

  - RT_MISS (blob + 8) starts with "addu $24,$25,$0";
  - STUBTAB holds 0x080234be exactly once, with an id that fits an ori immediate;
  - the hot blob [blob + 0x400, HASH) holds exactly one "ori $25,$0,ID; j RT_STUB; nop";
  - rt_hash (RT_BX + 8) computes the key and the slot as hot_lookup() does and rt_found jumps to the host word of the slot;
  - 1..8 hash keys lie in the overlay area [0x03000d84, 0x03003b74).

Milestone B (merged Star-FlyBack ROM, tools12/build_msb.sh): with --merged the intro is translated (prune.py without id 3), so STUBTAB
must NOT hold 0x080234be and no stub call site of it may exist; the RT_MISS, rt_hash and overlay-key checks stay.

usage: check_intro_site.py [--merged] ELF      (exit 0 = all present, 1 = a check failed, 2 = the file cannot be read)
No game data is read or written: only the linked program."""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mips1_lint import elf_parse  # noqa: E402

BLOB = 0x80030000
INTRO_JOIN = 0x080234BE
OV_BASE, OV1_SIZE, OV_NSL = 0x03000D84, 0x2DF0, 8


def symbols(path: str) -> dict[str, int]:
    """Symbol values of a 32-bit little-endian ELF (all symbol types)."""
    data = open(path, 'rb').read()
    shoff, = struct.unpack_from('<I', data, 0x20)
    shentsize, shnum, _ = struct.unpack_from('<HHH', data, 0x2e)
    secs = [struct.unpack_from('<10I', data, shoff + i * shentsize) for i in range(shnum)]
    out = {}
    for sec in secs:
        if sec[1] != 2:
            continue
        strings = secs[sec[6]][4]
        for off in range(sec[4], sec[4] + sec[5], 16):
            nm, value = struct.unpack_from('<II', data, off)
            name = data[strings + nm:data.index(b'\0', strings + nm)].decode('latin1')
            if name:
                out[name] = value
    return out


def check(path: str, merged: bool = False) -> list[str]:
    sections, _ = elf_parse(path)
    sym = symbols(path)

    def word(addr: int) -> int:
        for _name, base, data, _x in sections:
            if base <= addr and addr + 4 <= base + len(data):
                return struct.unpack_from('<I', data, addr - base)[0]
        raise KeyError('address 0x%08x is not in a loaded section' % addr)

    errors = []
    try:
        hash_host, nslots = word(sym['HASH_HOST']), word(sym['HASH_NSLOTS'])
        rt_bx, rt_stub = word(sym['RT_BX_HOST']), word(sym['RT_STUB_HOST'])
        nstub, stubtab = word(sym['STUBTAB_N']), sym['STUBTAB']
    except KeyError as missing:
        return ['symbol or value missing: %s' % missing]
    if word(BLOB + 8) != 0x0320C021:
        errors.append('RT_MISS (0x%08x) does not start with addu $24,$25,$0: %08x' % (BLOB + 8, word(BLOB + 8)))
    ids = [word(stubtab + 8 * k + 4) for k in range(nstub) if word(stubtab + 8 * k) == INTRO_JOIN]
    if merged:
        if ids:
            errors.append('STUBTAB holds 0x%08x (ids %s): the merged build must translate the intro' % (INTRO_JOIN, ids))
        else:
            print('intro join 0x%08x translated (no stub)' % INTRO_JOIN)
    elif len(ids) != 1 or not 1 <= ids[0] <= 0xFFFF:
        errors.append('STUBTAB holds 0x%08x %d times (ids %s), expected once' % (INTRO_JOIN, len(ids), ids))
    else:
        jst = 0x08000000 | ((rt_stub >> 2) & 0x03FFFFFF)
        sites = [a for a in range(BLOB + 0x400, hash_host - 8, 4)
                 if word(a) == (0x34190000 | ids[0]) and word(a + 4) == jst and word(a + 8) == 0]
        if len(sites) != 1:
            errors.append('%d stub call sites "ori $25,$0,%d; j RT_STUB; nop" in the hot blob, expected exactly 1 (%s)'
                          % (len(sites), ids[0], ' '.join('%08x' % a for a in sites[:8])))
        else:
            print('intro join stub id %d, call site 0x%08x' % (ids[0], sites[0]))
    if nslots & (nslots - 1) or not 0 < nslots <= 0x10000:
        errors.append('HASH_NSLOTS %d is not a power of two' % nslots)
    expect = {0: None, 1: 0, 2: 0x00190842, 3: 0x0001C040, 4: 0x000112C2, 5: 0x00220826, 6: 0x30210000 | ((nslots - 1) & 0xFFFF),
              7: 0x000108C0, 8: 0x3C020000 | (hash_host >> 16), 9: 0x34420000 | (hash_host & 0xFFFF), 10: 0x00220821,
              11: 0x8C220000, 20: 0x8C390004, 22: 0x03200008}
    for i, want in expect.items():
        got = word(rt_bx + 4 * i)
        ok = (got >> 16) == 0x0720 if i == 0 else got == want
        if not ok:
            errors.append('RT_BX+%d (0x%08x): %08x, expected %s' % (4 * i, rt_bx + 4 * i, got, 'bltz $25' if i == 0 else '%08x' % want))
    if (word(rt_bx + 52) >> 16) != 0x1058:
        errors.append('rt_hash does not compare the slot key with $24 at RT_BX+52: %08x' % word(rt_bx + 52))
    keys = [word(hash_host + 8 * i) for i in range(nslots) if 0 <= word(hash_host + 8 * i) - OV_BASE < OV1_SIZE]
    if not 1 <= len(keys) <= OV_NSL:
        errors.append('%d hash keys in the overlay area, expected 1..%d' % (len(keys), OV_NSL))
    else:
        print('overlay-area hash keys: %s' % ' '.join('%08x' % k for k in keys))
    return errors


def main(argv: list[str]) -> int:
    merged = '--merged' in argv[1:]
    argv = [a for a in argv if a != '--merged']
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        errors = check(argv[1], merged)
    except (OSError, ValueError, struct.error, IndexError) as error:
        print('%s: cannot be checked: %s' % (argv[1], error), file=sys.stderr)
        return 2
    for line in errors:
        print('INTRO FIX CHECK FAILED: ' + line, file=sys.stderr)
    if errors:
        return 1
    print('%s: the words the intro fix patches and relies on are all present' % argv[1])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
