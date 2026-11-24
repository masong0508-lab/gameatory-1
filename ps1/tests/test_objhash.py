"""rc10 review: the PP_DIRTY change detector of the OBJ tiles (stage19/ps1rt/ppu12.h pp_obj) must see tiles moved or swapped.

The first rc10 hash (rotate by 5 and xor, plus a sum) repeated every 32 words, so a 16x16 4 bpp sprite (4 tiles = 32 words) moved or swapped
by 4 tiles kept the hash and the texture upload was skipped.  This replicates the C expression (checked to be the one in ppu12.h) and tests
the review's cases plus random whole-tile moves and swaps.  Synthetic data only."""
import random
import unittest
from pathlib import Path

PPU = Path(__file__).resolve().parents[1] / 'stage19' / 'ps1rt' / 'ppu12.h'
C_EXPR = 'u32 hh=5381u, hs=0; for(u32 i=0;i<4096;i++){ u32 w=t[i]; hh=(hh<<5)+hh+w; hs=w+(hs<<6)+(hs<<16)-hs; }'
M = 0xffffffff


def objhash(t):
    a, b = 5381, 0
    for w in t:
        a = ((a << 5) + a + w) & M
        b = (w + (b << 6) + (b << 16) - b) & M
    return (a ^ (((b << 16) | (b >> 16)) & M)) | 1


class ObjHash(unittest.TestCase):
    def test_c_matches(self):
        self.assertIn(C_EXPR, PPU.read_text())

    def test_review_cases(self):
        r = random.Random(1)
        spr = [r.getrandbits(32) for _ in range(32)]
        a = [0] * 4096; a[0:32] = spr
        b = [0] * 4096; b[32:64] = spr
        self.assertNotEqual(objhash(a), objhash(b))
        d = [0] * 4096; d[0:32] = spr; d[32:64] = spr[::-1]
        e = [0] * 4096; e[0:32] = spr[::-1]; e[32:64] = spr
        self.assertNotEqual(objhash(d), objhash(e))

    def test_random_tile_moves(self):
        r = random.Random(7)
        for _ in range(2000):
            base = [0] * 4096
            for _ in range(r.randint(1, 40)):
                p = r.randrange(512) * 8
                base[p:p + 8] = [r.getrandbits(32) for _ in range(8)]
            n = r.randint(1, 16) * 8
            s, t = r.randrange(0, 4096 - n, 8), r.randrange(0, 4096 - n, 8)
            if abs(s - t) < n:
                continue
            x = list(base)
            x[t:t + n], x[s:s + n] = base[s:s + n], base[t:t + n]
            if x != base:
                self.assertNotEqual(objhash(x), objhash(base))


if __name__ == '__main__':
    unittest.main()
