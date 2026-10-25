"""The whole Killing Zone against the player's ROM: the vocabulary, a build, its tables, its picture, its world, and a
build that must be refused."""
import copy
import json
import struct
import unittest

import common
import arenacheck as AC
import minimap as MM
import mkarena as M
import mksolo
import mkworld


@common.needs_rom
class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = common.fresh_rom()
        cls.orig = common.rom_bytes()
        cls.loops = M.build(cls.rom, cls.orig)

    def test_column_index(self):
        rom = common.fresh_rom()
        ix = rom.column_index()
        g = rom.orig_grid(0)
        c = rom.column(g[5 * 128 + 5])
        n = ix.lookup(c)
        self.assertEqual(rom.column(n), c)
        self.assertGreater(ix.uses[n], 0)
        odd = bytearray(c)
        odd[4] ^= 0x55                                              # a column the ROM does not hold
        self.assertIsNone(ix.lookup(bytes(odd)))

    def test_vocab_has_every_junction(self):
        v = M.Vocab(common.fresh_rom())
        for arms in ('NESW', 'ESW', 'NSW', 'NEW', 'NES', 'ES', 'SW', 'NW', 'NE'):
            self.assertEqual(len(v.stamp(arms)), 16, arms)

    def test_returns_three_loops(self):
        self.assertEqual(list(self.loops), [3])
        self.assertEqual(len(self.loops[3]), 3)
        for x, z, d, r, w in self.loops[3]:
            self.assertEqual((d, r, w), (1, 2560, 1536))

    def test_grid_round_trips(self):
        # the stream written into the image decodes to the grid that was painted
        from paybackmod.mapcodec import COLUMN_BASE, decode
        g = self.rom.painted[3]
        self.assertEqual(len(g), 128 * 128)
        back, _ = decode(bytes(self.rom.d), 3)
        self.assertEqual([(p - COLUMN_BASE) // 60 for p in back], g)

    def test_tables(self):
        d = self.rom.d
        n = d[mksolo.PHONE_COUNT + 3]
        self.assertEqual(n, 22)
        g = self.rom.painted[3]
        for i in range(n):
            x, y, k, _ = d[mksolo.PHONE_TABLE + 4 * (22 * 3 + i):][:4]
            self.assertEqual(self.rom.column(g[x * 128 + y])[20 * k + 1], 0x0e)
        ns = struct.unpack_from('<b', d, mksolo.START_COUNT + 3)[0] + 1
        self.assertTrue(30 <= ns <= 68)
        # the other maps' tables are as shipped
        self.assertEqual(d[mksolo.PHONE_COUNT + 0], self.orig[mksolo.PHONE_COUNT + 0])

    def test_minimap_is_the_grid(self):
        pic = MM.read(bytes(self.rom.d), 3)
        lanes = [self.rom.column(c)[3] & 15 for c in self.rom.painted[3]]
        self.assertEqual(MM.check(MM.pack(pic), lanes, MM.compass(self.orig, 3)), [])
        # and the pictures of the other maps are untouched
        for lv in (0, 1, 2, 4):
            self.assertEqual(MM.read(bytes(self.rom.d), lv), MM.read(self.orig, lv))

    def test_pit_is_kept(self):
        orig3 = [self.rom.column(c) for c in self.rom.orig_grid(3)]
        new = [self.rom.column(c) for c in self.rom.painted[3]]
        same = diff = 0
        for x in range(54, 86):
            for y in range(59, 91):
                if orig3[x * 128 + y] == new[x * 128 + y]:
                    same += 1
                else:
                    diff += 1
        self.assertGreater(same, 0.9 * (same + diff))             # only the gates' blocks differ

    def test_rampage_destinations_fall_back_to_the_whole_map(self):
        # merge.c draws destinations from the non-filler box only if over half the cells equal the corner column
        g = self.rom.painted[3]
        self.assertLess(sum(1 for c in g if c == g[0]), len(g) // 2)

    def test_world_fits_what_citydraw_draws(self):
        data, st = mkworld.build(self.orig, merge=True, level=3, rom=self.rom, loops=self.loops)     # (limits on)
        self.assertLessEqual(st['boxes'], 3072)
        self.assertLessEqual(st['lots'], 1536)
        self.assertLessEqual(st['ramps'], 1024)
        self.assertLessEqual(st['lines'], 256)
        self.assertLessEqual(st['trees'], 2304)

    def test_rom_stays_in_32_mib(self):
        self.assertLess(self.rom.free, 32 << 20)
        self.assertLess(self.rom.ncols, 32768)

    def test_deterministic(self):
        rom = common.fresh_rom()
        M.build(rom, self.orig)
        self.assertEqual(rom.painted[3], self.rom.painted[3])


@common.needs_rom
class RefusalTest(unittest.TestCase):
    """A plan that breaks a rule stops the build (any validator)."""
    def plan(self):
        return json.load(open(M.PLAN))

    def fails(self, plan, text):
        rom = common.fresh_rom()
        with self.assertRaises(AssertionError) as cm:
            M.build(rom, common.rom_bytes(), plan)
        self.assertIn(text, str(cm.exception))

    def test_a_phone_far_from_any_road(self):
        p = self.plan()
        p['phones'][0]['cells'][0] = [37, 33]            # inside the Skyline B towers: no road within a cell
        self.fails(p, 'AV5')

    def test_a_gate_that_does_not_reach_the_pit(self):
        p = self.plan()
        p['gates'][0]['road'] = [64, 52, 67, 56]
        self.fails(p, 'AV9')

    def test_a_deck_too_low(self):
        p = self.plan()
        p['features']['SKYBRIDGE_AC']['top'] = 2048      # its underside 192 steps over the road: under 256
        self.fails(p, 'AV4')


if __name__ == '__main__':
    unittest.main()
