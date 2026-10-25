"""The shipped content: the blob round trip, the generators' determinism, the id lock, and a clean compile of every map
(those needing the atlases skip without the cache)."""
import json
import os
import tempfile
import unittest

import common
import misfmt as F
import sfc
import gen


class Blob(unittest.TestCase):
    def test_round_trip(self):
        def rec(name, **kw):
            d = {f: 0 for f, _ in F.FIELDS[name]}
            d.update(kw)
            return d
        texts = ['ONE', 'TWO LINES\nHERE', '']
        names = ['a.b', 'c']
        ch, ms = [rec('Chapter', map=3, split=6, hx2=20)], [rec('MisDef', id=7, map=3, par=99)]
        ob, pl = [rec('MisObj', op=2, a=-5)], [rec('MsPlace', x8=800, y8=900, h=1500, r8=12, kind=3)]
        d = F.parse(F.pack(ch, ms, ob, pl, texts, names))
        self.assertEqual(d['texts'], texts)
        self.assertEqual(d['names'], names)
        for key, want in (('chapters', ch), ('missions', ms), ('objs', ob), ('places', pl)):
            self.assertEqual(d[key], want)

    def test_crc_is_checked(self):
        b = bytearray(F.pack([], [], [], [], ['X']))
        b[-1] ^= 0xff if b[-1] else 1
        with self.assertRaises(AssertionError):
            F.parse(bytes(b))


class Shipping(unittest.TestCase):
    def test_the_rom_copy_leaves_the_mission_keys_out(self):
        import fixtures as X
        res = X.run()
        self.assertEqual(res.names, ['m0.t1'])
        full, ship = F.parse(res.blob), F.parse(res.ship)
        self.assertEqual(full['names'], ['m0.t1'])
        self.assertEqual(ship['names'], [])
        self.assertLess(len(res.ship), len(res.blob))
        for key in ('chapters', 'missions', 'objs', 'places', 'texts'):
            self.assertEqual(full[key], ship[key])

    def test_the_atlas_cache_key_holds_the_tools_that_make_an_atlas(self):
        import atlas
        import mkworld
        h0 = atlas._tool_hash()
        self.assertEqual(h0, atlas._tool_hash())
        old = mkworld.__file__
        try:
            with tempfile.NamedTemporaryFile('w', suffix='.py') as f:
                f.write('# another mkworld\n')
                f.flush()
                mkworld.__file__ = f.name
                self.assertNotEqual(h0, atlas._tool_hash())
        finally:
            mkworld.__file__ = old
        self.assertEqual(h0, atlas._tool_hash())


class Hunts(unittest.TestCase):
    def test_a_walk_in_nearest_order_and_its_length(self):
        import gen_misc as M
        order, d = M.tour([(10, 0), (3, 0), (6, 0)], (0, 0))
        self.assertEqual(order, [(3, 0), (6, 0), (10, 0)])
        self.assertAlmostEqual(d, 10.0)

    def test_the_generated_hunts_keep_to_the_walking_cap(self):
        import gen_misc as M
        import par as PAR
        self.assertLessEqual(M.HUNT_ROUTE_MAX / (1.18 * PAR.CRUISE) + 10.5, PAR.FOOT_PAR_MAX / PAR.SLACK + 1)      # (at the man's measured pace)


class Lock(unittest.TestCase):
    def test_ids_are_stable_and_unique(self):
        lock = json.load(open(os.path.join(sfc.CONTENT, 'ids.lock')))
        ids = lock['ids']
        self.assertEqual(len(set(ids.values())), len(ids))
        self.assertTrue(all(v < lock['next'] for v in ids.values()))


@common.needs_atlas
class Shipped(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.at = common.cached()
        cls.res = sfc.compile(sfc.Content.load(), cls.at)

    def test_compiles_clean(self):
        self.assertEqual(len(self.at), 11)
        self.assertFalse(self.res.errors)
        self.assertLessEqual(len(self.res.blob), 128 * 1024)

    def test_counts(self):
        import collections
        n = collections.Counter((m.map, m.kind) for m in self.res.rm)
        for lv in range(11):
            self.assertEqual(n[(lv, F.MK_ACT)], 6)
            self.assertEqual(n[(lv, F.MK_CONTRACT)], 6)
            self.assertEqual(n[(lv, F.MK_MEDAL)], 6)
            self.assertTrue(8 <= n[(lv, F.MK_CHAL)] <= 12, (lv, n[(lv, F.MK_CHAL)]))

    def test_generators_are_deterministic(self):
        hand = gen.hand_info()
        for lv in (0, 3, 9):
            a = gen.build_map(lv, self.at[lv], hand.get(lv, {}))
            b = gen.build_map(lv, self.at[lv], hand.get(lv, {}))
            self.assertEqual((a.places_text(), a.sfm_text()), (b.places_text(), b.sfm_text()))

    def test_generated_files_are_current(self):
        self.assertEqual(gen.main(None, True, self.at), 0)


if __name__ == '__main__':
    unittest.main()
