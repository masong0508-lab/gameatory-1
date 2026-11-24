"""ROM-free physical-miss ranking and relocated page-boundary tests."""
import sys
import unittest
from fractions import Fraction
from pathlib import Path

PS1 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PS1 / "msb"))
from mkpagelists_msb import T0, T1, remap
from residency import choose_pages, score_profiles


def profile(*scenes):
    return dict(schema=1, rom_bytes=16777216, page_bytes=4096,
                metric="physical_miss_requests", scenes=list(scenes))


def scene(name, counts, saturated=False):
    return dict(name=name, counts=counts, saturated=saturated)


class ResidencyTests(unittest.TestCase):
    def test_physical_miss_scene_normalization(self):
        scores = score_profiles(profile(scene("walk", {"001": 100, "002": 100}),
                                       scene("drive", {"802": 1})))
        self.assertEqual(scores, {1: Fraction(1, 2), 2: Fraction(1, 2), 0x802: Fraction(1)})

    def test_boot_reserve_and_unique_upper_half_pages(self):
        measured = {0x800: Fraction(1), 0x801: Fraction(2), 0x802: Fraction(3)}
        boot = {5: 10, 6: 20, 7: 1, 8: 2}
        self.assertEqual(choose_pages(boot, measured, 4, 1), [6, 0x800, 0x801, 0x802])
        self.assertEqual(choose_pages(boot, measured, 5, 2), [5, 6, 0x800, 0x801, 0x802])

    def test_refuses_bad_or_saturated_measurements(self):
        good = scene("walk", {"000": 1})
        for bad in (scene("drive", {"1000": 1}), scene("drive", {"800": -1}),
                    scene("drive", {"800": True}), scene("drive", {"800": 1}, True),
                    scene("drive", {"800": 1, "0x800": 2}), scene("walk", {"800": 1})):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                score_profiles(profile(good, bad))
        with self.assertRaises(ValueError):
            score_profiles(profile(good))
        with self.assertRaises(ValueError):
            choose_pages({1: 1}, {2: 1}, 62, 1)

    def test_relocation_keeps_original_prefix_and_tail(self):
        first, last = T0 >> 12, (T1 - 1) >> 12
        _, scores = remap([first, last], 61)
        self.assertEqual(scores[first], T0 & 4095)
        self.assertEqual(scores[last], 4096 - (T1 & 4095))
        self.assertEqual(sum(scores.values()), 8192)
        self.assertTrue(any(p >= 2048 for p in scores))

    def test_profiler_counts_only_real_fetch_paths(self):
        src = (PS1 / "stage19" / "ps1rt" / "rt.c").read_text()
        region = src[src.index("static __attribute__((noinline)) const u8 *cd_fetch(u32 pg){"):]
        soft = region.index("rom_soft++; return rom_pg[pg]")
        first = region.index("PGPROF_MISS(pg)")
        self.assertGreater(first, soft)
        self.assertEqual(region.split("#else  /*", 1)[0].count("PGPROF_MISS(pg); rom_miss_count++"), 2)


if __name__ == "__main__":
    unittest.main()
