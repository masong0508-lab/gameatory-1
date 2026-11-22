"""The keep's headroom rule of tools/memguard.py, without a cartridge image or a linked game.

The merged build runs memguard.check() after linking (tools/s2build.py) and stops when it exits. These cases
drive the rule itself, and check() over the real merge.ld and memmap.txt with a made-up section list in
place of the linked ELF's, so they need no ROM and no ARM tools.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import memguard  # noqa: E402

LD, MAP = str(ROOT / 'src' / 'merge.ld'), str(ROOT / 'memmap.txt')


class KeepHeadroom(unittest.TestCase):
    def setUp(self):
        _, keep = memguard.ranges(MAP)
        self.name, self.reserve, self.margin = keep
        _, byname = memguard.regions(LD)
        self.lo, self.hi = byname[self.name][0], byname[self.name][1]

    def test_the_floor_is_the_reserve_for_the_next_stage(self):
        self.assertEqual(memguard.MIN_HEADROOM, 900)

    def test_rule_passes_at_the_floor_and_fails_one_byte_under(self):
        base = self.reserve + self.margin
        lines, fail = memguard.keep_rule(base + 900, self.reserve, self.margin)
        self.assertEqual(fail, [])
        self.assertIn('memguard: keep headroom 900 bytes', lines[1])
        lines, fail = memguard.keep_rule(base + 899, self.reserve, self.margin)
        self.assertEqual(len(fail), 1)
        self.assertIn('keep headroom is 899 bytes, 1 short of the 900 kept back for the next stage', fail[0])
        self.assertIn('MIN_HEADROOM', fail[0])
        self.assertIn('memguard: keep headroom 899 bytes', lines[1])    # (the usual line is still printed)

    def test_rule_keeps_its_older_message_under_the_stage_3_reserve(self):
        _, fail = memguard.keep_rule(self.reserve + self.margin - 1, self.reserve, self.margin)
        self.assertEqual(len(fail), 1)
        self.assertIn('short of the stage 3 reserve', fail[0])

    def check_with_free(self, free):
        """memguard.check() with one made-up .bss that leaves `free` bytes of the keep."""
        real = memguard.sections
        memguard.sections = lambda elf: [(self.lo, self.hi - free, 'section .bss')]
        try:
            return memguard.check('no.elf', LD, MAP)
        finally:
            memguard.sections = real

    def test_check_passes_with_the_floor_free(self):
        report = self.check_with_free(self.reserve + self.margin + 900)
        self.assertIn('memguard: keep headroom 900 bytes', report)
        self.assertIn('memguard: OK', report)

    def test_check_stops_the_build_under_the_floor(self):
        with self.assertRaises(SystemExit) as stop:
            self.check_with_free(self.reserve + self.margin + 899)
        text = str(stop.exception)
        self.assertIn('1 short of the 900 kept back for the next stage', text)
        self.assertIn('memguard: memory map breaks memmap.txt', text)


if __name__ == '__main__':
    unittest.main()
