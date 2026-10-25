"""Two runs of tests/s2/scenes.py side by side: how far apart the man, the car and the Arwing are each second, and
how much of each picture differs. A third run of the first build, a few frames late (SKEW), is the floor: what two
runs of one build differ by when only the frame the first key landed in moved.

    python3 tests/s2/scenecmp.py OUT_DIR TAG_A TAG_B [TAG_FLOOR]
"""
import json
import math
import sys

import numpy as np
from PIL import Image

out, a, b = sys.argv[1:4]
floor = sys.argv[4] if len(sys.argv) > 4 else None


def load(tag):
    return json.load(open('%s/scenes_%s.json' % (out, tag)))


def img(tag, scene, i):
    return np.asarray(Image.open('%s/scenes_%s_%s_%02d.png' % (out, tag, scene, i)).convert('RGB'), dtype=int)


def compare(ta, tb):
    ra, rb = load(ta), load(tb)
    rows = {}
    for scene in ('foot', 'car', 'arwing'):
        n = min(len(ra[scene]), len(rb[scene]))
        dist = [math.dist(ra[scene][i][:2] if scene != 'arwing' else (ra[scene][i][0], ra[scene][i][2]),
                          rb[scene][i][:2] if scene != 'arwing' else (rb[scene][i][0], rb[scene][i][2])) for i in range(n)]
        px = [np.abs(img(ta, scene, i) - img(tb, scene, i)).mean() for i in range(n)]
        diffpx = [100.0 * (np.abs(img(ta, scene, i) - img(tb, scene, i)).sum(2) > 0).mean() for i in range(n)]
        rows[scene] = (dist, px, diffpx)
    return rows


for scene in ('foot', 'car', 'arwing'):
    pass
cmp_ab = compare(a, b)
cmp_fl = compare(a, floor) if floor else None
print('%-8s %-34s %-34s' % ('', '%s vs %s' % (a, b), ('%s vs %s (floor)' % (a, floor)) if floor else ''))
for scene in ('foot', 'car', 'arwing'):
    d, p, q = cmp_ab[scene]
    line = '%-8s apart max %6.2f mean %6.2f cells; picture mean diff %5.2f' % (scene, max(d), sum(d) / len(d), sum(p) / len(p))
    if cmp_fl:
        d2, p2, q2 = cmp_fl[scene]
        line += ' | apart max %6.2f mean %6.2f cells; picture mean diff %5.2f' % (max(d2), sum(d2) / len(d2), sum(p2) / len(p2))
    print(line)
ra, rb = load(a), load(b)
print('first second: foot', cmp_ab['foot'][0][0:3], 'arwing', [round(x, 2) for x in cmp_ab['arwing'][0][0:3]])
