#!/usr/bin/env python3
"""respages_opt.py pages.pkl N OUT.rompages [--cluster=4|1] [--slots=8] [--wlevel=3] [--sweeps=3] [--base=FILE.rompages]
EXPERIMENT (diagnosis of the ROM page cache thrash; not part of the rc4 build): choose the N resident ROM pages from the page working sets
MEASURED on the PS1 target (rigpages.py, -DPGTRACE build) instead of the simulator's raw read counts.

Model: the runtime's page cache is replayed over the measured per-guest-frame page sets (FIFO, `slots` slots, `cluster` pages per CD fetch;
the pages of one frame are visited once in ascending order: the real order inside a frame is not known, so the model UNDER-estimates the
fetches of frames that touch more clusters than the cache holds).  A first-improvement swap search minimises the weighted number of fetches;
level frames count `wlevel` times (the trace has 180 level frames, a real session has many more).

OUT.rompages is written in the format t/mkrompages.py reads ({page: count}; the N chosen pages get the highest counts), so the build
picks exactly these pages:  NPAGES=N RPG=OUT.rompages ... bash t/disc7.sh NAME "..." 0
"""
import sys, pickle, time
A = [a for a in sys.argv[1:] if not a.startswith('--')]; F = dict(a[2:].split('=', 1) for a in sys.argv[1:] if a.startswith('--'))
d = pickle.load(open(A[0], 'rb')); N = int(A[1]); out = A[2]
CL = int(F.get('cluster', 4)); SLOTS = int(F.get('slots', 8)); WL = float(F.get('wlevel', 3)); SWEEPS = int(F.get('sweeps', 3))
frames = d['frames']; gfs = sorted(frames); cur = set(d['resident'])
lvl = [m for m in d['marks'] if m[2] == 'level clock runs'][0][1]
PH = [('language', 0, 359), ('logos', 360, 659), ('title', 660, 759), ('menus', 760, 1060), ('setup', 1061, lvl - 1), ('level', lvl, 10 ** 9)]
def phase(g):
    for i, (n, a, b) in enumerate(PH):
        if a <= g <= b: return i
seq = [(phase(g), frames[g]) for g in gfs]; W = [1, 1, 1, 1, 1, WL]
def sim(R, cl=CL, slots=SLOTS, passes=1):
    """fetches per phase for the resident set R"""
    cap = slots // cl; mask = ~(cl - 1); cache = []; miss = [0] * len(PH)
    for ph, pages in seq:
        for _ in range(passes):
            for p in pages:
                if p in R: continue
                k = p & mask
                if k in cache: continue
                miss[ph] += 1; cache.append(k)
                if len(cache) > cap: del cache[0]
    return miss
def cost(R): return sum(w * m for w, m in zip(W, sim(R)))
def show(tag, R):
    m1 = sim(R); m2 = sim(R, passes=2)
    print('%-34s %3d pages: model fetches (1 pass / 2 passes per frame)  ' % (tag, len(R)) + '  '.join('%s %d/%d' % (PH[i][0], m1[i], m2[i]) for i in range(len(PH))) + '   total %d/%d' % (sum(m1), sum(m2)))
meas = [0] * len(PH)
for g, n in d['fetch'].items():
    i = phase(g)
    if i is not None: meas[i] += n
print('measured fetches in the traced run (current disc: %d resident pages, FIFO 8 slots, cluster 4): ' % len(cur) + '  '.join('%s %d' % (PH[i][0], meas[i]) for i in range(len(PH))) + '   total %d' % sum(meas))
print('search model: cluster %d, slots %d, level weight %g' % (CL, SLOTS, WL))
show('current resident set', cur)
allp = sorted(set().union(*[set(v) for v in frames.values()]))
# start: pages ranked by the weighted number of guest frames that touch them
cnt = {}
for ph, pages in seq:
    for p in pages: cnt[p] = cnt.get(p, 0) + W[ph]
if 'base' in F:
    b = pickle.load(open(F['base'], 'rb')); R = set(sorted(b, key=lambda p: -b[p])[:N])
else:
    R = set(sorted(allp, key=lambda p: -cnt[p])[:N])
show('start (by frames touched)', R)
best = cost(R); t0 = time.time()
for sweep in range(SWEEPS):
    improved = 0
    for o in sorted(allp, key=lambda p: -cnt[p]):          # candidate to bring in
        if o in R: continue
        bi, bc = None, best
        for i in list(R):
            R.remove(i); R.add(o); c = cost(R); R.remove(o); R.add(i)
            if c < bc: bi, bc = i, c
        if bi is not None: R.remove(bi); R.add(o); best = bc; improved += 1
    print('sweep %d: %d swaps, weighted cost %d, %.0f s' % (sweep + 1, improved, best, time.time() - t0), flush=True)
    if not improved: break
show('optimised', R)
print('pages: ' + ' '.join('%03x' % p for p in sorted(R)))
print('new vs current: +%d -%d;  in: %s;  out: %s' % (len(R - cur), len(cur - R), ' '.join('%03x' % p for p in sorted(R - cur)), ' '.join('%03x' % p for p in sorted(cur - R))))
for cl, sl in ((4, 8), (1, 8), (4, 12), (1, 12)):
    m1 = sim(R, cl, sl); m2 = sim(R, cl, sl, 2); print('   this set with cluster %d, %2d slots: ' % (cl, sl) + '  '.join('%s %d/%d' % (PH[i][0], m1[i], m2[i]) for i in range(len(PH))) + '   total %d/%d' % (sum(m1), sum(m2)))
# counts for mkrompages.py: chosen pages first (by frames touched), the rest below
rank = sorted(R, key=lambda p: -cnt.get(p, 0)) + sorted([p for p in allp if p not in R], key=lambda p: -cnt.get(p, 0))
pickle.dump({p: len(rank) - i + (1000 if p in R else 0) for i, p in enumerate(rank)}, open(out, 'wb'))
print('wrote %s (%d pages, top %d = the chosen set)' % (out, len(rank), N))
