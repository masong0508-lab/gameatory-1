"""Columns as the builders make them, and the validators on small made-up grids (no ROM needed), each with a grid that must fail."""
import unittest

import common   # noqa: F401  (import paths)
import arenacheck as AC
import mkarena as M
import mkworld

N, S = 128, M.STREET


class Fake:
    """Just enough of an Arena for the validators that read one."""
    def __init__(self, cols, pit=(0, 0, 0, 0)):
        self.cols, self.plan, self.loops = cols, {'pit': pit, 'gates': []}, []
        self.kind = ['ground'] * (N * N)

    def in_pit(self, x, y):
        return False

    def sector_boxes(self, r):
        return {}, {}


def flat():
    return [M.col_ground(2)] * (N * N)


def put(cols, x, y, col):
    cols[x * N + y] = col


def road_y(cols, x0, y0, y1):
    """A road along y (kerb, lane -y, lane +y, kerb across x) from y0 to y1."""
    for y in range(y0, y1 + 1):
        for i, b3 in enumerate((0x20, 1, 4, 0x20)):
            put(cols, x0 + i, y, M.col_ground(43, b3))


class BuilderTest(unittest.TestCase):
    def test_sizes_and_heights(self):
        for col in (M.col_ground(2), M.col_building(M.raw(2048), 41, 26), M.col_table(S + 100, 41, 41),
                    M.col_slope(S, S + 50, 3, 74), M.col_water(128)):
            self.assertEqual(len(col), 60)
        self.assertEqual(M.raw(0), S)
        self.assertEqual(M.raw(1024), S + 128)
        self.assertRaises(AssertionError, M.raw, 12)
        recs = mkworld.pb_records(M.col_building(M.raw(2048), 41, 26))
        self.assertEqual(max(r[2] for r in recs if r[3]), S + 256)
        slope = mkworld.pb_records(M.col_slope(S, S + 50, 3, 74))[0]
        self.assertEqual((slope[1], slope[2], slope[3]), (S, S + 50, 3))

    def test_deck_keeps_the_road_under_it(self):
        road = M.col_ground(43, 1)
        deck = M.with_deck(road, S + 256, S + 320, 41, 41)
        self.assertEqual(deck[3], 1)
        self.assertEqual(deck[:20], road[:20])
        self.assertEqual(AC.av4([deck] * (N * N)), [])
        low = M.with_deck(road, S + 100, S + 164, 41, 41)
        self.assertEqual(len(AC.av4([low] + [M.col_ground(2)] * (N * N - 1))), 1)

    def test_steps(self):
        b = M.Arena.steps(448, 9)
        self.assertEqual((b[0], b[-1], len(b)), (0, 448, 10))
        self.assertEqual(b, sorted(b))
        for lo, hi in zip(b, b[1:]):                                   # each cell reaches a knee (64) or lifts under 24 at its side
            self.assertTrue(hi >= 64 or lo + hi <= 48, (lo, hi))
        self.assertEqual(sum(1 for _ in M.Arena.steps(10, 4)), 5)


class ValidatorTest(unittest.TestCase):
    def test_flat_road_is_clean(self):
        cols = flat()
        road_y(cols, 10, 10, 60)
        self.assertEqual(AC.av2(cols), [])
        self.assertEqual(AC.av3(cols), [])
        self.assertEqual(AC.av6(cols, [(10, 30, 0), (13, 30, 0)]), [])

    def test_av2_a_gap_in_a_road_and_a_lone_lane(self):
        cols = flat()
        road_y(cols, 10, 10, 60)
        put(cols, 11, 30, M.col_ground(2))                    # a lane gone from the road
        self.assertTrue(any('gap' in m for m in AC.av2(cols)))
        cols = flat()
        put(cols, 40, 40, M.col_ground(43, 1))
        self.assertTrue(any('lone' in m for m in AC.av2(cols)))

    def test_av3_a_step_needs_a_wall(self):
        cols = flat()
        put(cols, 20, 20, M.col_table(S + 120, 41, 41))                  # a floor 120 steps up, built with walls
        self.assertEqual(AC.av3(cols), [])
        bare = bytearray(cols[20 * N + 20])
        bare[12:20] = bytes(8)                                           # the same with its walls taken off
        cols[20 * N + 20] = bytes(bare)
        self.assertTrue(any('without a wall' in m for m in AC.av3(cols)))
        put(cols, 20, 20, M.col_table(S + 20, 41, 41))                   # (a low step needs none)
        cols[20 * N + 20] = cols[20 * N + 20][:12] + bytes(8) + cols[20 * N + 20][20:]
        self.assertEqual(AC.av3(cols), [])

    def test_av3_slopes_meet(self):
        cols = flat()
        put(cols, 20, 20, M.col_slope(S, S + 20, 3, 74))
        put(cols, 21, 20, M.col_slope(S + 30, S + 50, 3, 74))
        self.assertTrue(any('do not meet' in m for m in AC.av3(cols)))
        put(cols, 21, 20, M.col_slope(S + 20, S + 40, 3, 74))
        self.assertEqual(AC.av3(cols), [])

    def test_av5_phones(self):
        cols = flat()
        road_y(cols, 10, 10, 60)
        put(cols, 14, 30, M.with_object(M.col_ground(2), M.PHONE_OBJ))
        self.assertEqual(AC.av5(cols, [(14, 30, 0)]), [])
        put(cols, 15, 30, M.col_building(M.raw(2048), 41, 26))          # a wall in the 3 x 3
        self.assertTrue(any('not clear' in m for m in AC.av5(cols, [(14, 30, 0)])))
        self.assertTrue(any('not beside' in m for m in AC.av5(flat(), [(40, 40, 0)])))

    def test_av6_spawns(self):
        cols = flat()
        road_y(cols, 10, 10, 60)
        self.assertEqual(AC.av6(cols, [(10, 30, 0)]), [])               # on the kerb, lane runs -y
        put(cols, 11, 28, M.col_building(M.raw(2048), 41, 26))
        put(cols, 10, 27, M.col_building(M.raw(2048), 41, 26))
        self.assertTrue(AC.av6(cols, [(10, 30, 0)]))                    # a wall 3 cells ahead
        self.assertTrue(AC.av6(cols, [(30, 30, 0)]))                    # not on a road

    def test_av1_roads_must_connect(self):
        cols = flat()
        road_y(cols, 10, 10, 60)
        road_y(cols, 30, 10, 60)
        for y in range(N):                                                # a wall between the two roads
            put(cols, 20, y, M.col_building(M.raw(2048), 41, 26))
        self.assertTrue(any('out of reach' in m for m in AC.av1(cols, [(10, 20, 0)])))
        for j, b3 in enumerate((0x20, 2, 8, 0x20)):                        # a gap in the wall, and a street through it
            put(cols, 20, 30 + j, M.col_ground(43, b3))
        self.assertEqual(AC.av1(cols, [(10, 20, 0), (33, 50, 0)]), [])

    def test_av9_gate_lanes(self):
        cols = flat()
        for y in range(52, 70):
            for i, b3 in enumerate((0x20, 1, 4, 0x20)):
                put(cols, 64 + i, y, M.col_ground(43, b3))
        gate = {'name': 'G', 'road': [64, 52, 67, 58]}
        self.assertEqual(AC.av9(cols, [gate], (53, 58, 86, 91)), [])
        put(cols, 65, 61, M.col_ground(2))
        self.assertTrue(AC.av9(cols, [gate], (53, 58, 86, 91)))


if __name__ == '__main__':
    unittest.main()
