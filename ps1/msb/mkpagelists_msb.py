#!/usr/bin/env python3
"""mkpagelists_msb.py STAGE19: write t/resident_msb.txt and t/pause_pages_msb.txt from rc10's t/resident62.txt and t/pause_pages.txt.

The merged Star-FlyBack ROM keeps Payback at the same addresses except its map column table: payback-mod (paybackmod/rom.py) moves
the bytes 0x081aa8e0..0x082f6de8 (mapcodec.COLUMN_BASE .. OLD_TABLE_END) to 0x08800000 (NEW_BASE), a shift of 0x655720, and the
mod's own code takes 0x081b0000 on.  An original page p that overlaps the table therefore maps to the merged pages holding
[max(p*4096, 0x1aa8e0), min((p+1)*4096, 0x2f6de8)) + 0x655720: usually two pages, 0x8e0 bytes in p+0x655 and 0x720 bytes in p+0x656.
Page 0x1aa keeps its own number as well (0x081aa000..0x081aa8e0 is still Payback's data).  Every merged page gets a score, the
number of bytes of listed original pages it holds; the lists keep the best pages up to the limit (61 resident pages, as B1's
pg_fr leaves room for; the pause block keeps rc10's 59).  Dropped first: pages holding only a 0x720-byte tail.  Page numbers only.
"""
import sys, os
T0, T1, SH = 0x1aa8e0, 0x2f6de8, 0x655720

def pages(path):
    return [int(t, 16) for line in open(path) for t in line.split('#')[0].split()]

def remap(orig, limit, drop_last=()):
    score = {}
    for p in orig:
        if p in drop_last:
            continue
        a, b = p * 4096, (p + 1) * 4096
        lo, hi = max(a, T0), min(b, T1)
        if lo < hi:                                     # the table part moves
            for q in range((lo + SH) >> 12, ((hi + SH - 1) >> 12) + 1):
                n = min(hi + SH, (q + 1) * 4096) - max(lo + SH, q * 4096)
                score[q] = score.get(q, 0) + n
            if a < T0:                                  # unchanged prefix
                score[p] = score.get(p, 0) + (T0 - a)
            if b > T1:                                  # unchanged tail (e.g. adjacent asset)
                score[p] = score.get(p, 0) + (b - T1)
        else:
            score[p] = score.get(p, 0) + 4096
    keep = sorted(score, key=lambda q: (-score[q], q))[:limit]
    return sorted(keep), score

def write(path, head, pg):
    with open(path, 'w') as f:
        f.write(head)
        for i in range(0, len(pg), 16):
            f.write(' '.join('%03x' % q for q in pg[i:i + 16]) + '\n')

def main():
    st = sys.argv[1]
    res, rs = remap(pages(os.path.join(st, 't/resident62.txt')), 61, drop_last=(0x7d9,))
    pz, ps = remap(pages(os.path.join(st, 't/pause_pages.txt')), 59)
    com = ("# (0x081aa8e0..0x082f6de8 in the original, paybackmod mapcodec.COLUMN_BASE) moved by 0x655720 to 0x08800000 (rom.py NEW_BASE):\n"
           "# an original table page becomes the merged pages holding its bytes; the pages with the most listed bytes are kept\n"
           "# (ps1/msb/mkpagelists_msb.py; pages holding only a 0x720-byte tail go first).  Page numbers only.\n")
    write(os.path.join(st, 't/resident_msb.txt'),
          "# Milestone B (merged Star-FlyBack ROM, tools12/build_msb.sh): t/resident62.txt with the pages of Payback's map column table\n" + com +
          "# 61 pages: rc10's 0x7d9 is left out (pg_fr takes 4 KiB of the ragdoll region).\n", res)
    write(os.path.join(st, 't/pause_pages_msb.txt'),
          "# Milestone B (merged Star-FlyBack ROM, tools12/build_msb.sh): t/pause_pages.txt with the pages of Payback's map column table\n" + com +
          "# 59 pages, as rc10's block.\n", pz)
    for n, pg, sc in (('resident', res, rs), ('pause', pz, ps)):
        print('%s: %d pages, dropped %s' % (n, len(pg), ' '.join('%03x(%d)' % (q, sc[q]) for q in sorted(set(sc) - set(pg)))))

if __name__ == '__main__':
    main()
