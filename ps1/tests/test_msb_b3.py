"""ROM-free B3 profile and physical RAM planning regressions."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "merged"))
from b3_profile import (B2_FILES, B2_CONST, choose_profile, align_up,
                        upper_bound, pack_text, linked_ram_census)


class B3ProfileTests(unittest.TestCase):
    def test_b2_exact_rollback(self):
        name, files, consts, _ = choose_profile({"SFNAT_PROFILE": "b2"})
        self.assertEqual((name, files, consts), ("b2", B2_FILES, B2_CONST))

    def test_b3_native_city_paths_and_tables(self):
        name, files, consts, _ = choose_profile({})
        self.assertEqual(name, "b3")
        self.assertEqual(files - B2_FILES, {"marker", "loops", "hudline", "settings"})
        self.assertTrue({"pb_pmap", "pb_sky", "pb_mesh", "sp_tab"} <= consts)
        self.assertFalse({"citydraw"} - files)
        self.assertNotIn("planetdata", files)

    def test_explicit_selection_and_bad_profile(self):
        self.assertEqual(choose_profile({"SFNAT_ONLY": "marker loops"})[1],
                         {"marker", "loops"})
        self.assertFalse(choose_profile({"SFNAT_ONLY": "all"})[1])
        with self.assertRaises(ValueError):
            choose_profile({"SFNAT_PROFILE": "typo"})

    def test_alignment_counts_every_section(self):
        self.assertEqual(align_up(17, 16), 32)
        with self.assertRaises(ValueError):
            align_up(17, 3)
        secs = [(".text.a", "PROGBITS", 31, 4),
                (".text.b", "PROGBITS", 30, 32),
                (".text.c", "PROGBITS", 20, 64)]
        where, used = pack_text(secs, {"R3": 96, "R2": 36})
        self.assertEqual(where["R3"], [".text.a", ".text.b"])
        self.assertEqual(used["R3"], 62)
        self.assertEqual(where["R2"], [".text.c"])
        self.assertEqual(upper_bound(secs), 178)

    def test_overflow_spills_to_R1_without_silent_overbook(self):
        secs = [(".text.a", "PROGBITS", 41, 4),
                (".text.b", "PROGBITS", 32, 32)]
        where, _ = pack_text(secs, {"R3": 96, "R2": 32})
        self.assertEqual(where["R1"], [".text.b"])

    def test_linked_census_reports_bytes_not_estimates(self):
        syms = dict(__bss_end=0x80026000, __rtcold_end=0x80029f00,
                    sfn___data_lma=0x80118000, __doll_start=0x80165000,
                    __dlbss_end=0x80179f00, __sfbss_end=0x801af000)
        out = linked_ram_census(syms, 512, 0x800eb430)
        self.assertEqual(out["runtime"]["free_bytes"], 8192)
        self.assertEqual(out["native_R1"]["free_bytes"], 3584)
        self.assertEqual(out["native_R2"]["free_bytes"], 256)
        self.assertEqual(out["native_stack"]["reserved_bytes"], 12288)
        syms["__dlbss_end"] = 0x8017a001
        with self.assertRaises(ValueError):
            linked_ram_census(syms, 512, 0x800eb430)
        del syms["__dlbss_end"]
        with self.assertRaises(KeyError):
            linked_ram_census(syms, 512, 0x800eb430)


if __name__ == "__main__":
    unittest.main()
