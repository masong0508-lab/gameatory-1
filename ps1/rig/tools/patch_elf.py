#!/usr/bin/env python3
"""patch_elf.py --elf IN.elf --patches P.json --out OUT.elf: copy of an ELF with the same instruction words replaced that
tools/patch_disc.py replaced in the boot executable of a TEST-ONLY disc copy, so that tools comparing the symbol file with the
PSX.EXE on the disc (ps1game.py: syms_match_disc) accept it.  Patch list: {patches: [{addr, old, new}]} or a plain list.
Every old word is verified.  The input file is not modified."""
import argparse
import json
import struct

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--elf', required=True)
ap.add_argument('--patches', required=True)
ap.add_argument('--out', required=True)
a = ap.parse_args()
d = bytearray(open(a.elf, 'rb').read())
assert d[:4] == b'\x7fELF', 'not an ELF'
phoff, = struct.unpack_from('<I', d, 0x1c)
phentsize, phnum = struct.unpack_from('<HH', d, 0x2a)
segs = []
for i in range(phnum):
    p_type, p_off, p_va, p_pa, p_fsz, p_msz = struct.unpack_from('<6I', d, phoff + i * phentsize)
    if p_type == 1 and p_fsz:
        segs.append((p_va, p_off, p_fsz))
P = json.load(open(a.patches))
P = P['patches'] if isinstance(P, dict) else P
n = 0
for p in P:
    for va, off, fsz in segs:
        if va <= p['addr'] < va + fsz:
            o = off + p['addr'] - va
            old, = struct.unpack_from('<I', d, o)
            assert old == p['old'], 'word at %08x is %08x, patch list expects %08x' % (p['addr'], old, p['old'])
            struct.pack_into('<I', d, o, p['new'])
            n += 1
            break
    else:
        raise SystemExit('address %08x is in no loadable segment' % p['addr'])
open(a.out, 'wb').write(d)
print('%s: %d words replaced -> %s' % (a.elf, n, a.out))
