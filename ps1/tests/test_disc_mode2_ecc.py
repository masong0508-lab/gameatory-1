"""ROM-free checks of the actual raw disc builder's Mode 2 sectors."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

BUILDER = pathlib.Path(__file__).resolve().parents[1] / 'stage7/integration/tools7/mkdisc2.py'
SECTOR = 2352


def syndrome(word):
    """Evaluate the Reed-Solomon codeword at roots 1 and 2 in GF(256)."""
    at_one = at_two = 0
    for value in word:
        at_one ^= value
        at_two = ((at_two << 1) ^ (0x11d if at_two & 128 else 0)) ^ value
    return at_one, at_two


def check_parity(sec, major, minor, stride, step, parity):
    # Mode 2 Form 1: both P and Q see four zero header bytes, not MSF/mode.
    data = bytes(4) + sec[16:parity]
    size = major * minor
    for m in range(major):
        start = (m // 2) * stride + m % 2
        word = [data[(start + k * step) % size] for k in range(minor)]
        word.extend((sec[parity + m], sec[parity + m + major]))
        if syndrome(word) != (0, 0):
            return False
    return True


class DiscMode2ECC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        p = pathlib.Path(cls.temp.name)
        cls.payload = bytes((i * 7 + 13) % 256 for i in range(2048))
        iso = p / 'synthetic.iso'
        iso.write_bytes(bytes(16 * 2048) + cls.payload * 80)
        cls.discs = {}
        for region in 'UEJ':
            out = p / region
            subprocess.run([sys.executable, str(BUILDER), '--iso', str(iso),
                            '--out', str(out), '--region', region], check=True,
                           capture_output=True)
            cls.discs[region] = out.with_suffix('.bin').read_bytes()

    def test_payload_and_addresses_preserved(self):
        for disc in self.discs.values():
            self.assertEqual(len(disc), 96 * SECTOR)
            for lba in range(16, 96):
                sec = disc[lba * SECTOR:(lba + 1) * SECTOR]
                frame = lba + 150
                def bcd(n): return (n // 10) * 16 + n % 10
                self.assertEqual(sec[12:16], bytes((bcd(frame // 4500),
                    bcd(frame // 75 % 60), bcd(frame % 75), 2)))
                self.assertEqual(sec[24:2072], self.payload)

    def test_equal_payload_has_equal_parity(self):
        disc = self.discs['U']
        first = disc[16 * SECTOR:17 * SECTOR]
        for lba in (17, 74, 75, 76, 95):
            sec = disc[lba * SECTOR:(lba + 1) * SECTOR]
            self.assertNotEqual(sec[12:16], first[12:16])
            self.assertEqual(sec[0x818:], first[0x818:])

    def test_all_form1_codewords_have_zero_syndrome(self):
        for region, disc in self.discs.items():
            for lba in list(range(12)) + list(range(16, 96)):
                sec = disc[lba * SECTOR:(lba + 1) * SECTOR]
                with self.subTest(region=region, lba=lba):
                    self.assertTrue(check_parity(sec, 86, 24, 2, 86, 0x81c))
                    self.assertTrue(check_parity(sec, 52, 43, 86, 88, 0x8c8))


if __name__ == '__main__':
    unittest.main()
