#!/usr/bin/env python3
"""Independently apply BPS and verify the integrated ROM's maps and runtime.

Usage: python3 harness/verify_artifact.py ORIGINAL.gba MOD.gba MOD.bps
No original game data is bundled or sent anywhere by this check.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from paybackmod.mapcodec import GBA, COLUMN_BASE, decode
from paybackmod.rom import PAYBACK_EU_SHA1, MAX_COLUMNS, NEW_BASE, validate_runtime
from paybackmod.stuntpark import build as park
from verify_bps import apply


def verify(source, data, patch):
    assert len(source) == 0x800000 and len(data) == 0x1000000
    assert hashlib.sha1(source).hexdigest() == PAYBACK_EU_SHA1
    applied, operations = apply(source, patch)
    assert applied == data, 'independent BPS output differs from the delivered ROM'
    assert data[0xa0:0xc0] == source[0xa0:0xc0], 'GBA metadata changed'
    assert (sum(data[0xa0:0xbe]) + 0x19) & 255 == 0, 'invalid GBA header checksum'
    syms = json.loads((ROOT / 'paybackmod/editor.json').read_text())
    runtime = (ROOT / 'paybackmod/editor.bin').read_bytes()
    validate_runtime(runtime, syms, source_root=ROOT)
    assert data[0x1b0000:0x1b0000+len(runtime)] == runtime

    decoded, _ = decode(data, 0)
    original, _ = decode(source, 0)
    changed = {(x, y) for x in range(128) for y in range(128)
               if decoded[x*128+y] != original[x*128+y]}
    assert changed == set(park()), 'encoded level changes must be exactly the 800-cell stadium'
    table = struct.unpack_from('<85I', data, syms['cols'] - GBA)
    addresses = struct.unpack_from('<3I', data, syms['maps'] - GBA)

    def valid_pointer(p):
        return GBA+NEW_BASE <= p < GBA+NEW_BASE+60*MAX_COLUMNS and (p-GBA-NEW_BASE) % 60 == 0

    def column(p):
        return data[p-GBA:p-GBA+60]

    assert all(valid_pointer(p) for p in table)
    grids = []
    for address in addresses:
        assert GBA+NEW_BASE+60*MAX_COLUMNS <= address <= GBA+len(data)-65536
        values = struct.unpack_from('<16384I', data, address-GBA)
        assert all(valid_pointer(p) for p in values)
        grids.append(values)
    space, city, neo = grids
    assert city == tuple(GBA+NEW_BASE+60*((p-COLUMN_BASE)//60) for p in decoded)
    assert len({space[0], city[0], neo[0]}) == 3, 'reload markers are not distinct'
    assert column(space[0]) == column(city[0]) == column(neo[0]), 'marker changed visible geometry'
    neo_changed = 0
    roads = 0
    for i, (n, c) in enumerate(zip(neo, city)):
        original_col, neo_col = column(c), column(n)
        neo_changed += original_col != neo_col
        if original_col[3] & 15:
            roads += 1
            assert original_col == neo_col, f'road geometry changed at {i//128},{i%128}'
    assert neo_changed > 5000
    for x in range(40, 80):
        for y in range(24, 44):
            i = x*128+y
            assert column(neo[i]) == column(city[i]), 'Neo city overwrote the stadium'
    for i in range(128):
        for x, y in ((i, 0), (i, 127), (0, i), (127, i)):
            k = x*128+y
            assert column(space[k]) == column(city[k]), 'space perimeter changed'
    assert city[53*128+37] == table[81] and city[49*128+37] == table[82]
    first, second = struct.unpack_from('<HH', data, 0xe9a8)
    assert first >> 11 == 0x1e and second >> 11 == 0x1f
    delta = ((first & 0x7ff) << 12) | ((second & 0x7ff) << 1)
    if delta & (1 << 22):
        delta -= 1 << 23
    assert GBA+0xe9ac+delta == (syms['hook'] & ~1)
    return {'passed': True, 'rom_sha256': hashlib.sha256(data).hexdigest(),
            'bps_sha256': hashlib.sha256(patch).hexdigest(), 'stadium_cells': len(changed),
            'neo_changed_geometry_cells': neo_changed, 'preserved_road_cells': roads,
            'runtime_bytes': len(runtime), 'independent_bps_operation_counts': operations,
            'reload_marker_pointers': {'space': space[0], 'city': city[0], 'neo': neo[0]}}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('original')
    ap.add_argument('modded')
    ap.add_argument('patch')
    ap.add_argument('--report')
    args = ap.parse_args()
    result = verify(*(Path(p).read_bytes() for p in (args.original, args.modded, args.patch)))
    text = json.dumps(result, indent=2, sort_keys=True)+'\n'
    if args.report:
        Path(args.report).write_text(text)
    print(text)
