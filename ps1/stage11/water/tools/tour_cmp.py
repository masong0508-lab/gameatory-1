#!/usr/bin/env python3
"""tour_cmp.py LOG_A LOG_B ...: per map worst-view scanlines of the AUTOTOUR log lines (avg/max lines a frame, prims, lod); emulator-only numbers."""
import re, sys
def rd(n):
    d = {}
    for l in open(n):
        m = re.search(r'TOUR map (\d+) view (\d+) avg (\d+) max (\d+) prims (\d+) ovf (\d+) lod (\d+)', l)
        if m: d.setdefault((int(m[1]), int(m[2])), tuple(map(int, m.groups()[2:])))   # first lap only (the tour loops; later laps differ by CD stream state)
    return d
L = [rd(n) for n in sys.argv[1:]]
print('map  ' + '  '.join('%-22s' % n.split('/')[-1] for n in sys.argv[1:]) + '   (worst avg lines / mean lod / mean prims of the 4 views)')
for m in range(11):
    row = []
    for d in L:
        v = [d[(m, k)] for k in range(4) if (m, k) in d]
        row.append('%4d  lod %.1f  prims %3d   ' % (max(x[0] for x in v), sum(x[4] for x in v) / len(v), sum(x[2] for x in v) / len(v)) if v else '-')
    print('%3d  ' % m + '  '.join(row))
print('worst max ' + ', '.join('%d' % max(x[1] for x in d.values()) for d in L) + '   ovf ' + ', '.join('%d' % sum(x[3] for x in d.values()) for d in L))
