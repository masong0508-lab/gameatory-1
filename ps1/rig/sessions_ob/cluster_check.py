# Session for obrun.py: which ROM cluster do the CD fetches of the page cache bring in?  Independent check of misses.csv:
# every emulated frame the page table entries rom_pg[0..3] (symbol rom_pg: pointer per 4 KiB ROM page, 0 = not in RAM) are
# read; a change from 0 to a pointer is one fetch of cluster 0 (ROM offset 0..0x3fff).  Also counted: all fetches
# (rom_miss_count).  OB_FRAMES emulated frames, from power-on (after OB_SKIP frames) or from a state (--load).
import os
N = int(os.environ.get('OB_FRAMES', '3000')); SKIP = int(os.environ.get('OB_SKIP', '600'))
PGS = [int(x, 0) for x in os.environ.get('OB_PAGES', '0').split(',')]      # first page of each cluster to watch
if not S.a.load:
    S.run(SKIP)
rp = S.syms.get('rom_pg')
m0 = S.g('rom_miss_count'); g0 = S.g('g_gframes')
prev = {p: S.e.r32(rp + 4 * p) for p in PGS}; hits = {p: 0 for p in PGS}; multi = 0; lastm = m0
for f in range(N):
    S.run(1)
    m = S.g('rom_miss_count')
    if m - lastm > 1:
        multi += 1                       # more than one fetch inside one emulated frame: transitions can be missed
    lastm = m
    for p in PGS:
        v = S.e.r32(rp + 4 * p)
        if v and not prev[p]:
            hits[p] += 1
        prev[p] = v
S.mark('cluster_check', frames=N, fetches=S.g('rom_miss_count') - m0, guest_frames=S.g('g_gframes') - g0,
       fetched_cluster={'%06x' % (p << 12): hits[p] for p in PGS}, frames_with_more_than_one_fetch=multi)
