"""ROM-free regression tests for traffic preservation during Neo Mute City generation."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from paybackmod import newcity, stuntpark
from paybackmod.blocks import rec, EMPTY


class CityRoadTests(unittest.TestCase):
    def test_elevated_road_is_still_road(self):
        # Roads can be raised and sloped. Their lane flags, not floor height,
        # determine whether they must survive the new city generator.
        raised = rec(0x100, 0x160, shape=3, flags=0x60, b3=0x2) + EMPTY + EMPTY
        self.assertEqual(newcity._kind(raised), '+')
        self.assertEqual(newcity._kind(stuntpark.surf(0x100)), '.')

    def test_city_generator_preserves_roads_and_stadium(self):
        ground = stuntpark.surf(0x100)
        road = rec(0x100, 0x160, shape=3, flags=0x60, b3=0x2) + EMPTY + EMPTY
        city = [ground] * (128 * 128)
        for x in range(8, 120):
            city[x * 128 + 48] = road
        changes = newcity.build(city, seed=2026)
        for x in range(8, 120):
            self.assertNotIn((x, 48), changes,
                             f'elevated road cell {x},48 was painted over')
        for x in range(40, 80):
            for y in range(24, 44):
                self.assertNotIn((x, y), changes,
                                 f'stunt stadium cell {x},{y} was overwritten')


if __name__ == '__main__':
    unittest.main()
