#!/usr/bin/env python3
"""pages_report.py pages.pkl: ROM page working sets per phase from the PGTRACE run (see rigpages.py)."""
import sys, pickle, collections
d = pickle.load(open(sys.argv[1], 'rb')); F = d['frames']; R = set(d['resident']); marks = d['marks']; fetch = d['fetch']
gfs = sorted(F)
lvl = [m for m in marks if m[2] == 'level clock runs'][0][1]
phases = [('language screen', 100, 350), ('logos / intro', 360, 655), ('title menu', 660, 750), ('save slots, name, game menu', 760, 1060), ('rampage setup -> level load', 1061, lvl - 1), ('level (idle, walk, turn, pause, weapon, shoot)', lvl, max(gfs))]
print('resident pages %d; level clock from guest frame %d; frames with data %d' % (len(R), lvl, len(gfs)))
allp = set().union(*[set(F[g]) for g in gfs]); print('distinct ROM pages touched in the whole run: %d (%d KiB), of them resident %d, not resident %d' % (len(allp), len(allp) * 4, len(allp & R), len(allp - R)))
print('resident pages never touched in this run: %d: %s' % (len(R - allp), ' '.join('%03x' % p for p in sorted(R - allp))))
for name, a, b in phases:
    G = [g for g in gfs if a <= g <= b]
    if not G: continue
    cnt = collections.Counter(p for g in G for p in F[g]); n = len(G)
    per = [len(F[g]) for g in G]; nonres = [len(set(F[g]) - R) for g in G]; ncl = [len({p & ~3 for p in set(F[g]) - R}) for g in G]
    ft = sum(fetch.get(g, 0) for g in range(a, b + 1))
    print('\n== %s: guest frames %d..%d (%d with ROM reads), CD cluster fetches %d (%.1f per guest frame)' % (name, a, b, n, ft, ft / max(b - a + 1, 1)))
    print('   pages touched per frame: mean %.1f max %d; NOT resident per frame: mean %.1f max %d (in mean %.1f / max %d clusters of 16 KiB; the cache holds 2 clusters)' % (sum(per) / n, max(per), sum(nonres) / n, max(nonres), sum(ncl) / n, max(ncl)))
    P = set(cnt); print('   distinct pages in the phase: %d, not resident %d' % (len(P), len(P - R)))
    hot = sorted(P - R, key=lambda p: -cnt[p])
    print('   not resident, by share of frames touching them: ' + ' '.join('%03x:%d%%' % (p, 100 * cnt[p] // n) for p in hot[:40]))
    cold = sorted(P & R, key=lambda p: cnt[p])
    print('   resident, least used here: ' + ' '.join('%03x:%d%%' % (p, 100 * cnt[p] // n) for p in cold[:16]))
    print('   resident pages not touched at all in this phase: %d' % len(R - P))
