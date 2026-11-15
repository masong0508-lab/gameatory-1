"""waterfix.py: ground cells the world data leaves empty.  A cell with no ground tile (ctex 0xffff) that no solid box and no ramp covers draws nothing,
so the island underlay colour (dark road grey) shows through: a hole.  The Amiga copy says what is there (grass, gravel, pavement, road edge); where the
Amiga copy has no such map the nearest drawn ground tiles do.  Code only; used by mkps1world.py (converter) and water_check.py (checker).

fill_holes(ct, hole, avoid, names=None) -> (new ct, [(x, z, old, new, how)]):
  ct     128x128 tile ids (or slots) as they are, 0xffff = none        hole   bool grid: cells to fill
  avoid  bool grid: cells whose tile must not be copied (water, box tops, ramps: not ground at street level)
  names  optional 128x128 object grid of the Amiga top texture name per cell: the tile used by the cells of the same name, the one most common nearby."""
import numpy as np
from collections import Counter
N = 128

def fill_holes(ct, hole, avoid, names=None):
    ct = ct.copy(); log = []
    good = (ct != 0xffff) & ~avoid & ~hole
    by_name = {}
    if names is not None:
        for x, z in np.argwhere(good):
            by_name.setdefault(names[x, z], Counter())[int(ct[x, z])] += 1
    todo = [tuple(c) for c in np.argwhere(hole)]
    def local(x, z, r):
        c = Counter()
        for a in range(max(0, x - r), min(N, x + r + 1)):
            for b in range(max(0, z - r), min(N, z + r + 1)):
                if good[a, b]: c[int(ct[a, b])] += 1
        return c
    for rnd in range(8):
        rest = []
        for (x, z) in todo:
            new = None; how = ''
            if names is not None and by_name.get(names[x, z]):
                cand = by_name[names[x, z]]; loc = local(x, z, 3)
                best = max(cand, key=lambda t: (loc.get(t, 0), cand[t]))
                new = best; how = 'amiga:%s' % names[x, z]
            if new is None:
                loc = local(x, z, 1)
                if loc: new = loc.most_common(1)[0][0]; how = 'nearest'
            if new is None: rest.append((x, z)); continue
            log.append((x, z, int(ct[x, z]), new, how)); ct[x, z] = new
        for (x, z, o, n, h) in log: good[x, z] = True
        if not rest: break
        todo = rest
    return ct, log
