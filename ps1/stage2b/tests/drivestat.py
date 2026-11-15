"""drivestat.py LOG: totals of the STATLOG window lines of a scripted drive (F frame eng fps nprim ovf lod x z | max M over O slow S)."""
import re, sys
mx = over = slow = n = 0; fr = 0; lods = {}
for l in open(sys.argv[1], errors='ignore'):
    m = re.search(r'F (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)\s*\|\s*max (\d+) over (\d+) slow (\d+)', l)
    if m:
        n += 1; fr = int(m.group(1)); mx = max(mx, int(m.group(9))); over += int(m.group(10)); slow += int(m.group(11)); lods[int(m.group(6))] = lods.get(int(m.group(6)), 0) + 1
print('frames %d (windows of 64: %d)  worst engine lines %d  frames over 456 lines: %d  frames shown later than 2 fields: %d  LOD at window ends %s' % (fr, n, mx, over, slow, lods))
