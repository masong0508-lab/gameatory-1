import os, random, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from paybackmod import bps


class BpsTest(unittest.TestCase):
    def test_roundtrip(self):
        rnd = random.Random(1)
        src = bytes(rnd.randrange(256) for _ in range(5000))
        tgt = bytearray(src) + bytes(3000)
        tgt[100:200] = bytes(rnd.randrange(256) for _ in range(100))
        tgt[6000:6500] = src[1000:1500]
        patch = bps.encode(src, bytes(tgt), [(6000, 1000, 500)])
        self.assertEqual(bps.apply(src, patch), bytes(tgt))


if __name__ == '__main__':
    unittest.main()
