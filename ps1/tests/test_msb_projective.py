"""ROM-free coverage for the native projective wall planner."""
import ctypes as C
import pathlib
import random
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Plane(C.Structure):
    _fields_ = [("w", C.c_int32 * 3), ("a", C.c_int32 * 3),
                ("b", C.c_int32 * 3), ("wlim", C.c_int32), ("mask", C.c_uint)]


class Tri(C.Structure):
    _fields_ = [("xy", C.c_int16 * 6), ("uv", C.c_uint16 * 3), ("tile", C.c_uint8)]


class Plan(C.Structure):
    _fields_ = [("tri", Tri * 64), ("n", C.c_uint)]


@unittest.skipUnless(shutil.which("cc"), "C compiler required")
class TestProjective(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        src = pathlib.Path(cls.tmp.name) / "plan.c"
        src.write_text('''#include <stdint.h>
typedef uint32_t u32;typedef int32_t s32;typedef uint64_t u64;typedef int64_t s64;
typedef int16_t s16;typedef uint16_t u16;typedef uint8_t u8;
#include "sfprojective.h"
int plan(const SfpPlane*p,const s16*xy,int n,SfpPlan*out){return sfp_plan(p,xy,n,out);}
''')
        lib = src.with_suffix(".so")
        subprocess.run(["cc", "-std=c99", "-O2", "-shared", "-fPIC",
                        "-I", str(ROOT / "merged"), str(src), "-o", str(lib)], check=True)
        cls.lib = C.CDLL(str(lib))
        cls.lib.plan.argtypes = [C.POINTER(Plane), C.POINTER(C.c_int16), C.c_int, C.POINTER(Plan)]
        cls.lib.plan.restype = C.c_int

    def plan(self, w, a, b, lim=1, mask=15, xy=(0, 0, 3840, 0, 3840, 2560, 0, 2560)):
        p = Plane((C.c_int32 * 3)(*w), (C.c_int32 * 3)(*a), (C.c_int32 * 3)(*b), lim, mask)
        o = Plan()
        o.n = 64
        ok = self.lib.plan(C.byref(p), (C.c_int16 * len(xy))(*xy), len(xy) // 2, C.byref(o))
        return ok, o

    def test_tiles_and_atomic_rejection(self):
        ok, plan = self.plan([102400, 0, 0], [0, 100, 0], [0, 0, 100])
        self.assertTrue(ok)
        self.assertEqual({q.tile for q in plan.tri[:plan.n]}, {0, 1, 2, 3})
        ok, plan = self.plan([102400, 0, 0], [0, 100, 0], [0, 0, 100], mask=0)
        self.assertTrue(ok)
        self.assertEqual({q.tile for q in plan.tri[:plan.n]}, {4})
        for w, xy in [([0, 0, 0], (0, 0, 3840, 0, 3840, 2560, 0, 2560)),
                      ([102400, 0, 0], (-1, 0, 3840, 0, 3840, 2560, 0, 2560)),
                      ([102400, -1000, 0], (0, 0, 3840, 0, 3840, 2560, 0, 2560))]:
            ok, plan = self.plan(w, [0, 100, 0], [0, 0, 100], xy=xy)
            self.assertFalse(ok)
            self.assertEqual(plan.n, 0)

    def test_random_coverage_and_budget(self):
        rng = random.Random(20261125)
        accepted = rejected = split = 0
        for _ in range(500):
            w = [102400, rng.randrange(-300, 1200), rng.randrange(-120, 200)]
            a = [rng.randrange(-1200, 1200), rng.randrange(30, 150), rng.randrange(-6, 7)]
            b = [rng.randrange(-500, 500), rng.randrange(-5, 6), rng.randrange(30, 200)]
            ok, o = self.plan(w, a, b, rng.choice([0, 50000, 105000, 130000]), rng.randrange(1, 16))
            if not ok:
                self.assertEqual(o.n, 0)
                rejected += 1
                continue
            accepted += 1
            split += o.n > 8
            self.assertLessEqual(o.n, 64)
            area = 0
            for q in o.tri[:o.n]:
                self.assertIn(q.tile, range(5))
                self.assertTrue(all(0 <= v <= (160 if i % 2 else 240) for i, v in enumerate(q.xy)))
                x, y, x1, y1, x2, y2 = q.xy
                area += abs((x1-x)*(y2-y)-(y1-y)*(x2-x))
            # Rounded integer GPU vertices, not a pixel-equivalence test.
            self.assertLessEqual(abs(area - 2*240*160), 300)
        self.assertGreater(accepted, 400)
        self.assertGreater(rejected, 0)
        self.assertGreater(split, 200)


if __name__ == "__main__":
    unittest.main()
