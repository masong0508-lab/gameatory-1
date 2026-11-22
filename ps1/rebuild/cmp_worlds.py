#!/usr/bin/env python3
"""cmp_worlds.py ROM_A ROM_B [ROM_C ...]: compare the 11 SFW4 world blobs of merged GBA cartridges (read-only).
Same blob finder as ps1 tools7/dumpworld.py (worlds_in_rom + blob_at, scan by magic)."""
import sys, struct, hashlib
N, NSEC, NWORLD = 128, 17, 11
def blob_at(rom, o):
    assert rom[o:o+4] == b'SFW4'
    first = struct.unpack_from('<I', rom, o+36)[0]; nsec = (first-36)//4; assert nsec == NSEC
    swim = struct.unpack_from('<I', rom, o+36+4*(nsec-1))[0]; nlad = struct.unpack_from('<H', rom, o+swim+N*N)[0]
    return bytes(rom[o:o+swim+N*N+4+8*nlad])
def worlds(rom):
    scan, o = [], rom.find(b'SFW4', 0x800000)
    while o >= 0:
        if o % 4 == 0 and struct.unpack_from('<I', rom, o+36)[0] == 36+4*NSEC: scan.append(o)
        o = rom.find(b'SFW4', o+4)
    assert len(scan) == NWORLD, len(scan); return scan
roms = [open(p,'rb').read() for p in sys.argv[1:]]
bl = [[blob_at(r, o) for o in worlds(r)] for r in roms]
for p, r, b in zip(sys.argv[1:], roms, bl): print('%-28s %9d bytes rom, worlds total %d bytes at 0x%08x' % (p.split('/')[-1], len(r), sum(map(len, b)), 0x08000000+worlds(r)[0]))
same_all = [True]*len(roms)
for m in range(NWORLD):
    row = []
    for i, b in enumerate(bl):
        h = hashlib.sha256(b[m]).hexdigest()[:12]; eq = b[m] == bl[0][m]; same_all[i] &= eq
        row.append('%7d %s %s' % (len(b[m]), h, 'same' if eq else 'DIFF'))
    print('map %2d  ' % m + '  |  '.join(row))
for p, s in zip(sys.argv[1:], same_all): print('%-28s all 11 worlds identical to the first ROM: %s' % (p.split('/')[-1], s))
