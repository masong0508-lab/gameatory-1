"""Route arithmetic regressions; these polylines need no ROM or atlas cache."""
import unittest

import common
import routes


class Resample(unittest.TestCase):
    def test_shipped_courses_preserve_exact_endpoints(self):
        # These two courses exposed a one-unit height drift after integer
        # conversion, with different results from different float summations.
        courses = (
            [(104.5, 51.5, 2560), (97.5, 59.5, 1024),
             (96.5, 60.5, 512), (95.5, 71.5, 2048),
             (89.5, 74.5, 512), (82.5, 74.5, 512),
             (81.5, 83.5, 3584), (80.5, 84.5, 4096),
             (81.5, 85.5, 3072), (81.5, 90.5, 512),
             (78.5, 91.5, 512), (78.5, 101.5, 512),
             (75.5, 105.5, 4096)],
            [(28.5, 88.5, 2048), (49.5, 93.5, 2048),
             (66.5, 95.5, 2560), (73.5, 95.5, 1024),
             (75.5, 93.5, 2048), (76.5, 93.5, 2560),
             (84.5, 86.5, 3072)],
        )
        for pts in courses:
            with self.subTest(endpoint=pts[-1]):
                sampled = routes.resample(pts, 7.0)
                self.assertEqual(sampled[0], pts[0])
                self.assertEqual(sampled[-1], pts[-1])
                self.assertEqual(len(sampled), 1 + round(routes.polyline_len(pts) / 7.0))

    def test_short_route_keeps_both_endpoints(self):
        pts = [(2, 3, 512), (2.5, 3.5, 1024)]
        self.assertEqual(routes.resample(pts, 7.0), pts)

    def test_single_point_is_not_duplicated(self):
        pts = [(2, 3, 512)]
        self.assertEqual(routes.resample(pts, 7.0), pts)


if __name__ == '__main__':
    unittest.main()
