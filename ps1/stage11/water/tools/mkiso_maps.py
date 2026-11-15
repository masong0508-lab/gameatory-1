#!/usr/bin/env python3
"""mkiso_maps.py DIR OUT.iso: DIR holds SF5M.EXE, MAPS.BIN, SYSTEM.CNF.  Makes the ISO (genisoimage), finds MAPS.BIN's first sector in it and patches that LBA into the copy of the
EXE inside the ISO (the EXE carries the marker words 'SPAM' 'ABL1' at maps_lba; the EXE's size and place do not change)."""
import sys, struct, subprocess
d, out = sys.argv[1:3]
subprocess.run(['genisoimage', '-quiet', '-V', 'SF5M', '-sysid', 'PLAYSTATION', '-o', out, d], check=True)
iso = bytearray(open(out, 'rb').read())
maps = open(d + '/MAPS.BIN', 'rb').read(2048)
at = bytes(iso).find(maps)
assert at % 2048 == 0 and bytes(iso).find(maps, at + 1) < 0 or at % 2048 == 0, 'MAPS.BIN header not found'
lba = at // 2048
mk = struct.pack('<II', 0x4D415053, 0x31424C41); k = bytes(iso).find(mk)
assert k > 0 and bytes(iso).find(mk, k + 1) < 0, 'marker'
iso[k:k + 4] = struct.pack('<I', lba)
open(out, 'wb').write(iso); print('MAPS.BIN at LBA', lba, 'iso', len(iso))
