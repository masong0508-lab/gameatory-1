"""Synthetic GPU flip/picture timing regressions; no emulator or game assets."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flicker_evidence import choose_counter, display_step


class FlipEvidenceTests(unittest.TestCase):
    def test_rc8_actual_flip_counter_wins_over_present_start(self):
        vals = {'g_flips': 153, 'g_pres': 151}
        self.assertEqual(choose_counter(vals.get), ('g_flips', True))

    def test_old_disc_does_not_claim_flip_certification(self):
        vals = {'g_pres': 151}
        self.assertEqual(choose_counter(vals.get), (None, False))
        self.assertEqual(choose_counter(vals.get, allow_legacy=True), ('g_pres', False))

    def test_missing_both_symbols_fails_even_with_legacy_option(self):
        self.assertEqual(choose_counter({}.get, allow_legacy=True), (None, False))

    def test_legitimate_change_with_real_flip_is_not_a_defect(self):
        # rc8 can flip after present() started, without another g_pres step.
        # The old test filed a false issue; g_flips advances correctly.
        previous = None
        previous, changed, unsynced = display_step(previous, b'alpha', 40)
        self.assertFalse(changed)
        previous, changed, unsynced = display_step(previous, b'beta', 41)
        self.assertTrue(changed)
        self.assertFalse(unsynced)

    def test_changed_picture_with_no_gpu_flip_is_a_defect(self):
        prev, _, _ = display_step(None, b'alpha', 40)
        _, changed, unsynced = display_step(prev, b'beta', 40)
        self.assertTrue(changed)
        self.assertTrue(unsynced)

    def test_previous_flip_counter_must_advance_every_emulator_frame(self):
        # A flip can display identical pixels. If the display later mutates
        # WITHOUT a flip, counting only from the preceding changed image
        # would mistakenly forgive the in-place write.
        prev, _, _ = display_step(None, b'alpha', 40)
        prev, changed, unsynced = display_step(prev, b'alpha', 41)
        self.assertFalse(changed)
        self.assertFalse(unsynced)
        _, changed, unsynced = display_step(prev, b'beta', 41)
        self.assertTrue(changed)
        self.assertTrue(unsynced)

    def test_counter_wrap_and_invalid_data(self):
        prev, _, _ = display_step(None, b'alpha', 0xffffffff)
        _, changed, unsynced = display_step(prev, b'beta', 0)
        self.assertTrue(changed)
        self.assertFalse(unsynced)
        for invalid in (None, True, 4.5, '500'):
            with self.subTest(counter=invalid):
                with self.assertRaises(ValueError):
                    display_step(prev, b'beta', invalid)


if __name__ == '__main__':
    unittest.main()
