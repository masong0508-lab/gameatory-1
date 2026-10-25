"""content/arena/killzone.json: the plan is sound before anything is painted."""
import json
import os
import unittest

import common
import mkarena as M


def over(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


class PlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.load(open(M.PLAN))

    def test_everything_is_on_the_map(self):
        p = self.plan
        rects = [d['rect'] for d in p['districts'].values()] + [f['rect'] for f in p['features'].values()] + \
            [r for r in p['roads'].values()] + [g['road'] for g in p['gates']]
        for r in rects:
            self.assertTrue(2 <= r[0] <= r[2] <= 125 and 2 <= r[1] <= r[3] <= 125, r)

    def test_districts_and_roads_do_not_overlap(self):
        p = self.plan
        for dn, d in p['districts'].items():
            if d['kit'] in ('beach', 'harbour'):
                continue
            for rn, r in p['roads'].items():
                if rn.startswith('SPW') and dn == 'SPEEDWAY':
                    continue                                    # the oval is laid in its district
                self.assertFalse(over(d['rect'], r), (dn, rn))
            self.assertFalse(over(d['rect'], p['pit']) and dn != 'THE PIT', dn)

    def test_districts_do_not_overlap_each_other(self):
        ds = sorted(self.plan['districts'].items())
        for i, (an, a) in enumerate(ds):
            for bn, b in ds[i + 1:]:
                self.assertFalse(over(a['rect'], b['rect']), (an, bn))

    def test_roads_are_four_wide(self):
        for n, r in self.plan['roads'].items():
            self.assertTrue((r[2] - r[0] == 3) != (r[3] - r[1] == 3), n)

    def test_gates_cut_the_pit_wall_and_meet_a_street(self):
        px0, py0, px1, py1 = self.plan['pit']
        for g in self.plan['gates']:
            r = g['road']
            self.assertTrue(over(r, self.plan['pit']), g['name'])
            outer = [rr for n, rr in self.plan['roads'].items() if over(rr, r)]
            self.assertTrue(outer, g['name'] + ' reaches no street')
            self.assertEqual(len(g['arms']), 3, g['name'])

    def test_phones_and_spawn_hints(self):
        n = sum(len(g['cells']) for g in self.plan['phones'])
        self.assertEqual(n, 22)                                  # the table's maximum
        self.assertLessEqual(self.plan['spawns']['pit_keep'] + len(self.plan['spawns']['extra']), 68)

    def test_heights_are_whole_steps(self):
        def walk(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    if k in ('top', 'tops', 'heights', 'base', 'lip', 'under', 'slab', 'thick', 'hangar_top', 'tower_top',
                             'crane_top', 'landing_top', 'depth'):
                        for h in (x if isinstance(x, list) else [x]):
                            self.assertEqual(h % 8, 0, (k, h))
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        walk(self.plan)


if __name__ == '__main__':
    unittest.main()
