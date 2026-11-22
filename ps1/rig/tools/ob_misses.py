#!/usr/bin/env python3
"""ob_misses.py RUNDIR: which ROM clusters (16 KiB = 4 pages = 8 sectors) the page cache keeps re-reading from CD
(misses.csv of obrun.py), per phase.  'distinct' clusters and how many of the fetches the top N account for tell how much
RAM a resident set would need to stop the reading."""
import csv, sys, collections
run = sys.argv[1]
rows = list(csv.DictReader(open(run + '/misses.csv')))
unk = sum(1 for r in rows if int(r['rom_offset_of_cluster'], 16) >= 0xfffff000)
if unk:
    print('%d of %d fetches could not be attributed to a cluster (left out)' % (unk, len(rows)))
rows = [r for r in rows if int(r['rom_offset_of_cluster'], 16) < 0xfffff000]
def stats(rs, name):
    if not rs: return
    c = collections.Counter(int(r['rom_offset_of_cluster'], 16) for r in rs)
    n = sum(c.values()); top = c.most_common()
    cum = 0; marks = {}
    for i, (k, v) in enumerate(top, 1):
        cum += v
        for q in (50, 80, 90, 95, 99):
            if q not in marks and cum * 100 >= q * n: marks[q] = i
    fr = int(rs[-1]['frame']) - int(rs[0]['frame']); gf = int(rs[-1]['gframes']) - int(rs[0]['gframes'])
    print('%s: %d fetches in %d emulated frames (%.2f per second, one every %.0f ms), %d guest frames (%.1f fetches per guest frame)' % (name, n, fr, n * 59.82 / max(fr, 1), 1000 * fr / 59.82 / n, gf, n / max(gf, 1)))
    print('   distinct clusters %d (= %d KiB of ROM); clusters needed for 50/80/90/95/99 %% of the fetches: %s' % (len(c), len(c) * 16, ' / '.join(str(marks.get(q)) for q in (50, 80, 90, 95, 99))))
    print('   most fetched (ROM offset x count): ' + ', '.join('%06x x %d' % kv for kv in top[:10]))
    # ping-pong: how often a fetch re-reads the cluster that was evicted 2 fetches ago (cache = 2 clusters)
    seq = [int(r['rom_offset_of_cluster'], 16) for r in rs]
    for depth in (2, 3, 4, 6, 8, 12, 16, 24, 32):
        hit = 0; lru = []
        for k in seq:
            if k in lru: hit += 1; lru.remove(k)
            lru.append(k)
            if len(lru) > depth: lru.pop(0)
        print('   an LRU cache of %2d clusters (%3d KiB) would have served %5.1f %% of these fetches' % (depth, depth * 16, 100.0 * hit / n))
lvl = next((i for i, r in enumerate(rows) if int(r['lvl_clock']) > 0), len(rows))
stats(rows[:lvl], 'menus'); stats(rows[lvl:], 'level')
