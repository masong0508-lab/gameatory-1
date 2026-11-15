#!/usr/bin/env python3
"""gbaprobe.py ROM ELF OUT.png: boot the GBA build to map 0 (libmgba harness in SP/work), then
  - compare Payback's live tile pointer table (0x02002c60, by tile id) with the ROM bank dumpworld.py reads,
  - compare the screen's BG palette with the ROM palette (red and blue swapped),
  - save a screenshot and print the camera (cam: pos, then right, up, forward rows, 1.14) for tools/viewcheck.py."""
import struct
import sys

SP = '/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad'
sys.path.insert(0, SP + '/work')
import scenes                      # noqa: E402
from emu import Emu                # noqa: E402

rom_path, elf, out = sys.argv[1:4]
e = Emu(rom_path, elf)
scenes.boot_to_level(e)
e.run(120, [])
rom = open(rom_path, 'rb').read()
BANK, IDS = 0x080ce0bc, 0x318
tab = struct.unpack('<%dI' % IDS, e.read(0x02002c60, 4 * IDS))
odd = []
for i, p in enumerate(tab):
    if p != BANK + i * 0x400:
        same = e.read(p, 0x400) == rom[BANK - 0x08000000 + i * 0x400:][:0x400]
        odd.append('id 0x%x -> 0x%08x (%s)' % (i, p, 'the same texels' if same else 'other texels'))
print('tile table: %d of %d ids point at bank + id * 0x400; the others: %s' % (IDS - len(odd), IDS, '; '.join(odd)))
pal = struct.unpack('<256H', e.read(0x05000000, 512))
rp = struct.unpack_from('<256H', rom, 0x6367a8)
sw = lambda c: (c >> 10 & 31) | (c & 0x3e0) | ((c & 31) << 10)
print('palette: %d of 256 screen colours are the ROM palette with red and blue swapped' % sum(a == sw(b) for a, b in zip(pal, rp)))
cam = e.S['cam']
print('cam', [e.s32(cam + 4 * k) for k in range(12)], 'DISPCNT 0x%04x' % e.r16(0x04000000))
e.screenshot(out)
