"""ROM-free regression checks for the Payback grid codec and patch allocator."""
import os
import random
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from paybackmod import mapcodec
from paybackmod.rom import PaybackRom


class MapCodecTest(unittest.TestCase):
    def test_grid_roundtrip_without_original_rom(self):
        rng = random.Random(0x5F0)
        grid = [rng.randrange(4096) for _ in range(128 * 128)]
        stream = mapcodec.encode(grid)
        offset = mapcodec.LEVEL_TABLE + 64
        rom = bytearray(offset + len(stream))
        struct.pack_into('<I', rom, mapcodec.LEVEL_TABLE, mapcodec.GBA + offset)
        rom[offset:offset + len(stream)] = stream
        decoded, consumed = mapcodec.decode(rom, 0)
        expected = [mapcodec.COLUMN_BASE + 60 * col for col in grid]
        self.assertEqual(decoded, expected)
        self.assertLessEqual(consumed, len(stream))

    def test_reject_incomplete_grid(self):
        with self.assertRaisesRegex(ValueError, 'expected 16384'):
            mapcodec.encode([1, 2, 3])

    def test_reject_out_of_range_column_index(self):
        for invalid in (-1, 32768, None):
            with self.subTest(invalid=invalid):
                cells = [0] * (128 * 128)
                cells[0] = invalid
                with self.assertRaisesRegex(ValueError, 'invalid column index'):
                    mapcodec.encode(cells)


class RomSafetyTest(unittest.TestCase):
    def test_wrong_length_rom_is_clear_error(self):
        with self.assertRaisesRegex(ValueError, '8 MiB'):
            PaybackRom(b'not a ROM', check=False)

    def test_allocation_stays_inside_fixed_capacity(self):
        rom = PaybackRom.__new__(PaybackRom)
        rom.d = bytearray(16)
        rom.free = 14
        with self.assertRaisesRegex(ValueError, '16 MiB ROM capacity'):
            rom.alloc(b'overflow')
        self.assertEqual(len(rom.d), 16)
        self.assertEqual(rom.free, 14)
        rom.free = 5
        self.assertEqual(rom.alloc(b'ok'), 8)
        self.assertEqual(rom.d[8:10], b'ok')
        with self.assertRaisesRegex(ValueError, 'alignment'):
            rom.alloc(b'', align=3)

    def test_out_of_bounds_paint_is_rejected(self):
        rom = PaybackRom.__new__(PaybackRom)
        rom.painted = {0: [0] * (128 * 128)}
        for point in ((-1, 0), (0, 128), (128, 5)):
            with self.subTest(point=point):
                with self.assertRaisesRegex(ValueError, 'outside the 128x128 map'):
                    rom.paint(0, {point: bytes(60)})


if __name__ == '__main__':
    unittest.main()
