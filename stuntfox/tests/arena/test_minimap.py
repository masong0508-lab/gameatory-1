"""The minimap picture: packing, Payback's rule for it, the compass mark, and AV8's check."""
import unittest

import common
import minimap as MM


def lanes_with(cells):
    lanes = [0] * (128 * 128)
    for x, y in cells:
        lanes[x * 128 + y] = 1
    return lanes


class MinimapTest(unittest.TestCase):
    def test_pack_roundtrip(self):
        pix = [[(px * 3 + py) % 16 for px in range(64)] for py in range(64)]
        self.assertEqual(MM.unpack(MM.pack(pix)), pix)
        self.assertEqual(len(MM.pack(pix)), 0x800)

    def test_low_nibble_first(self):
        pix = [[0] * 64 for _ in range(64)]
        pix[0][0], pix[0][1] = 2, 7
        self.assertEqual(MM.pack(pix)[0], 0x72)

    def test_rule(self):
        # one lane cell at (10, 10) fills the pixel (5, 5) with road; the pixels east and south of it are clear, the
        # ones whose west, north or north-west pixel is road are in its shadow
        pix = MM.pixels(lanes_with([(10, 10)]))
        self.assertEqual(pix[5][5], MM.ROAD)
        self.assertEqual((pix[5][6], pix[6][5], pix[6][6]), (MM.SHADOW,) * 3)
        self.assertEqual((pix[5][4], pix[4][5], pix[4][4]), (MM.EMPTY,) * 3)

    def test_stamp_is_on_top(self):
        pix = MM.pixels(lanes_with([(60, 4)]), [(30, 2, MM.MARK)])
        self.assertEqual(pix[2][30], MM.MARK)

    def test_check(self):
        lanes = lanes_with([(x, 40) for x in range(10, 60)])
        pic = MM.pack(MM.pixels(lanes))
        self.assertEqual(MM.check(pic, lanes), [])
        bad = MM.pack(MM.pixels(lanes_with([(x, 90) for x in range(10, 60)])))     # a picture of another map
        self.assertTrue(MM.check(bad, lanes))
        self.assertTrue(MM.check(pic[:-1], lanes))

    @common.needs_rom
    def test_compass_and_rule_on_freedom_city(self):
        from paybackmod.rom import PaybackRom
        rb = common.rom_bytes()
        rom = PaybackRom(rb)
        stamp = MM.compass(rb, 3)
        self.assertEqual(sum(1 for *_, c in stamp if c == MM.MARK), 16)
        self.assertEqual(MM.compass(rb, 0), stamp)                 # the same mark on every map
        for level in (0, 1, 2):
            g = rom.orig_grid(level)
            lanes = [rom.column(c)[3] & 15 for c in g]
            mine, shipped = MM.pixels(lanes, stamp), MM.read(rb, level)
            road = [(a == MM.ROAD) == (b == MM.ROAD) for ra, rb2 in zip(mine, shipped) for a, b in zip(ra, rb2)]
            self.assertGreater(sum(road) / len(road), 0.97, 'level %d' % level)      # (the shipped pictures were touched by hand: 98 to 99.6%)


if __name__ == '__main__':
    unittest.main()
