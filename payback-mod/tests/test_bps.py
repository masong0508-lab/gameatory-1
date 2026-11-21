import os
import random
import sys
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from paybackmod import bps


def crafted_patch(source, target, commands, metadata=b''):
    """Build a checksummed patch with arbitrary commands to test corrupt input."""
    out = (b'BPS1' + bps._num(len(source)) + bps._num(len(target))
           + bps._num(len(metadata)) + metadata + commands)
    out += zlib.crc32(source).to_bytes(4, 'little')
    out += zlib.crc32(target).to_bytes(4, 'little')
    return out + zlib.crc32(out).to_bytes(4, 'little')


class BpsTest(unittest.TestCase):
    def test_roundtrip(self):
        rnd = random.Random(1)
        src = bytes(rnd.randrange(256) for _ in range(5000))
        tgt = bytearray(src) + bytes(3000)
        tgt[100:200] = bytes(rnd.randrange(256) for _ in range(100))
        tgt[6000:6500] = src[1000:1500]
        patch = bps.encode(src, bytes(tgt), [(6000, 1000, 500)])
        self.assertEqual(bps.apply(src, patch), bytes(tgt))

    def test_target_copy_overlap(self):
        # A literal "AB", followed by a TargetCopy pointing two bytes backward.
        # The copy must repeat the already-built output without reading future bytes.
        src, tgt = b'', b'AB' * 6
        commands = (bps._num(((2 - 1) << 2) | bps.TARGET_READ) + b'AB'
                    + bps._num(((10 - 1) << 2) | bps.TARGET_COPY) + bps._signed(0))
        self.assertEqual(bps.apply(src, crafted_patch(src, tgt, commands)), tgt)

    def test_wrong_source_and_bad_patch_crc(self):
        patch = bps.encode(b'abcdefghijk', b'HELLO')
        with self.assertRaisesRegex(ValueError, 'different source'):
            bps.apply(b'abcdefghijX', patch)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            bps.apply(b'abcdefghijk', patch[:-1] + bytes([patch[-1] ^ 1]))

    def test_rejects_malformed_commands(self):
        cases = [
            # A command writes more than the declared output length.
            (b'abc', b'X', bps._num(((2 - 1) << 2) | bps.TARGET_READ) + b'XY'),
            # A SourceRead cannot read beyond the input.
            (b'a', b'12', bps._num(((2 - 1) << 2) | bps.SOURCE_READ)),
            # A SourceCopy cannot read a position outside the input.
            (b'ab', b'Z', bps._num(bps.SOURCE_COPY) + bps._signed(-1)),
            # A TargetCopy cannot reference output that has not been written.
            (b'', b'X', bps._num(bps.TARGET_COPY) + bps._signed(0)),
            # A TargetRead cannot consume bytes from the checksum footer.
            (b'', b'XY', bps._num(((2 - 1) << 2) | bps.TARGET_READ) + b'X'),
            # An incomplete command sequence must not leave zero-filled output.
            (b'', b'XY', bps._num(bps.TARGET_READ) + b'X'),
        ]
        for src, target, commands in cases:
            with self.subTest(commands=commands), self.assertRaises(ValueError):
                bps.apply(src, crafted_patch(src, target, commands))

    def test_rejects_truncated_header_and_metadata(self):
        with self.assertRaises(ValueError):
            bps.apply(b'', b'BPS1')
        broken = crafted_patch(b'', b'', b'', metadata=b'a')
        # Header claims metadata length two, but has only one byte.
        pos = 4 + len(bps._num(0)) + len(bps._num(0))
        broken = broken[:pos] + bps._num(2) + broken[pos + 1:]
        broken = broken[:-4] + zlib.crc32(broken[:-4]).to_bytes(4, 'little')
        with self.assertRaises(ValueError):
            bps.apply(b'', broken)


if __name__ == '__main__':
    unittest.main()
